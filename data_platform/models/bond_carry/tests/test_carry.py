"""bond_carry: pricing, and the funding rate."""
from __future__ import annotations

import datetime as dt

import pytest

from data_platform.collectors.pdmo import isin as isin_mod
from data_platform.models._lib import bond_workspace as ws
from data_platform.models.bond_carry import compute as carry


def test_a_bond_priced_at_its_coupon_on_a_coupon_date_is_at_par():
    price, duration = carry.price_and_duration(10.0, 10.0, 3.0)
    assert price == pytest.approx(100.0)
    assert 0 < duration < 3.0


def test_a_one_period_bond_has_duration_equal_to_its_life_discounted():
    price, duration = carry.price_and_duration(8.0, 0.0, 0.5)
    assert price == pytest.approx(100 / 1.04)
    assert duration == pytest.approx(0.5 / 1.04)


def test_funding_is_volume_weighted_12_month_bills_plus_the_spread():
    conn = ws.open_workspace()
    day = dt.date(2026, 9, 30)
    one_year = isin_mod.build_bill(364, day + dt.timedelta(days=300))
    three_month = isin_mod.build_bill(91, day + dt.timedelta(days=60))
    ws.upsert_trade_summary(conn, "2026-09-29", one_year, "Tbill", None, None, None, None, 9.0, 300, 1, None)
    ws.upsert_trade_summary(conn, "2026-09-26", one_year + "", "Tbill", None, None, None, None, 9.0, 300, 1, None)
    other = isin_mod.build_bill(364, day + dt.timedelta(days=320))
    ws.upsert_trade_summary(conn, "2026-09-29", other, "Tbill", None, None, None, None, 10.0, 100, 1, None)
    ws.upsert_trade_summary(conn, "2026-09-29", three_month, "Tbill", None, None, None, None, 7.0, 10_000, 1, None)
    f = carry.funding_rate(conn, day.isoformat())
    assert f["bill_pct"] == pytest.approx((9.0 * 600 + 10.0 * 100) / 700)   # the 3-month bill is not 12-month
    assert f["rate_pct"] == pytest.approx(f["bill_pct"] + 0.05)
    assert f["as_of"] == "2026-09-29" and f["stale_days"] == 1 and f["n_bills"] == 3


@pytest.mark.db
def test_carry_on_a_real_day(bond_models):
    conn = bond_models
    funding = conn.execute("select * from models.bond_funding").fetchone()
    assert str(funding["obs_date"]) == "2026-08-31" and funding["stale_days"] == 3   # bills from the 08-28 trades
    rows = conn.execute("select * from models.bond_carry").fetchall()
    assert len(rows) > 40
    for r in rows:
        assert r["total_bp"] == pytest.approx(r["carry_bp"] + r["roll_bp"])
        assert r["carry_bp"] == pytest.approx((r["entry_yield"] - funding["rate_pct"]) * 100)
        assert r["per_duration_bp"] == pytest.approx(r["total_bp"] / r["duration"])
