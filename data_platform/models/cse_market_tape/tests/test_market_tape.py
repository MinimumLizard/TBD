"""cse_market_tape on a small hand-made history, where every number can be checked by hand."""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import run_models
from data_platform.core import db

SESSIONS = [dt.date(2026, 9, 1) + dt.timedelta(days=k) for k in range(22)]


def _fetch(conn, store) -> int:
    fetch_id, _ = db.record_fetch(conn, store, source_id="cse_api", method="POST", url="https://www.cse.lk/api/test",
                                  params={}, http_status=200, body=b"{}", content_type="application/json",
                                  fetched_at=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
    return fetch_id


@pytest.fixture
def tape(conn, store):
    f = _fetch(conn, store)
    now = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
    for k, day in enumerate(SESSIONS):
        conn.execute("""insert into cse.indices_daily (session_date, index_code, source, value, change, fetch_id,
                        fetched_at) values (%s, 'ASI', 'daily', %s, %s, %s, %s)""", (day, 20000 + k, 1.0, f, now))
        conn.execute("""insert into cse.market_daily (session_date, source, turnover, volume, trades, foreign_buy,
                        foreign_sell, listed, traded, per, fetch_id, fetched_at)
                        values (%s, 'daily', %s, 1000, 50, 30, 10, 289, 250, 10.8, %s, %s)""",
                     (day, 100.0 + k, f, now))
    last = SESSIONS[-1]
    for symbol, close, prev in (("UP.N0000", 11, 10), ("DOWN.X0000", 9, 10), ("FLAT.N0000", 10, 10),
                                ("RIGHTS.R0000", 1, 2)):
        conn.execute("""insert into cse.prices_daily (session_date, symbol, source, close, previous_close, fetch_id,
                        fetched_at) values (%s, %s, 'daily', %s, %s, %s, %s)""", (last, symbol, close, prev, f, now))
    conn.commit()
    run_models(conn, ["cse_market_tape"])
    return conn


@pytest.mark.db
def test_activity_against_the_previous_20_sessions(tape):
    rows = {r["session_date"]: r for r in tape.execute("select * from models.cse_market_session")}
    last = rows[SESSIONS[-1]]
    assert last["turnover"] == 121.0
    assert last["turnover_avg20"] == pytest.approx(sum(101.0 + k for k in range(20)) / 20)   # sessions 2..21
    assert last["sessions_needed"] == 0
    early = rows[SESSIONS[4]]
    assert early["turnover_avg20"] is None and early["sessions_needed"] == 16
    assert last["foreign_net"] == 20.0 and last["per"] == 10.8


@pytest.mark.db
def test_breadth_counts_ordinary_shares_only(tape):
    last = tape.execute("select * from models.cse_market_session order by session_date desc limit 1").fetchone()
    assert (last["equities_up"], last["equities_down"], last["equities_flat"], last["equities_traded"]) == (1, 1, 1, 3)


@pytest.mark.db
def test_index_change_as_a_fraction_of_the_previous_level(tape):
    row = tape.execute("select * from models.cse_index_session where session_date = %s", (SESSIONS[0],)).fetchone()
    assert row["pct"] == pytest.approx(1.0 / 19999.0)
