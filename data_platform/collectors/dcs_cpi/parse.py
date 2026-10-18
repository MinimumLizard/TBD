"""Read the DCS's "Movements of the CCPI" tables. Pure functions: bytes in, rows out.

How the DCS publishes them (statistics.gov.lk, checked 2026-10-18):
  * the Monthly CCPI page links one "Movements of the CCPI" page per base year (2021, 2013, 2006/07, 2002, 1952);
  * each of those is a small HTML page holding the PDF in an <iframe>;
  * the PDF is one table: year (printed on January only), month, index number, then the month-to-month change,
    the year-on-year change and the 12-month moving average, each printed only once there is enough history.

The base year is read from the PDF's own title ("Base : 2021 = 100"), never from the link. Every index number is
checked against the changes the DCS prints beside it: a misread number would disagree with its own month-to-month
and year-on-year changes, so the file is refused rather than stored wrong. Base 1952 (1953 to 2008) is not parsed:
the comparison it would serve starts in 2003, which the 2002 base covers.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PARSER_VERSION = 1

INDEX_URL = "https://www.statistics.gov.lk/InflationAndPrices/StaticalInformation/MonthlyCCPI"
LINK_TEXT = "movements of the ccpi"          # exactly; "Movements of the CCPI, CCPI Core" is a different table
BASES = ("2021", "2013", "2006/07", "2002")   # parsed; anything else is refused
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
TITLE = re.compile(r"Base\s*:\s*(\d{4}(?:\s*/\s*\d{2})?)\s*=\s*100", re.I)
LINE = re.compile(r"^(?:(\d{4})\s+)?(" + "|".join(MONTHS) + r")\s+(\d{2,4}\.\d)((?:\s+-?\d+\.\d%?)*)\s*$")
TOLERANCE_PP = 0.2      # index numbers are printed to 0.1 and changes to 0.1 percentage points


class ParseError(ValueError):
    pass


@dataclass
class Parsed:
    dataset: str
    base: str = ""
    rows: list[dict] = field(default_factory=list)
    note: str = ""


def dataset_for(base: str) -> str:
    return "dcs_ccpi_" + base.replace("/", "_")


# --- the two HTML pages -----------------------------------------------------------------------------------------

def parse_index(html: bytes | str) -> list[str]:
    """The Monthly CCPI page -> the address of every "Movements of the CCPI" page (one per base year)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        if " ".join(a.get_text(" ", strip=True).split()).lower() == LINK_TEXT:
            href = urljoin(INDEX_URL + "/", a["href"].strip()).replace("http://", "https://", 1)
            if href not in out:
                out.append(href)
    return out


def parse_wrapper(html: bytes | str, page_url: str) -> str:
    """A "Movements of the CCPI" page -> the PDF it shows. Exactly one PDF, or an error."""
    soup = BeautifulSoup(html, "html.parser")
    srcs = {urljoin(page_url, f["src"].strip()) for f in soup.find_all(["iframe", "embed", "object"], src=True)
            if f["src"].strip().lower().endswith(".pdf")}
    srcs |= {urljoin(page_url, o["data"].strip()) for o in soup.find_all("object", data=True)
             if o["data"].strip().lower().endswith(".pdf")}
    if len(srcs) != 1:
        raise ParseError(f"{page_url}: expected one PDF, found {sorted(srcs)}")
    return srcs.pop()


# --- the PDF ----------------------------------------------------------------------------------------------------

def pdf_text(body: bytes) -> str:
    import pdfplumber  # local import: keeps the xlsx-only workflows light

    if not body.startswith(b"%PDF"):
        raise ParseError("not a PDF (an error page or a truncated download?)")
    try:
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            # dedupe_chars: a bold row is printed twice over itself ("JJuullyy 111155..44" otherwise; the 2002 base)
            return "\n".join(page.dedupe_chars().extract_text() or "" for page in pdf.pages)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"cannot read the PDF: {type(exc).__name__}: {exc}") from exc


def parse_ccpi_text(text: str) -> Parsed:
    """The text of one "Movements of the CCPI" table -> rows {index_code, base, month, value}."""
    m = TITLE.search(text)
    if not m or "ccpi" not in text[:300].lower():
        raise ParseError("no 'MOVEMENTS OF THE CCPI ... Base : YYYY = 100' title")
    base = re.sub(r"\s+", "", m.group(1))
    if base not in BASES:
        raise ParseError(f"base {base} is not one this parser reads ({', '.join(BASES)})")

    values: dict[dt.date, float] = {}
    printed: dict[dt.date, list[float]] = {}
    year, prev = None, None
    for raw in text.splitlines():
        line = " ".join(raw.split())
        hit = LINE.match(line)
        if not hit:
            if any(line.startswith(mo) or re.match(r"^\d{4}\s+" + mo, line) for mo in MONTHS):
                raise ParseError(f"a month line this parser cannot read: {line!r}")
            continue
        y, month_name, index, rest = hit.groups()
        month = MONTHS.index(month_name) + 1
        if y:
            year = int(y)
        elif prev is not None:
            year = prev.year + (1 if month == 1 and prev.month == 12 else 0)
        if year is None:
            raise ParseError(f"{line!r}: month before any year")
        day = dt.date(year, month, 1)
        if prev is not None and day != dt.date(prev.year + (prev.month == 12), prev.month % 12 + 1, 1):
            raise ParseError(f"{day:%Y-%m} follows {prev:%Y-%m}: months must run without a gap")
        prev = day
        values[day] = float(index)
        printed[day] = [float(x.rstrip("%")) for x in rest.split()]
    if len(values) < 13:
        raise ParseError(f"only {len(values)} months found")

    # Check every index number against the changes printed beside it (month to month, then year on year).
    days = sorted(values)
    checked = 0
    for i, day in enumerate(days):
        changes = printed[day]
        prev_m = days[i - 1] if i else None
        year_ago = dt.date(day.year - 1, day.month, 1)
        expect = []
        if prev_m is not None:
            expect.append(("month-to-month", values[prev_m]))
        if year_ago in values:
            expect.append(("year-on-year", values[year_ago]))
        if len(changes) > len(expect) + 1:          # +1: the 12-month moving average, not checked
            raise ParseError(f"{day:%Y-%m}: more figures than expected: {changes}")
        for (what, earlier), stated in zip(expect, changes):
            got = (values[day] / earlier - 1) * 100
            if abs(got - stated) > TOLERANCE_PP:
                raise ParseError(f"{day:%Y-%m}: index {values[day]} gives a {what} change of {got:.2f}%, "
                                 f"the table prints {stated}%")
            checked += 1
    rows = [{"index_code": "CCPI", "base": base, "month": d, "value": values[d]} for d in days]
    return Parsed(dataset_for(base), base, rows,
                  f"CCPI base {base}: {len(rows)} months {days[0]:%Y-%m} to {days[-1]:%Y-%m}; "
                  f"{checked} printed changes agree with the index numbers")


def parse_ccpi(body: bytes) -> Parsed:
    return parse_ccpi_text(pdf_text(body))
