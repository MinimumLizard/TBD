"""The optimiser (the old terminal's tests, ported to a made-up market of 30 shares with a fixed random seed) and the
versions with fewer names: every constraint holds, each portfolio does what its name says, infeasibility is named,
and the K-name selection keeps a name while it stays within the buffer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data_platform.models._lib import cse_optimize as opt
from data_platform.models._lib.cse_estimates import dimson_beta, ledoit_wolf

RNG = np.random.default_rng(20261020)
N, T = 30, 52
SYMS = [f"S{i:02d}.N0000" for i in range(N)]
SECTORS = ["Banks"] * 8 + ["Capital Goods"] * 6 + ["Materials"] * 6 + ["Utilities"] * 5 + ["Insurance"] * 5
GROUPS = ["G1"] * 6 + [s for s in SYMS[6:]]               # six shares trace to one holder
MARKET = RNG.normal(0.002, 0.025, T)
R = pd.DataFrame({s: 0.8 * MARKET + RNG.normal(0, 0.02 + 0.001 * i, T) for i, s in enumerate(SYMS)},
                 index=[f"w{i:02d}" for i in range(T)])
COV, SHRINK = ledoit_wolf(R)
RF = 0.099
MED = pd.Series({s: 2_000_000.0 + 400_000.0 * i for i, s in enumerate(SYMS)})


def problem(max_weight=0.10, max_sector=0.30, size=5_000_000, symbols=None, groups=None, group_cap=None):
    syms = symbols or SYMS
    idx = [SYMS.index(s) for s in syms]
    er = pd.Series({s: RF + (0.8 + 0.02 * i) * 0.06 for i, s in enumerate(SYMS)})
    cfg = {"max_weight": max_weight, "max_sector_weight": max_sector, "participation": 0.2, "days_to_build": 10,
           "notional_lkr": size}
    if group_cap:
        cfg["max_group_weight"] = group_cap
    return opt.make_problem(syms, dict(zip(SYMS, SECTORS)), COV[np.ix_(idx, idx)], er, RF, MED, cfg,
                            dict(zip(SYMS, GROUPS)) if groups else None)


def test_the_covariance_is_ledoit_wolf_in_the_stored_factor_form():
    X = R.to_numpy() - R.to_numpy().mean(axis=0)
    S = X.T @ X / T
    rebuilt = 52 * ((1 - SHRINK) * S + SHRINK * np.trace(S) / N * np.eye(N))
    assert np.allclose(rebuilt, COV, rtol=1e-12, atol=1e-15) and 0 < SHRINK < 1


@pytest.mark.parametrize("solver", [opt.min_variance, opt.risk_parity, opt.max_sharpe])
def test_every_constraint_holds_and_the_weights_sum_to_one(solver):
    p = problem()
    w = solver(p)
    rep = opt.constraint_report(w, p)
    assert rep["ok"], rep
    assert w.sum() == pytest.approx(1.0, abs=1e-9) and (w >= 0).all() and (w <= 0.10 + 1e-6).all()
    assert (p.sector_matrix() @ w <= 0.30 + 1e-6).all()


def test_the_liquidity_cap_binds_for_a_large_portfolio():
    p = problem(size=400_000_000)
    assert (p.liq_caps < 0.10).sum() >= 10
    for solver in (opt.min_variance, opt.risk_parity, opt.max_sharpe):
        w = solver(p)
        assert (w <= p.liq_caps + 1e-6).all() and opt.constraint_report(w, p)["ok"]


def test_minimum_variance_has_the_lowest_variance_and_maximum_sharpe_the_highest_sharpe():
    p = problem()
    mv, rp, ms = opt.min_variance(p), opt.risk_parity(p), opt.max_sharpe(p)
    ew = np.full(N, 1 / N)
    assert all(mv @ p.cov @ mv <= w @ p.cov @ w + 1e-10 for w in (rp, ms, ew))
    sharpe = lambda w: (p.er @ w - RF) / np.sqrt(w @ p.cov @ w)  # noqa: E731
    assert all(sharpe(ms) >= sharpe(w) - 1e-6 for w in (mv, rp))


def test_risk_parity_equalises_contributions_when_no_cap_binds():
    p = problem(max_weight=1.0, max_sector=1.0)
    rc = opt.risk_contributions(opt.risk_parity(p), p.cov)
    assert rc.sum() == pytest.approx(1.0) and rc.max() - rc.min() < 1e-4


def test_the_frontier_rises_in_return_and_in_risk():
    pts = opt.frontier(problem(), points=10)
    ers, vols = [x["er"] for x in pts], [x["vol"] for x in pts]
    assert len(pts) >= 8 and ers == sorted(ers) and all(b >= a - 1e-9 for a, b in zip(vols, vols[1:]))


@pytest.mark.parametrize("kw,match", [
    ({"symbols": SYMS[:8]}, "max_weight"),                                 # 8 x 10 % < 100 %
    ({"symbols": SYMS[:8], "max_weight": 0.5}, "sector caps bind"),        # all banks, 30 % sector cap
    ({"size": 1e12}, "liquidity caps"),
    ({"symbols": SYMS[:6], "max_weight": 1.0, "max_sector": 1.0, "groups": True, "group_cap": 0.5}, "group caps bind"),
])
def test_infeasibility_names_what_binds(kw, match):
    with pytest.raises(opt.Infeasible, match=match):
        opt.check_feasible(problem(**kw))


def test_the_group_cap_holds_and_a_one_share_group_adds_no_constraint():
    p = problem(max_weight=0.10, max_sector=0.6, groups=True, group_cap=0.12)
    assert p.group_names == ["G1"]
    w = opt.max_sharpe(p)
    assert pd.Series(w, index=p.groups).groupby(level=0).sum()["G1"] <= 0.12 + 1e-6
    assert problem().group_names == [] and opt.constraint_report(opt.min_variance(problem()), problem())[
        "max_group_over"] == -1.0


def test_what_binds_is_said_in_words():
    free = opt.min_variance(problem(max_weight=0.10, max_sector=0.6))
    cap = round(float(free[:6].sum()) / 2, 2)           # half of what the six shares of G1 take without a group cap
    p = problem(max_weight=0.10, max_sector=0.6, groups=True, group_cap=cap)
    words = opt.binding(opt.min_variance(p), p)
    assert any(x.startswith(f"ownership group G1 at the {cap:.0%} cap") for x in words), words
    assert opt.binding(np.full(N, 1 / N), problem(max_weight=1.0, max_sector=1.0)) == []


def test_dimson_beta_sums_the_current_and_lagged_slopes():
    m = R.mean(axis=1)
    y = 0.7 * m + 0.3 * m.shift(1).fillna(0)
    b, b0, b1 = dimson_beta(y, m)
    assert b0 == pytest.approx(0.7, abs=1e-6) and b1 == pytest.approx(0.3, abs=0.05) and b == pytest.approx(b0 + b1)


# --- fewer names ---------------------------------------------------------------------------------------------

def test_cap_and_floor_for_k_names():
    assert opt.retail_cap(10, 0.10) == pytest.approx(0.15) and opt.retail_cap(15, 0.10) == 0.10
    assert opt.retail_floor(10) == 0.05 and opt.retail_floor(15) == pytest.approx(1 / 30)


def test_the_k_largest_first_then_a_name_stays_within_the_buffer():
    ranked = [f"N{i}" for i in range(30)]
    assert opt.retail_names(ranked, 10, None, 1.5) == ranked[:10]
    previous = ranked[:9] + ["N14"]                     # N14 ranks 15th: inside the top 15 (1.5 x 10), it stays
    assert opt.retail_names(ranked, 10, previous, 1.5) == ranked[:9] + ["N14"]
    previous = ranked[:9] + ["N15"]                     # 16th: outside the buffer, replaced by the next best
    assert opt.retail_names(ranked, 10, previous, 1.5) == ranked[:10]
    assert opt.retail_names(ranked, 10, ["GONE"] + ranked[:9], 1.5) == ranked[:10]   # no longer in the portfolio


@pytest.mark.parametrize("kind", ["min_variance", "max_sharpe"])
@pytest.mark.parametrize("k", [10, 15])
def test_k_name_portfolios_keep_the_caps_and_the_floor(kind, k):
    p = problem(groups=True, group_cap=0.20)
    full = {"min_variance": opt.min_variance, "max_sharpe": opt.max_sharpe}[kind](p)
    names = opt.retail_names(opt.ranking(full, p.symbols), k, None, 1.5)
    sub = opt.subproblem(p, [p.symbols.index(s) for s in names], opt.retail_cap(k, 0.10))
    w = opt.solve_retail(kind, sub, opt.retail_floor(k))
    assert len(w) == k and w.sum() == pytest.approx(1.0) and (w >= opt.retail_floor(k) - 1e-6).all()
    assert opt.constraint_report(w, sub)["ok"]
    wide = np.zeros(N)
    wide[[p.symbols.index(s) for s in names]] = w
    assert opt.tracking_error(wide, full, p.cov) > 0


def test_a_k_name_portfolio_that_cannot_meet_the_caps_says_so():
    p = problem(max_weight=0.5)
    sub = opt.subproblem(p, list(range(5)), 0.5)       # five banks: the 30 % sector cap cannot be met
    with pytest.raises(opt.Infeasible, match="cannot all be met"):
        opt.solve_retail("min_variance", sub, 0.1)
    assert opt.solve_retail("equal_weight", sub, 0.1) == pytest.approx(np.full(5, 0.2))
