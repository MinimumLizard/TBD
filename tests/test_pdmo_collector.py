"""The PDMO collector end to end, against real index pages and real report files (no network)."""
from __future__ import annotations

import datetime as dt
import gzip
from pathlib import Path

import pytest

from data_platform.collectors.pdmo import collector as pdmo
from data_platform.collectors.pdmo import index
from data_platform.collectors.pdmo.facts import parse_file
from data_platform.core.collector import Context
from data_platform.core.http import Response

FIX = Path(__file__).parent / "fixtures" / "pdmo"


def page(name: str) -> bytes:
    return gzip.open(FIX / name).read()


# --- index pages (real HTML saved 2026-10-11) -----------------------------------------------------------------

def test_real_index_pages_parse():
    daily = index.parse_daily_index(page("index_daily_2026.html.gz"))
    kinds = {e.kind for e in daily}
    assert kinds == {"volumes", "daily_summary"} and len(daily) > 300
    assert len(index.parse_trade_summary_index(page("index_trades_2026.html.gz"))) > 150
    assert len(index.parse_issuance_index(page("index_issuance_2026.html.gz"))) > 10
    assert len(index.parse_auction_index(page("index_auction_2026.html.gz"))) > 10


def test_next_years_page_already_exists_and_is_empty():
    # treasury.gov.lk/.../section/2027 answered 200 with a normal page on 2026-10-11, listing no files yet.
    assert index.parse_daily_index(page("index_daily_2027_empty.html.gz")) == []


def test_years_are_derived_not_typed_in():
    assert list(pdmo.index_years(dt.date(2026, 12, 31))) == [2025, 2026]
    assert list(pdmo.index_years(dt.date(2027, 1, 1))) == [2025, 2026, 2027]   # the old pipeline stopped here


# --- facts ------------------------------------------------------------------------------------------------------

def test_daily_summary_keeps_every_quote_row():
    parsed = parse_file("daily_summary", (FIX / "daily_summary_2026-08-31.xls").read_bytes())
    assert parsed.report_date == dt.date(2026, 8, 31) and parsed.trading_date == dt.date(2026, 8, 28)
    assert len(parsed.rows) == 92                     # all live rows, including step-coupon bonds
    assert any(r["n_coupon_steps"] > 1 for r in parsed.rows)


def test_volumes_dated_by_the_data():
    parsed = parse_file("volumes", (FIX / "volumes_2025-12-19_typo_title.xls").read_bytes(), dt.date(2025, 12, 19))
    assert parsed.report_date == dt.date(2025, 12, 19)


# --- the collector against a fake PDMO website ------------------------------------------------------------------

INDEX_HTML = """<html><body><div class="page-template--body__content">
<p>&gt; 31.08.2026 <a href="/api/file/vol-0828">Outright Treasury Bond Transactions Volumes as at 28.08.2026</a>
   <a href="/api/file/sum-0831">Daily Summary Report</a></p>
</div></body></html>"""
TRADES_HTML = """<html><body><div class="page-template--body__content">
<p><a href="/api/file/trd-0828">Secondary Market Trade Summary - 28 August 2026</a></p></div></body></html>"""
AUCTION_HTML = """<html><body><div class="page-template--body__content">
<p>12.01.2026 <a href="/api/file/auc-0112">Treasury Bond Auction 12 January 2026 | English</a></p></div></body></html>"""
ISSUANCE_HTML = """<html><body><div class="page-template--body__content">
<p>25 August 2026 <a href="/api/file/ann-0825">English</a></p></div></body></html>"""
EMPTY_HTML = page("index_daily_2027_empty.html.gz").decode("utf-8", "replace")

FILES = {
    "vol-0828": "volumes_2025-12-19_typo_title.xls",
    "sum-0831": "daily_summary_2026-08-31.xls",
    "trd-0828": "trade_summary_2026-08-28.pdf",
    "auc-0112": "auction_2026-01-12_wrapped.pdf",
    "ann-0825": "announcement_2026-08-25.pdf",
}


class FakePdmo:
    """Serves index pages for 2025 (empty unless told otherwise) and 2026, and the fixture files."""

    def __init__(self, empty_2026_daily: bool = False, broken_file: str | None = None):
        self.empty_2026_daily = empty_2026_daily
        self.broken_file = broken_file
        self.requests = []

    def request(self, method, url, params=None):
        self.requests.append(url)
        if "/api/file/" in url:
            key = url.rsplit("/", 1)[-1]
            body = b"not a spreadsheet" if key == self.broken_file else (FIX / FILES[key]).read_bytes()
        elif url.endswith("/2026"):
            body = {"report-daily-report": EMPTY_HTML if self.empty_2026_daily else INDEX_HTML,
                    "reports-secondary-market-trade-summary": TRADES_HTML,
                    "treasury-bonds-issuances": ISSUANCE_HTML,
                    "result-treasury-bonds": AUCTION_HTML}[url.split("/web/")[1].split("/")[0]].encode()
        else:  # 2025 pages: reuse the 2026 listings (same URLs) so nothing is "empty" in a past year
            return self.request(method, url[:-4] + "2026", params)
        return Response(method, url, params or {}, 200, body, None, dt.datetime.now(dt.timezone.utc))


