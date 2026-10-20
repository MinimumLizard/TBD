"""cse_fundamentals: the ported reading rules on a synthetic report (tests/fixtures/cse/reports; made-up company),
the trailing-twelve-month arithmetic, the ratios end to end, and the point-in-time rule. The exactness of the port
is proven against the old code by the legacy parity test."""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import run_models
from data_platform.core import db
from data_platform.models._lib import cse_figures as fig
from data_platform.models.cse_ownership.tests.test_ownership import TEXT, _fetch, add_report, add_session

D1, D2 = dt.date(2026, 10, 1), dt.date(2026, 10, 2)


def test_eps_and_nav_reconcile_inside_the_report_and_fix_its_unit():
    x = fig.extract(TEXT, 100e6)
    assert (x["eps"], x["unit"], x["profit"], x["eps_class"]) == (1.10, 1e3, 110_000_000.0, "quarter")
    assert (x["nav"], x["nav_unit"], x["equity"]) == (25.0, 1e3, 2_500_000_000.0)
    assert fig.extract(TEXT, 300e6)["eps"] is None          # no share count, no figure: never guessed


def test_tolerance_is_two_percent_plus_the_printed_rounding():
    assert fig._tol(10.0) == pytest.approx(0.02 + 0.005 / 10)
    assert fig._tol(0.04) == pytest.approx(0.02 + 0.005 / 0.04)
    assert fig._tol(0.001) == 0.15
    assert fig._reconcile(1.10, 110_000, 100e6) == 1e3 and fig._reconcile(-1.10, 110_000, 100e6) is None


def test_which_quarter_a_report_covers():
    assert fig.quarter_end("x", "2026-06-30") == "2026-06-30"
    assert fig.quarter_end("Interim statements for the quarter ended 30th June 2026", "2026-07-28") == "2026-06-30"
    assert fig.quarter_end("Accounts 31.12.2025", "2026-02-10") == "2025-12-31"
    assert fig.quarter_end("no date", "2026-08-14") == "2026-06-30"         # the last quarter end 15+ days before
    assert fig.fiscal_quarter("2026-06-30", "1") == (2027, 1) and fig.fiscal_quarter("2026-03-31", "1") == (2026, 4)
    assert fig.fiscal_quarter("2026-06-30", "2") == (2026, 2) and fig.fiscal_quarter("2026-07-31", "2") is None


def test_ttm_adds_four_consecutive_quarters_from_quarter_and_year_to_date_columns():
    rows = [{"period_date": p, "eps_status": "verified", "profit": v, "eps_class": c} for p, v, c in (
        ("2025-09-30", 30.0, "ytd"),        # Q2 year to date: Q1 (10) + Q2 (20)
        ("2025-06-30", 10.0, "quarter"),
        ("2025-12-31", 25.0, "quarter"),
        ("2026-03-31", 100.0, "ytd"),       # Q4 year to date: Q4 = 100 - 55 = 45
        ("2026-06-30", 12.0, "unknown"))]   # Q1: an unknown column counts (both readings agree)
    assert fig.ttm(rows, "1") == (20.0 + 25.0 + 45.0 + 12.0, "2026-06-30", "sum of 4 quarters' profit")
    profit, _, note = fig.ttm(rows[:3], "1")
    assert profit is None and note == "quarter 4 of FY2025 not known"


@pytest.mark.parametrize("v, stored", [(0.123456789123, 0.12345679), (3.0, 3.0), (1 / 3, 0.33333333)])
def test_numbers_are_read_back_as_the_old_csv_stored_them(v, stored):
    assert fig.csv_float(v) == stored


# --- end to end ---------------------------------------------------------------------------------------------------

QUARTERS = [(200 + i, dt.date(*d)) for i, d in enumerate(((2025, 9, 30), (2025, 12, 31), (2026, 3, 31), (2026, 6, 30)))]


