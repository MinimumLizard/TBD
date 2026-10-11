"""cse_security_metrics: the look-ups, and a hand-made history checked by hand."""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import run_models
from data_platform.core import db
from data_platform.models.cse_security_metrics import compute as sm


def test_history_lookups():
    d = [dt.date(2026, 9, k) for k in (1, 2, 3, 7)]
    h = sm.History(d, [10.0, 10.5, 16.0, 16.2])                  # 10.5 -> 16.0 is a 52% move
    assert h.last_on_or_before(dt.date(2026, 9, 5)) == 16.0
    assert h.last_on_or_before(dt.date(2026, 8, 31)) is None
    assert h.has_jump(dt.date(2026, 9, 1), dt.date(2026, 9, 7))
    assert not h.has_jump(dt.date(2026, 9, 3), dt.date(2026, 9, 7))   # the jump needs both closes in range
    assert not h.has_jump(dt.date(2026, 9, 1), dt.date(2026, 9, 2))


def test_range_position():
    assert sm.range_position(15, 10, 20) == 0.5
    assert sm.range_position(15, 20, 20) is None and sm.range_position(None, 10, 20) is None


SESSIONS = [dt.date(2026, 6, 1) + dt.timedelta(days=k) for k in range(70)]


@pytest.fixture
def metrics(conn, store):
    f, _ = db.record_fetch(conn, store, source_id="cse_api", method="POST", url="https://www.cse.lk/api/test",
                           params={}, http_status=200, body=b"{}", content_type="application/json",
                           fetched_at=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
    now = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
    for k, day in enumerate(SESSIONS):
        conn.execute("""insert into cse.indices_daily (session_date, index_code, source, value, change, fetch_id,
                        fetched_at) values (%s, 'ASI', 'backfill', %s, null, %s, %s)""", (day, 100.0 + k, f, now))
        if k == 69:                                               # the last session: no trade, company info only
            continue
        close = 50.0 + k                                          # a steady rise ...
        if k >= 60:
            close *= 1.5                                          # ... and a 50% jump at session 60
        conn.execute("""insert into cse.prices_daily (session_date, symbol, source, close, previous_close,
                        volume_total, turnover_est, fetch_id, fetched_at)
                        values (%s, 'AAA.N0000', 'backfill', %s, null, %s, null, %s, %s)""",
                     (day, close, 100.0 * (k + 1), f, now))
    conn.execute("""insert into cse.company_info_daily (session_date, symbol, last_traded_price, high_52w, low_52w,
                    market_cap, beta_triasi, fetch_id, fetched_at)
                    values (%s, 'AAA.N0000', 177.0, 200.0, 40.0, 1e9, 0.8, %s, %s)""", (SESSIONS[-1], f, now))
    conn.commit()
    run_models(conn, ["cse_security_metrics"])
    return {r["session_date"]: r for r in conn.execute("select * from models.cse_security_session")}


@pytest.mark.db
def test_relative_return_and_volume_by_hand(metrics):
    row = metrics[SESSIONS[30]]
    p1, p0 = 50.0 + 30, 50.0 + 25
    a1, a0 = 130.0, 125.0
    assert row["ret_1w"] == pytest.approx(p1 / p0 - 1)
    assert row["rel_1w"] == pytest.approx((p1 / p0 - 1) - (a1 / a0 - 1))
    assert row["rel_3m"] is None                                  # 63 sessions are not there yet
    assert row["vol_avg20"] == pytest.approx(sum(100.0 * (k + 1) for k in range(10, 30)) / 20)
    assert row["vol_ratio"] == pytest.approx(3100.0 / row["vol_avg20"])
    assert not row["range_flag"] and row["flag_1m"] is None


@pytest.mark.db
def test_a_big_move_is_flagged_and_a_day_without_a_trade_uses_the_company_summary(metrics):
    assert metrics[SESSIONS[63]]["flag_1w"] == sm.JUMP_FLAG and metrics[SESSIONS[63]]["range_flag"]
    assert metrics[SESSIONS[66]]["flag_1w"] is None              # the jump has left the 5-session window
    last = metrics[SESSIONS[-1]]
    assert not last["traded"] and last["close"] == 177.0
    assert last["range_pos"] == pytest.approx((177.0 - 40.0) / 160.0)
    assert last["vol_ratio"] == 0.0 and last["beta"] == 0.8 and last["market_cap"] == 1e9
    assert last["rel_3m"] is not None                             # last close on or before each end of the window
