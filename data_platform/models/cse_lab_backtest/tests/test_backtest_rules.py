"""The walk-forward engine's rules on made-up numbers: the check dates, the tracking error, the statistics, and a
small run where everything can be worked out by hand."""
from __future__ import annotations

import math

import numpy as np
import pytest

from data_platform.models._lib import cse_backtest as bt
from data_platform.models._lib import cse_optimize as opt

SESSIONS = ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-30", "2026-05-04", "2026-05-05",
            "2026-06-01", "2026-07-01", "2026-07-02"]


def test_check_dates_are_the_start_and_each_month_s_first_session():
    assert bt.check_dates(SESSIONS, "2026-03-31") == ["2026-03-31", "2026-04-01", "2026-05-04", "2026-06-01",
                                                      "2026-07-01"]


def test_statistics():
    navs = [("2026-01-30", 100.0), ("2026-02-27", 110.0), ("2026-03-31", 99.0), ("2026-04-30", 108.9)]
    s = bt.statistics(navs, 12)
    assert s["total_return"] == pytest.approx(0.089)
    assert s["max_drawdown"] == pytest.approx(-0.10)
    assert s["best_month"] == pytest.approx(0.10) and s["worst_month"] == pytest.approx(-0.10)


def model(symbols, vols, corr=0.0):
    n = len(symbols)
    sd = np.array(vols)
    cov = np.outer(sd, sd) * (np.full((n, n), corr) + np.eye(n) * (1 - corr))
    p = opt.Problem(symbols=symbols, sectors=["S"] * n, cov=cov, er=np.full(n, 0.15), rf=0.1, caps=np.full(n, 1.0),
                    liq_caps=np.full(n, 10.0), max_weight=1.0, max_sector_weight=1.0)
    full = {"min_variance": opt.min_variance(p), "max_sharpe": opt.max_sharpe(p)}
    return bt.DateModel("x", p, full, 26, True, 0.1, {s: 1.0 for s in symbols}, dict(zip(symbols, vols)), {})


def test_tracking_error_is_zero_on_target_and_infinite_when_a_holding_left_the_universe():
    dm = model(["A", "B", "C"], [0.2, 0.2, 0.2])
    t = {"A": 0.5, "B": 0.5}
    assert bt.tracking_error(t, t, dm) == 0.0
    assert bt.tracking_error({"A": 0.5, "Z": 0.5}, t, dm) == math.inf
    assert bt.tracking_error({"A": 1.0}, t, dm) == pytest.approx(math.sqrt(0.25 * 0.04 + 0.25 * 0.04))


def test_a_target_explains_each_holding():
    dm = model(["A", "B", "C"], [0.10, 0.20, 0.40])
    tgt = bt.build_target(dm, "min_variance_2", None, {"buffer": 1.5}, 0.5)
    assert tgt.names == ["A", "B"]                     # the two lowest-risk names
    assert sum(tgt.weights.values()) == pytest.approx(1.0) and tgt.weights["A"] > tgt.weights["B"]
    h = {x["symbol"]: x for x in tgt.holdings}
    assert h["A"]["volatility"] == pytest.approx(0.10) and h["A"]["avg_correlation"] == pytest.approx(0.0)
    assert sum(x["risk_contribution"] for x in tgt.holdings) == pytest.approx(1.0)


CFG = {"record_notional_lkr": 1_000_000, "cost_per_side": 0.01, "dividend_withholding": 0.0,
       "rebalance_months": [1, 4, 7, 10], "band_relative": 0.25, "band_absolute": 0.02, "min_trade_lkr": 0.0,
       "te_threshold": 0.03}


def test_a_small_run_by_hand():
    dm = model(["A", "B"], [0.2, 0.2])                 # equal risk: minimum variance holds half of each
    closes = {"A": {s: 100.0 for s in SESSIONS}, "B": {s: 100.0 for s in SESSIONS}}
    aspi = {s: 1000.0 for s in SESSIONS}
    res = bt.run(SESSIONS, "2026-03-31", lambda s: dm, closes, [], aspi, lambda s: 0.0, CFG, {"buffer": 1.5}, 1.0,
                 ["min_variance_2"], ["quarterly", "dynamic"])
    q = [r for r in res.nav if r["policy"] == "quarterly" and r["portfolio"] == "min_variance_2"]
    # inception: 4,950 shares of each at Rs 100 plus 1 % cost; prices never move, so the value is what is left
    first = q[0]
    assert first["n_names"] == 2 and first["nav"] == pytest.approx(1_000_000 - 2 * 4950 * 100 * 0.01)
    kinds = {(e["policy"], e["session_date"], e["kind"]) for e in res.events}
    assert ("quarterly", "2026-04-01", "scheduled") in kinds                # the first session of April
    assert ("quarterly", "2026-07-01", "scheduled") in kinds
    assert not any(k == "threshold" for _, _, k in kinds)                   # never off target: no threshold trades
    bills = [r["nav"] for r in res.nav if r["portfolio"] == "bills"]
    assert set(bills) == {1_000_000.0}                                      # at a zero rate, bills stay put