def seed(conn, store):
    add_session(conn, store, D1)
    for rid, period in QUARTERS:
        add_report(conn, store, rid, TEXT, dt.datetime.combine(period + dt.timedelta(days=40), dt.time(6),
                                                               dt.timezone.utc), period=period)
    fid, sha = _fetch(conn, store, "companyProfile", b'{"reqComSumInfo": [{"finYearEnd": "1"}]}',
                      {"symbol": "TESTCO.N0000"})
    db.insert_facts(conn, "cse.company_fiscal_years", [{"symbol": "TESTCO.N0000", "raw_sha256": sha,
                                                         "session_date": D1, "fin_year_end": "1", "fetch_id": fid,
                                                         "fetched_at": dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)}],
                    key=["symbol", "raw_sha256"])
    run_id = conn.execute("insert into models.runs (model, method_version, code_version) values "
                          "('cse_corporate_actions', '1.0.0', 'test') returning run_id").fetchone()["run_id"]
    for aid, ex, announced, amount in (("1:TESTCO.N0000", "2026-09-01", "2026-08-20", 2.0),
                                       ("2:TESTCO.N0000", "2026-09-20", "2026-10-02", 0.5)):   # announced after D1
        conn.execute("""insert into models.cse_corporate_action_used (method_version, action_id, symbol, action_type,
                        ex_date, amount_per_share, status, note, source_url, announced_date, run_id)
                        values ('1.0.0', %s, 'TESTCO.N0000', 'cash_dividend', %s, %s, 'confirmed', '', '', %s, %s)""",
                     (aid, ex, amount, announced, run_id))
    conn.commit()


def ratios(conn):
    return {(r["session_date"], r["code"]): r for r in conn.execute("select * from models.cse_fundamentals")}


@pytest.mark.db
def test_the_ratios_from_four_reconciled_quarters(conn, store):
    seed(conn, store)
    run_models(conn, ["cse_fundamentals"])
    r = ratios(conn)[(D1, "TESTCO")]
    assert r["ttm_profit"] == pytest.approx(440e6) and r["ttm_eps"] == pytest.approx(4.4)
    assert r["ttm_to"] == dt.date(2026, 6, 30) and r["fye"] == "31 Mar"
    assert r["nav"] == pytest.approx(25.0) and r["nav_period"] == dt.date(2026, 6, 30)
    assert r["pe"] == pytest.approx(50 / 4.4) and r["pb"] == pytest.approx(2.0) and r["roe"] == pytest.approx(4.4 / 25)
    assert r["div_ttm"] == 2.0 and r["dy"] == pytest.approx(0.04)     # the dividend announced after D1 is not known
    assert r["report_id"] == 203 and r["report_url"] == "https://cdn.cse.lk/203.pdf"
    figures = {f["report_id"]: f for f in conn.execute("select * from models.cse_report_figures")}
    assert len(figures) == 4 and all(f["eps_status"] == "verified" and f["shares"] == pytest.approx(100e6) for f in figures.values())


@pytest.mark.db
def test_a_session_never_changes_when_later_sessions_arrive(conn, store):
    seed(conn, store)
    run_models(conn, ["cse_fundamentals"])
    before = ratios(conn)
    add_session(conn, store, D2, issued=200e6, close=40.0)      # a share issue and a new price
    conn.commit()
    run_models(conn, ["cse_fundamentals"])
    after = ratios(conn)
    strip = lambda r: {c: v for c, v in r.items() if c != "run_id"}  # noqa: E731
    assert strip(after[(D1, "TESTCO")]) == strip(before[(D1, "TESTCO")])
    d2 = after[(D2, "TESTCO")]
    assert d2["shares"] == 200e6 and d2["ttm_eps"] == pytest.approx(2.2) and d2["div_ttm"] == 2.5   # both dividends
    assert conn.execute("select count(*) n from models.revisions where table_name = 'models.cse_fundamentals'"
                        ).fetchone()["n"] == 0
