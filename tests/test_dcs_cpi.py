"""The DCS CCPI collector: the Monthly CCPI page, the per-base pages, the PDF tables, end to end (no network).

Fixtures (tests/fixtures/dcs_cpi), from statistics.gov.lk on 2026-10-18: the base-2002 PDF itself (12 KB; it has the
bold, printed-twice row that needed dedupe_chars), the text of the base-2021 and base-2013 PDFs as pdf_text() reads
them, one base-year page, and the links of the Monthly CCPI page.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from data_platform.collectors.dcs_cpi import collector as dcs
from data_platform.collectors.dcs_cpi import parse
from data_platform.core.collector import Context
from data_platform.core.http import Response

FIX = Path(__file__).parent / "fixtures" / "dcs_cpi"
D = dt.date


def text(name: str) -> str:
    return (FIX / name).read_text()


def series(parsed) -> dict:
    return {r["month"]: r["value"] for r in parsed.rows}


def test_index_lists_one_page_per_base_and_not_the_core_tables():
    pages = parse.parse_index((FIX / "monthly_ccpi.html").read_bytes())
    assert len(pages) == 5 and all("Core" not in p for p in pages)
    assert pages[0].endswith("/Movementsofthe_CCPI") and pages[-1].endswith("_1952")


def test_a_base_page_gives_its_pdf():
    url = parse.parse_wrapper((FIX / "wrapper_base2021.html").read_bytes(), parse.INDEX_URL + "/Movementsofthe_CCPI")
    assert url == "https://www.statistics.gov.lk/Resource/en/InflationAndPrices/CCPI/MOVEMENTS_of_CCPI_with_MV_Base2021.pdf"
    with pytest.raises(parse.ParseError, match="expected one PDF"):
        parse.parse_wrapper(b"<html><p>moved</p></html>", parse.INDEX_URL)


def test_base_2021():
    p = parse.parse_ccpi_text(text("ccpi_base2021.txt"))
    s = series(p)
    assert p.dataset == "dcs_ccpi_2021" and p.base == "2021"
    assert min(s) == D(2022, 1, 1) and max(s) == D(2026, 9, 1) and len(s) == 57
    assert s[D(2022, 1, 1)] == 124.3 and s[D(2026, 9, 1)] == 209.1      # spot checks against the PDF


def test_base_2013():
    s = series(parse.parse_ccpi_text(text("ccpi_base2013.txt")))
    assert min(s) == D(2014, 1, 1) and max(s) == D(2023, 1, 1) and s[D(2022, 1, 1)] == 158.4


def test_base_2002_from_the_real_pdf_including_its_doubled_bold_row():
    p = parse.parse_ccpi((FIX / "MovementsofCCPI2002.pdf").read_bytes())
    s = series(p)
    assert p.base == "2002" and min(s) == D(2003, 1, 1) and max(s) == D(2011, 5, 1) and len(s) == 101
    assert s[D(2004, 7, 1)] == 115.4                   # the row printed twice over itself ("JJuullyy 111155..44")


def test_a_misread_index_number_disagrees_with_its_printed_changes():
    bad = text("ccpi_base2021.txt").replace("May 153.6", "May 135.6")
    with pytest.raises(parse.ParseError, match="2022-05: index 135.6 gives a month-to-month change"):
        parse.parse_ccpi_text(bad)


def test_a_missing_month_is_an_error():
    lines = [x for x in text("ccpi_base2021.txt").splitlines() if not x.startswith("June 171.7")]
    with pytest.raises(parse.ParseError, match="without a gap"):
        parse.parse_ccpi_text("\n".join(lines))


def test_an_unexpected_base_or_title_is_refused():
    with pytest.raises(parse.ParseError, match="base 1952"):
        parse.parse_ccpi_text(text("ccpi_base2021.txt").replace("2021 = 100", "1952 = 100"))
    with pytest.raises(parse.ParseError, match="title"):
        parse.parse_ccpi_text("Some other table\nJanuary 100.0")
    with pytest.raises(parse.ParseError, match="not a PDF"):
        parse.parse_ccpi(b"<html>error</html>")


def test_a_month_line_in_an_unknown_layout_is_an_error_not_skipped():
    bad = text("ccpi_base2021.txt").replace("March 129.7 3.1", "March 129.7 (r) 3.1")
    with pytest.raises(parse.ParseError, match="cannot read"):
        parse.parse_ccpi_text(bad)


# --- the collector against a fake DCS website -------------------------------------------------------------------

def _pdf_page(name):
    return f'<a href="">back</a><iframe src="https://www.statistics.gov.lk/Resource/en/InflationAndPrices/CCPI/{name}"></iframe>'


PAGES = {"Movementsofthe_CCPI": "base2021.pdf", "MovementsoftheCCPI": "base2013.pdf",
         "MovementsoftheCCPI2006": "base2006.pdf", "MovementsoftheCCPI2002": "MovementsofCCPI2002.pdf"}


class FakeDcs:
    def __init__(self, texts: dict | None = None):
        self.requests = []
        self.texts = texts or {}

    def request(self, method, url, params=None):
        self.requests.append(url)
        name = url.rsplit("/", 1)[-1]
        if url == parse.INDEX_URL:
            body = (FIX / "monthly_ccpi.html").read_bytes()
        elif name in PAGES:
            body = _pdf_page(PAGES[name]).encode()
        elif name.endswith(".pdf"):
            body = b"%PDF-fake " + name.encode() if name != "MovementsofCCPI2002.pdf" else (FIX / name).read_bytes()
        else:
            raise AssertionError(f"unexpected request {url}")
        return Response(method, url, params or {}, 200, body, None, dt.datetime.now(dt.timezone.utc))


def fake_parse(texts):
    """pdf_text() for the fake PDFs: the fixture texts (the real base-2002 PDF is read for real)."""
    real = parse.pdf_text

    def pdf_text(body):
        if body.startswith(b"%PDF-fake "):
            return texts[body.split(b" ", 1)[1].decode()]
        return real(body)
    return pdf_text


@pytest.fixture
def dcs_texts(monkeypatch):
    t2006 = text("ccpi_base2013.txt").replace("2013 = 100", "2006/07 = 100")   # stands in for the 2006/07 table
    texts = {"base2021.pdf": text("ccpi_base2021.txt"), "base2013.pdf": text("ccpi_base2013.txt"),
             "base2006.pdf": t2006}
    monkeypatch.setattr(parse, "pdf_text", fake_parse(texts))
    return texts


def run(conn, store, http):
    return dcs.DcsCpiCollector(Context(conn, store, http, None)).collect()


@pytest.mark.db
def test_collects_every_base_skips_1952_and_a_second_run_adds_nothing(conn, store, dcs_texts):
    http = FakeDcs()
    result = run(conn, store, http)
    conn.commit()
    assert result.new_data and not any("1952" in u for u in http.requests)
    bases = {r["base"]: r["n"] for r in conn.execute(
        "select base, count(*) n from rates.cpi_monthly_current group by 1")}
    assert bases == {"2021": 57, "2013": 109, "2006/07": 109, "2002": 101}
    again = run(conn, store, FakeDcs())
    assert not again.new_data and again.rows_added == 0


@pytest.mark.db
def test_a_replaced_pdf_becomes_current(conn, store, dcs_texts):
    run(conn, store, FakeDcs())
    conn.commit()
    dcs_texts["base2021.pdf"] += "\n"                   # the DCS republishes: same address, a new month
    lines = dcs_texts["base2021.pdf"].splitlines()
    i = next(n for n, x in enumerate(lines) if x.startswith("September 209.1"))
    lines.insert(i + 1, "October 210.1 0.5 8.4 5.1")
    dcs_texts["base2021.pdf"] = "\n".join(lines)
    http = FakeDcs()
    original = http.request

    def changed(method, url, params=None):
        r = original(method, url, params)
        if url.endswith("base2021.pdf"):
            return Response(method, url, {}, 200, b"%PDF-fake base2021.pdf v2", None, r.fetched_at)
        return r
    http.request = changed
    dcs_texts["base2021.pdf v2"] = dcs_texts["base2021.pdf"]
    result = run(conn, store, http)
    conn.commit()
    assert result.new_data
    latest = conn.execute("select max(month) m from rates.cpi_monthly_current where base = '2021'").fetchone()["m"]
    assert latest == D(2026, 10, 1)
    assert conn.execute("select count(*) n from rates.cpi_monthly where base = '2021'").fetchone()["n"] == 57 + 58


@pytest.mark.db
def test_a_missing_base_fails_the_run(conn, store, dcs_texts):
    http = FakeDcs()
    original = http.request

    def no_2002(method, url, params=None):
        r = original(method, url, params)
        if url == parse.INDEX_URL:
            body = re.sub(rb'<a href="[^"]*/MovementsoftheCCPI2002"[^>]*>.*?</a>', b"", r.body, flags=re.S)
            return Response(method, url, {}, 200, body, None, r.fetched_at)
        return r
    http.request = no_2002
    with pytest.raises(RuntimeError, match="No table found for dcs_ccpi_2002"):
        run(conn, store, http)
