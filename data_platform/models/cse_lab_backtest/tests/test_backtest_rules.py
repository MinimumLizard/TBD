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


# --- version 1.1.0's rules (decision 0025) ---------------------------------------------------------------------------

def test_the_marginal_fill_lists_the_shares_minimum_variance_would_take_next():
    # D moves with A (which is held), E does not: E is the next share minimum variance would take
    symbols = ["A", "B", "C", "D", "E"]
    sd = np.array([0.10, 0.12, 0.30, 0.30, 0.30])
    corr = np.eye(5)
    corr[0, 3] = corr[3, 0] = 0.9
    cov = np.outer(sd, sd) * corr
    full = np.array([0.6, 0.4, 0.0, 0.0, 0.0])
    assert opt.ranking(full, symbols) == ["A", "B"]                         # version 1.0.0: only what is held
    ranked = opt.ranking(full, symbols, cov)
    assert ranked[:2] == ["A", "B"] and ranked[-1] == "D" and set(ranked[2:4]) == {"C", "E"}


def test_a_k_name_portfolio_is_filled_when_minimum_variance_holds_fewer_names():
    dm = model(["A", "B", "C", "D"], [0.10, 0.40, 0.45, 0.50], corr=0.95)   # so alike that only A is worth having
    dm.full["min_variance"] = np.array([1.0, 0.0, 0.0, 0.0])
    with pytest.raises(opt.Infeasible, match="only 1 names"):
        bt.build_target(dm, "min_variance_3", None, {"buffer": 1.5}, 0.5)
    tgt = bt.build_target(dm, "min_variance_3", None, {"buffer": 1.5, "fill": "marginal"}, 0.5)
    assert tgt.names == ["A", "B", "C"] and sum(tgt.weights.values()) == pytest.approx(1.0)
    assert min(tgt.weights.values()) >= opt.retail_floor(3) - 1e-9


def near_problem():
    symbols = ["A", "B", "C", "D"]
    sd = np.array([0.18, 0.20, 0.22, 0.24])
    cov = np.outer(sd, sd) * (np.full((4, 4), 0.3) + np.eye(4) * 0.7)
    return opt.Problem(symbols=symbols, sectors=["S"] * 4, cov=cov, er=np.full(4, 0.15), rf=0.1, caps=np.full(4, 0.5),
                       liq_caps=np.full(4, 10.0), max_weight=0.5, max_sector_weight=1.0)


def test_a_review_trades_the_least_that_stays_within_the_tolerance():
    p = near_problem()
    floor = 0.05
    best = opt.solve_retail("min_variance", p, floor)
    held = np.array([0.40, 0.10, 0.40, 0.10])
    vol = lambda w: math.sqrt(w @ p.cov @ w)  # noqa: E731
    trade = lambda w: float(np.abs(w - held).sum())  # noqa: E731
    assert (opt.nearest_within(p, floor, best, held, 0.0) == best).all()          # no tolerance: the minimum itself
    near = opt.nearest_within(p, floor, best, held, 0.01)
    assert vol(near) <= vol(best) * 1.01 + 1e-9                                   # nearly as steady
    assert trade(near) < trade(best) - 0.01                                       # for clearly less trading
    assert near.sum() == pytest.approx(1.0) and near.min() >= floor - 1e-6 and near.max() <= 0.5 + 1e-6
    wider = opt.nearest_within(p, floor, best, held, 0.05)
    assert trade(wider) <= trade(near) + 1e-6                                     # more tolerance never trades more
    # holdings already within the tolerance are left exactly as they are
    close = best + np.array([0.002, -0.002, 0.001, -0.001])
    assert np.abs(opt.nearest_within(p, floor, best, close, 0.01) - close).max() < 1e-5


def test_the_tolerance_applies_only_when_something_is_held_and_only_to_minimum_variance():
    dm = model(["A", "B", "C"], [0.18, 0.20, 0.22], corr=0.3)
    spec = {"buffer": 1.5, "tolerance": 0.02}
    fresh = bt.build_target(dm, "min_variance_3", None, spec, 0.6)
    exact = bt.build_target(dm, "min_variance_3", None, {"buffer": 1.5}, 0.6)
    assert fresh.weights == exact.weights                                          # nothing held: the minimum
    held = {"A": 0.5, "B": 0.25, "C": 0.25}
    kept = bt.build_target(dm, "min_variance_3", None, spec, 0.6, held)
    assert sum(abs(kept.weights[s] - held[s]) for s in held) < sum(abs(exact.weights[s] - held[s]) for s in held)
    assert kept.volatility <= exact.volatility * 1.02 + 1e-9
    sharpe = bt.build_target(dm, "max_sharpe_3", None, spec, 0.6, held)
    assert sharpe.weights == bt.build_target(dm, "max_sharpe_3", None, {"buffer": 1.5}, 0.6).weights


def test_the_risk_tests_variance_ratio():
    from data_platform.models.cse_lab_backtest import compute as backtest
    rng = np.random.default_rng(5)
    b = rng.normal(0, 0.01, 400)
    same = backtest.variance_ratio(b, b)
    assert same == (1.0, 1.0, 1.0)
    calmer = backtest.variance_ratio(b * 0.7, b)                # the same days at 70 % of the size: 0.49, exactly
    assert all(x == pytest.approx(0.49) for x in calmer)
    other = backtest.variance_ratio(rng.normal(0, 0.007, 400), b)
    assert other[1] < other[0] < other[2] < 1.0                 # an interval around the ratio, clear of 1
    a = np.random.default_rng(9).normal(0, 0.007, 400)
    assert backtest.variance_ratio(a, b) == backtest.variance_ratio(a, b)       # a fixed seed: the same rows each run