def run(conn, store, http, now=dt.datetime(2026, 10, 11, 1, 0, tzinfo=dt.timezone.utc)):
    ctx = Context(conn, store, http, None, now)
    return pdmo.PdmoCollector(ctx).collect()


@pytest.mark.db
def test_first_run_stores_everything_as_published_and_second_run_is_a_no_op(conn, store):
    result = run(conn, store, FakePdmo())
    conn.commit()
    counts = {t: conn.execute(f"select count(*) n from bonds.{t}").fetchone()["n"]
              for t in ("quotes", "volumes", "trades", "auction_results", "auction_announcements", "source_files")}
    assert counts["quotes"] == 92 and counts["source_files"] == 5
    assert all(n > 0 for n in counts.values())
    assert result.new_data
    # every stored fact traces to an archived file
    orphans = conn.execute("""select count(*) n from bonds.quotes q
                              left join ops.raw_objects o on o.sha256 = q.raw_sha256 where o.sha256 is null""")
    assert orphans.fetchone()["n"] == 0
    again = run(conn, store, FakePdmo())
    assert not again.new_data and again.rows_added == 0


@pytest.mark.db
def test_current_views_pick_one_file_per_day(conn, store):
    run(conn, store, FakePdmo())
    conn.commit()
    n = conn.execute("select count(distinct raw_sha256) n from bonds.quotes_current").fetchone()["n"]
    assert n == 1


@pytest.mark.db
def test_an_index_page_that_suddenly_lists_nothing_fails_loudly(conn, store):
    with pytest.raises(RuntimeError, match="ZERO files"):
        run(conn, store, FakePdmo(empty_2026_daily=True))


@pytest.mark.db
def test_a_new_years_empty_page_in_january_is_expected(conn, store):
    http = FakePdmo()
    original = http.request

    def with_empty_2027(method, url, params=None):
        if url.endswith("/2027"):
            http.requests.append(url)
            return Response(method, url, {}, 200, EMPTY_HTML.encode(), None, dt.datetime.now(dt.timezone.utc))
        return original(method, url, params)

    http.request = with_empty_2027
    result = run(conn, store, http, now=dt.datetime(2027, 1, 5, 1, 0, tzinfo=dt.timezone.utc))
    assert result.new_data
    assert any(u.endswith("/2027") for u in http.requests)          # 2027 was asked for, automatically


@pytest.mark.db
def test_an_unparseable_file_is_recorded_and_fails_the_run(conn, store):
    with pytest.raises(RuntimeError, match="parse failed"):
        run(conn, store, FakePdmo(broken_file="sum-0831"))
    conn.rollback()
    row = conn.execute("select parse_status, parse_note from bonds.source_files where url like '%sum-0831'").fetchone()
    assert row["parse_status"] == "failed"          # committed before the run failed: nothing is lost
    assert conn.execute("select count(*) n from ops.raw_fetches where url like '%sum-0831'").fetchone()["n"] == 1


@pytest.mark.db
def test_a_dead_link_or_bad_file_never_blocks_the_rest_and_is_retried_next_run(conn, store):
    http = FakePdmo(broken_file="sum-0831")
    original = http.request

    def dead_volumes_link(method, url, params=None):
        if url.endswith("/vol-0828"):
            raise ConnectionError("connection reset")
        return original(method, url, params)

    http.request = dead_volumes_link
    with pytest.raises(RuntimeError, match="download failed.*vol-0828") as caught:
        run(conn, store, http)
    assert "parse failed" in str(caught.value)
    conn.rollback()
    stored = {r["url"].rsplit("/", 1)[-1] for r in conn.execute("select url from bonds.source_files")}
    assert {"trd-0828", "auc-0112", "ann-0825"} <= stored     # the files listed after the dead link still came in
    again = run(conn, store, FakePdmo())                       # the site is fixed: both are fetched again
    conn.commit()
    ok = {r["url"].rsplit("/", 1)[-1] for r in conn.execute(
        "select url from bonds.source_files where parse_status = 'ok'")}
    assert again.new_data and {"vol-0828", "sum-0831"} <= ok
