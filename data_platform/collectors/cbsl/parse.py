"""Read the CBSL's interest-rate spreadsheets. Pure functions: bytes in, rows out. No network, no database.

Three files, all .xlsx, all hand-laid-out tables with multi-row headers:

    table 4.04  Interest Rates - Monthly (2003 to latest)   one row per month; year printed on January only
    table 4.03  Interest Rates - Annual  (1990 to latest)   one row per year (end of year)
    Treasury Bill Auctions - Weekly (1996 to latest)        one row per auction; three tenors side by side

Columns are found by their header text, never by position: the two rate tables already lay the same series out in
different columns (4.04 has a month column, 4.03 does not), and a new column would otherwise shift every value
silently. A series whose header cannot be found exactly once is an error, never a guess.

Cell values seen in the files (2026-10-18): numbers; "-", "--", "  -" and "n.a" for "no figure"; ranges such as
"7.00-11.00" (one typo, "2.50.-11.75", in table 4.03 for 2019); "Auction was not held" across an auction row.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field

PARSER_VERSION = 1

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MISSING = {"", "-", "--", "n.a", "n.a.", "na", "n/a"}
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
RANGE = re.compile(r"^(\d+(?:\.\d+)?)\.?\s*-\s*(\d+(?:\.\d+)?)$")


class ParseError(ValueError):
    """The file is not what this parser expects. Raised with a clear message; never guessed around."""


@dataclass
class Parsed:
    dataset: str
    rows: list[dict] = field(default_factory=list)
    note: str = ""


def _sheet_rows(body: bytes) -> list[tuple]:
    import openpyxl  # local import: the other collectors do not need it

    if not body.startswith(b"PK\x03\x04"):
        raise ParseError("not an .xlsx file (an error page or a truncated download?)")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any failure to open is the same problem for the caller
        raise ParseError(f"cannot open the workbook: {type(exc).__name__}: {exc}") from exc
    try:
        return [tuple(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()


def _text(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def number(v, *, where: str) -> float | None:
    """A published figure: a number, or None for the table's "no figure" marks. Anything else is an error."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ParseError(f"{where}: unexpected value {v!r}")
    if isinstance(v, (int, float)):
        return float(v)
    s = _text(v)
    if s.lower() in MISSING:
        return None
    if NUMBER.match(s):
        return float(s)
    raise ParseError(f"{where}: {v!r} is not a number")


