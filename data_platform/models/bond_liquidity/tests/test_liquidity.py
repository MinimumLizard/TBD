"""bond_liquidity: tiers, and the trade-feed lag, on a hand-made workspace."""
from __future__ import annotations

import datetime as dt

from data_platform.models._lib import bond_workspace as ws
from data_platform.models.bond_liquidity import compute as liq

DAY = dt.date(2026, 9, 30)


def _trades(conn, isin, n_days, last=DAY - dt.timedelta(days=1)):
    for k in range(n_days):
        ws.upsert_trade_summary(conn, (last - dt.timedelta(days=k)).isoformat(), isin, "TBond", None, None, None,
                                None, 10.0 + k / 100, 1_000_000_000, 3, None)


def test_tiers():
    conn = ws.open_workspace()
    _trades(conn, "ACTIVE", 12)
    _trades(conn, "CORE", 8)
    _trades(conn, "WIDER", 3)
    ws.upsert_auction(conn, (DAY - dt.timedelta(days=120)).isoformat(), "CORE", "auction", None, 10.0, 100, 250, 90,
                      None)
    facts = liq.profile(conn, DAY.isoformat())
    assert {k: v["tier"] for k, v in facts.items()} == {"ACTIVE": "active", "CORE": "core", "WIDER": "wider"}
    assert facts["CORE"]["is_benchmark"] and facts["CORE"]["days_since_auction"] == 120   # day 120 still counts
    assert facts["CORE"]["bid_to_cover"] == 2.5
    assert facts["ACTIVE"]["last_trade_date"] == (DAY - dt.timedelta(days=1)).isoformat()
    assert facts["ACTIVE"]["trades_through"] == (DAY - dt.timedelta(days=1)).isoformat()


def test_a_late_trade_file_does_not_demote_a_bond_but_a_dead_feed_does():
    conn = ws.open_workspace()
    _trades(conn, "X", 10, last=DAY - dt.timedelta(days=3))     # trade files published to 3 days ago
    assert liq.profile(conn, DAY.isoformat())["X"]["days_traded"] == 10
    later = DAY + dt.timedelta(days=60)                           # feed silent for 63 days: window ends on the day
    facts = liq.profile(conn, later.isoformat())["X"]
    assert facts["days_traded"] == 0 and facts["trade_data_lag_days"] == 0 and facts["tier"] == "wider"
