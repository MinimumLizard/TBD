"""CSE parsers and collectors, against real API responses recorded on 2026-10-02 (copied from the old repo's
tests/fixtures; no network). Per-company calls are limited to the companies those recordings cover."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from data_platform.collectors.cse import collector as cse
from data_platform.collectors.cse import parse
from data_platform.core.collector import Context
from data_platform.core.http import Response

FIX = Path(__file__).parent / "fixtures" / "cse" / "2026-10-02"
SESSION = dt.date(2026, 10, 2)
SYMBOLS = {"CIC.N0000", "LOLC.N0000", "NTB.N0000"}


def body(name: str) -> bytes:
    return (FIX / name).read_bytes()


# --- parsers ----------------------------------------------------------------------------------------------------

def test_session_comes_from_the_api_not_the_clock():
    session, market, tri = parse.session_and_market(body("dailyMarketSummery.json"))
    assert session == SESSION
    assert [m["session_date"] for m in market] == [SESSION, dt.date(2026, 10, 1)]
    assert {r["index_code"] for r in tri} == {"ASTRI", "S&P SL20 TRI"}


def test_trade_summary_keeps_both_volume_definitions():
    rows = parse.trade_summary(body("tradeSummary.json"), SESSION)
    assert len(rows) == 24                                    # the recording is a trimmed copy of the session
    lioc = next(r for r in rows if r["symbol"] == "LIOC.N0000")
    assert lioc["volume_regular"] == 62740 and lioc["volume_total"] == 551334   # audit addendum item 4


def test_trade_summary_for_another_session_is_refused():
    with pytest.raises(ValueError, match="tradeSummary is for"):
        parse.trade_summary(body("tradeSummary.json"), dt.date(2026, 10, 5))


def test_chart_history_is_unadjusted_and_has_no_turnover():
    rows = parse.stock_chart(body("companyChartDataByStock/CIC.N0000.json"), "CIC.N0000")
    assert all(r["turnover"] is None and r["turnover_est"] == r["close"] * r["volume_total"] for r in rows)
    pre = next(r for r in rows if r["session_date"] == dt.date(2025, 10, 13))
    post = next(r for r in rows if r["session_date"] == dt.date(2025, 10, 22))
    assert pre["close"] / post["close"] > 4.5                 # CIC's 1:5 split shows as a raw price break


def test_company_info_must_be_for_the_symbol_asked():
    with pytest.raises(ValueError, match="returned"):
        parse.company_info(body("companyInfoSummery/CIC.N0000.json"), "LOLC.N0000", SESSION)


# --- collectors against a fake CSE API serving the recordings ---------------------------------------------------

class FakeCse:
    def __init__(self, status="Market Closed"):
        self.status = status
        self.calls = []

    def request(self, method, url, params=None):
        ep = url.rsplit("/", 1)[-1]
        params = params or {}
        self.calls.append(ep)
        if ep == "marketStatus":
            data = json.dumps({"status": self.status}).encode()
        elif ep in ("companyInfoSummery", "companyProfile"):
            data = body(f"{ep}/{params['symbol']}.json")
        elif ep == "companyChartDataByStock":
            sym = next(s["symbol"] for s in json.loads(body("allSecurityCode.json")) if s["id"] == params["stockId"])
            data = body(f"companyChartDataByStock/{sym}.json")
        elif ep == "chartData":
            data = body("chartData_1_p5.json") if params["chartId"] == 1 else b"[]"
        elif ep in ("getAnnouncementById", "getGeneralAnnouncementById"):
            p = FIX / ep / f"{params['announcementId']}.json"
            if p.exists():
                data = p.read_bytes()
            else:   # what the API really does: 204 from the typed endpoint, {} from the general one
                return Response(method, url, params, 204 if ep == "getAnnouncementById" else 200,
                                b"" if ep == "getAnnouncementById" else b"{}", None, dt.datetime.now(dt.timezone.utc))
        else:
            data = body(f"{ep}.json")
        return Response(method, url, params, 200, data, "application/json", dt.datetime.now(dt.timezone.utc))


def make(cls, conn, store, http):
    c = cls(Context(conn, store, http, None, dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)))
    c.only_symbols = SYMBOLS
    return c


@pytest.mark.db
def test_end_of_day_stores_the_session_once(conn, store):
    result = make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()
    conn.commit()
    n = lambda t: conn.execute(f"select count(*) n from {t}").fetchone()["n"]  # noqa: E731
    assert n("cse.prices_daily") == 24 and n("cse.market_daily") == 2
    assert n("cse.company_info_daily") == 3 and n("cse.company_profiles") == 3
    assert n("cse.indices_daily") == 22 + 4          # 22 from allSectors + two TRI series for two sessions
    assert result.new_data
    again = make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()
    assert not again.new_data and "no new session" in again.message


@pytest.mark.db
def test_an_open_market_is_never_snapshotted(conn, store):
    with pytest.raises(RuntimeError, match="open session"):
        make(cse.CseEndOfDayCollector, conn, store, FakeCse(status="Market Open")).collect()


@pytest.mark.db
def test_an_api_session_older_than_stored_is_an_error(conn, store):
    make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()
    conn.commit()
    fetch_id = conn.execute("select max(fetch_id) f from ops.raw_fetches").fetchone()["f"]
    conn.execute("""insert into cse.prices_daily (session_date, symbol, source, close, fetch_id, fetched_at)
                    values ('2026-10-06', 'CIC.N0000', 'daily', 1, %s, now())""", (fetch_id,))
    conn.commit()
    with pytest.raises(RuntimeError, match="older than"):
        make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()


@pytest.mark.db
def test_announcements_fetch_detail_once_per_new_id(conn, store):
    http = FakeCse()
    first = make(cse.CseAnnouncementsCollector, conn, store, http).collect()
    conn.commit()
    assert first.rows_added >= 3
    rows = conn.execute("select * from cse.announcements where announcement_id not like 'F%'").fetchall()
    assert all(r["symbol"] for r in rows)
    http2 = FakeCse()
    assert make(cse.CseAnnouncementsCollector, conn, store, http2).collect().rows_added == 0
    assert "getAnnouncementById" not in http2.calls                 # known ids: no detail calls


@pytest.mark.db
def test_history_job_fills_only_missing_sessions(conn, store):
    make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()
    conn.commit()
    hist = make(cse.CseHistoryCollector, conn, store, FakeCse())
    first = hist.collect()
    conn.commit()
    # the 2026-10-02 session already has daily rows, so the chart's 2026-10-02 bar is not written again
    dup = conn.execute("""select count(*) n from cse.prices_daily where session_date = '2026-10-02'
                          and source = 'backfill' and symbol = any(%s)""", (list(SYMBOLS),)).fetchone()["n"]
    assert first.rows_added > 0 and dup == 0
    assert make(cse.CseHistoryCollector, conn, store, FakeCse()).collect().rows_added == 0


@pytest.mark.db
def test_one_company_failing_never_loses_the_others_and_the_next_run_completes_it(conn, store):
    http = FakeCse()
    original = http.request
    victim = sorted(SYMBOLS)[0]

    def one_broken_company(method, url, params=None):
        if url.endswith("/companyInfoSummery") and (params or {}).get("symbol") == victim:
            raise ConnectionError("timed out")
        return original(method, url, params)

    http.request = one_broken_company
    with pytest.raises(RuntimeError, match=f"1 company summaries failed: {re.escape(victim)}"):
        make(cse.CseEndOfDayCollector, conn, store, http).collect()
    conn.rollback()
    n = lambda: conn.execute("select count(*) n from cse.company_info_daily").fetchone()["n"]  # noqa: E731
    assert n() == len(SYMBOLS) - 1 and conn.execute("select count(*) n from cse.prices_daily").fetchone()["n"] == 24
    again = make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()   # same session, later run
    conn.commit()
    assert n() == len(SYMBOLS) and "1 company summaries completed" in again.message
    last = make(cse.CseEndOfDayCollector, conn, store, FakeCse()).collect()
    assert "no new session" in last.message