def value_range(v, *, where: str) -> tuple[float, float] | None:
    """A range such as "7.00-11.00" -> (7.0, 11.0). A single number is a range of one value."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), float(v)
    s = _text(v)
    if s.lower() in MISSING:
        return None
    m = RANGE.match(s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
    elif NUMBER.match(s):
        lo = hi = float(s)
    else:
        raise ParseError(f"{where}: {v!r} is not a range of rates")
    if lo > hi:
        raise ParseError(f"{where}: range {v!r} runs backwards")
    return lo, hi


def _check_rate(value: float, *, where: str) -> float:
    if not -1.0 <= value <= 120.0:      # 1995's inter-bank call rate peaked at 102%: rates can be wild, not absurd
        raise ParseError(f"{where}: {value} is outside any plausible interest rate")
    return value


# --- headers ----------------------------------------------------------------------------------------------------

def _header_block(rows: list[tuple], first_data: int) -> tuple[int, int]:
    """(first, last+1) header rows: from the row naming 'End of Period' / 'Issue Date' to the first data row."""
    for i in range(first_data - 1, -1, -1):
        if any(_text(c).lower().startswith(("end of period", "issue date")) for c in rows[i]):
            return i, first_data
    raise ParseError("no header row ('End of Period' / 'Issue Date') above the data")


def _nearest_left(row: tuple, col: int) -> str:
    for c in range(min(col, len(row) - 1), -1, -1):
        if _text(row[c]):
            return _text(row[c])
    return ""


@dataclass(frozen=True)
class ColumnRule:
    series: str
    own: re.Pattern            # the column's own header text (any header row)
    group: str | None = None   # a group header that must sit at or left of the column, in some header row
    kind: str = "value"        # value | range


RATE_COLUMNS = [
    ColumnRule("OPR", re.compile(r"^(overnight policy rate|opr)\b", re.I)),
    ColumnRule("SDFR", re.compile(r"^(standing deposit|sdf rate)", re.I)),
    ColumnRule("SLFR", re.compile(r"^(standing lending|slf rate)", re.I)),
    ColumnRule("TB_3M", re.compile(r"^3-month\b", re.I), group="treasury bills"),
    ColumnRule("TB_12M", re.compile(r"^12-month\b", re.I), group="treasury bills"),
    ColumnRule("AWDR", re.compile(r"^awdr\b", re.I)),
    ColumnRule("AWFDR", re.compile(r"^awfdr\b", re.I)),
    ColumnRule("AWNDR", re.compile(r"^awndr\b", re.I)),
    ColumnRule("AWNFDR", re.compile(r"^awnfdr\b", re.I)),
    ColumnRule("FD_12M", re.compile(r"^12 months$", re.I), group="fixed deposits", kind="range"),
]


def find_columns(header: list[tuple], rules: list[ColumnRule]) -> dict[str, int]:
    """{series: column} by header text. Each rule must match exactly one column (a header may repeat its text in
    a lower row, as 4.03 does for AWNFDR: the same column counts once)."""
    width = max(len(r) for r in header)
    found: dict[str, int] = {}
    for rule in rules:
        cols = set()
        for row in header:
            for c in range(len(row)):
                if rule.own.search(_text(row[c])):
                    if rule.group is None or any(rule.group in _nearest_left(r, c).lower() for r in header):
                        cols.add(c)
        if len(cols) != 1:
            raise ParseError(f"column for {rule.series}: found {len(cols)} matching headers {sorted(cols)} "
                             f"in a {width}-column header; the table's layout has changed")
        found[rule.series] = cols.pop()
    return found


# --- tables 4.04 (monthly) and 4.03 (annual) --------------------------------------------------------------------

def _month_number(v) -> int | None:
    s = _text(v).lower()
    return MONTHS.index(s) + 1 if s in MONTHS else None


def _rate_values(row: tuple, columns: dict[str, int], where: str) -> list[tuple[str, float]]:
    out = []
    for series, col in columns.items():
        cell = row[col] if col < len(row) else None
        if series == "FD_12M":
            rng = value_range(cell, where=f"{where} {series}")
            if rng is not None:
                out.append(("FD_12M_MIN", _check_rate(rng[0], where=where)))
                out.append(("FD_12M_MAX", _check_rate(rng[1], where=where)))
            continue
        v = number(cell, where=f"{where} {series}")
        if v is not None:
            out.append((series, _check_rate(v, where=f"{where} {series}")))
    return out


def parse_monthly_rates(body: bytes) -> Parsed:
    """Table 4.04 -> rows {series, month, value}. Months must run without a gap from the first to the last."""
    rows = _sheet_rows(body)
    title = next((_text(c) for r in rows[:5] for c in r if _text(c)), "")
    if "4.04" not in title or "monthly" not in title.lower():
        raise ParseError(f"not table 4.04 (title {title!r})")
    first = next((i for i, r in enumerate(rows) if any(_month_number(c) for c in r[:4])), None)
    if first is None:
        raise ParseError("no month rows found")
    h0, h1 = _header_block(rows, first)
    header = rows[h0:h1]
    year_col = next(c for c, v in enumerate(rows[h0]) if _text(v).lower().startswith("end of period"))
    month_col = next(c for c in range(len(rows[first])) if _month_number(rows[first][c]))
    columns = find_columns(header, RATE_COLUMNS)

    out, year, prev = [], None, None
    for i in range(first, len(rows)):
        row = rows[i]
        label = _text(row[year_col]) if year_col < len(row) else ""
        if label.startswith("(") or label.lower().startswith(("source", "note")):   # footnotes: the table has ended
            break
        if isinstance(row[year_col], (int, float)) and not isinstance(row[year_col], bool):
            year = int(row[year_col])
        month = _month_number(row[month_col]) if month_col < len(row) else None
        if month is None:
            if any(_text(c) for c in row):
                raise ParseError(f"row {i + 1}: a row that is neither a month nor a footnote: {row[:6]}")
            continue                          # blank spacer row between years
        if year is None or not 1990 <= year <= 2100:
            raise ParseError(f"row {i + 1}: month without a year")
        day = dt.date(year, month, 1)
        if prev is not None and day != _next_month(prev):
            raise ParseError(f"row {i + 1}: {day:%Y-%m} follows {prev:%Y-%m}; months must run without a gap")
        prev = day
        for series, value in _rate_values(row, columns, where=f"row {i + 1} ({day:%Y-%m})"):
            out.append({"series": series, "month": day, "value": value})
    if prev is None:
        raise ParseError("no months parsed")
    months = len({r["month"] for r in out})
    return Parsed("cbsl_4.04", out, f"{len(out)} values, {months} months to {prev:%Y-%m}; "
                                    f"columns {sorted(columns)}")


def _next_month(d: dt.date) -> dt.date:
    return dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def parse_annual_rates(body: bytes) -> Parsed:
    """Table 4.03 -> rows {series, year, value} (end of year)."""
    rows = _sheet_rows(body)
    title = next((_text(c) for r in rows[:5] for c in r if _text(c)), "")
    if "4.03" not in title or "annual" not in title.lower():
        raise ParseError(f"not table 4.03 (title {title!r})")
    header_row = next((i for i, r in enumerate(rows) if any(_text(c).lower().startswith("end of period") for c in r)),
                      None)
    if header_row is None:
        raise ParseError("no 'End of Period' header")
    year_col = next(c for c, v in enumerate(rows[header_row]) if _text(v).lower().startswith("end of period"))
    first = next((i for i in range(header_row + 1, len(rows))
                  if isinstance(rows[i][year_col], int) and 1980 <= rows[i][year_col] <= 2100), None)
    if first is None:
        raise ParseError("no year rows found")
    columns = find_columns(rows[header_row:first], RATE_COLUMNS)
    out, prev = [], None
    for i in range(first, len(rows)):
        row = rows[i]
        v = row[year_col] if year_col < len(row) else None
        if _text(v).startswith("("):
            break
        if v is None:
            if any(_text(c) for c in row):
                raise ParseError(f"row {i + 1}: a row without a year: {row[:6]}")
            continue
        if not isinstance(v, int) or isinstance(v, bool):
            raise ParseError(f"row {i + 1}: {v!r} is not a year")
        if prev is not None and v != prev + 1:
            raise ParseError(f"row {i + 1}: {v} follows {prev}; years must run without a gap")
        prev = v
        for series, value in _rate_values(row, columns, where=f"row {i + 1} ({v})"):
            out.append({"series": series, "year": v, "value": value})
    if prev is None:
        raise ParseError("no years parsed")
    return Parsed("cbsl_4.03", out, f"{len(out)} values, {len({r['year'] for r in out})} years to {prev}")


# --- weekly treasury bill auctions ------------------------------------------------------------------------------

AUCTION_GROUPS = [   # (field, group header pattern)
    ("offered_mn", re.compile(r"^amount offered", re.I)),
    ("received_mn", re.compile(r"^amount received", re.I)),
    ("accepted_mn", re.compile(r"^amount accepted", re.I)),
    ("yield_without_tax_pct", re.compile(r"^weighted average yield rates? \(with ?out tax\)", re.I)),
    ("yield_pct", re.compile(r"^weighted average yield rates? \(before tax\)", re.I)),
]
TENORS = {"91 days": 91, "182 days": 182, "364 days": 364}


def parse_tbill_auctions(body: bytes) -> Parsed:
    """The weekly auction file -> rows {issue_date, tenor_days, offered_mn, ..., yield_pct}, one per tenor that has
    any figure. A yield printed as 0 (nothing accepted) is stored as None."""
    rows = _sheet_rows(body)
    title = next((_text(c) for r in rows[:5] for c in r if _text(c)), "")
    if "treasury bill auctions" not in title.lower():
        raise ParseError(f"not the treasury bill auction file (title {title!r})")
    first = next((i for i, r in enumerate(rows) if any(isinstance(c, dt.datetime) for c in r[:3])), None)
    if first is None:
        raise ParseError("no auction dates found")
    h0, h1 = _header_block(rows, first)
    header = rows[h0:h1]
    date_col = next(c for c, v in enumerate(rows[h0]) if _text(v).lower().startswith("issue date"))
    group_row = rows[h0]
    columns: dict[tuple[str, int], int] = {}
    for row in header:
        for c, v in enumerate(row):
            tenor = TENORS.get(_text(v).lower())
            if tenor is None:
                continue
            group = _nearest_left(group_row, c)
            field_ = next((f for f, pat in AUCTION_GROUPS if pat.search(group)), None)
            if field_ is None:
                raise ParseError(f"column {c}: tenor {tenor} under an unknown heading {group!r}")
            if (field_, tenor) in columns:
                raise ParseError(f"two columns for {field_} {tenor} days")
            columns[(field_, tenor)] = c
    missing = [(f, t) for f, _ in AUCTION_GROUPS for t in TENORS.values() if (f, t) not in columns]
    if missing:
        raise ParseError(f"columns not found: {missing}")

    out, prev, skipped, zero = [], None, 0, 0
    for i in range(first, len(rows)):
        row = rows[i]
        d = row[date_col] if date_col < len(row) else None
        if d is None:
            if any(_text(c) for c in row):
                text = " ".join(_text(c) for c in row if _text(c))
                if text.startswith("("):
                    break
                raise ParseError(f"row {i + 1}: a row without an issue date: {text[:80]}")
            continue
        if not isinstance(d, dt.datetime):
            raise ParseError(f"row {i + 1}: {d!r} is not a date")
        day = d.date()
        if prev is not None and day <= prev:
            raise ParseError(f"row {i + 1}: {day} is not after {prev}; auctions must be in date order")
        prev = day
        texts = [_text(c).lower() for c in row if isinstance(c, str)]
        if any(t.startswith("auction was not held") for t in texts):
            skipped += 1
            continue
        for tenor in TENORS.values():
            rec = {"issue_date": day, "tenor_days": tenor}
            for field_, _ in AUCTION_GROUPS:
                col = columns[(field_, tenor)]
                v = number(row[col] if col < len(row) else None, where=f"row {i + 1} ({day}) {field_} {tenor}d")
                if field_.startswith("yield"):
                    if v == 0:
                        v, zero = None, zero + 1
                    if v is not None:
                        _check_rate(v, where=f"row {i + 1} {field_}")
                elif v is not None and v < 0:
                    raise ParseError(f"row {i + 1}: negative amount {v}")
                rec[field_] = v
            if any(rec[f] is not None for f, _ in AUCTION_GROUPS):
                out.append(rec)
    if prev is None:
        raise ParseError("no auctions parsed")
    return Parsed("cbsl_tbill_auctions", out,
                  f"{len(out)} auction-tenor rows to {prev}; {skipped} auctions not held; {zero} yields printed as 0 "
                  "(nothing accepted) stored as blank")


PARSERS = {"cbsl_4.04": parse_monthly_rates, "cbsl_4.03": parse_annual_rates,
           "cbsl_tbill_auctions": parse_tbill_auctions}
