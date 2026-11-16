"""Research, not a product feature: which covariance estimator and which rebalancing rule should the portfolio lab
use? (decision 0025; results in docs/research/portfolio-lab-optimisation-2026-11.md)

Everything is walk-forward: on each date only the facts up to that date are read (the lab's own loaders and rules,
through cse_lab_backtest.setup). Nothing is chosen on returns: with a few months of history a difference in return
between two methods is noise. The estimators are compared on what can be measured, RISK:

  Part A  the estimators. Every week the minimum-variance portfolio is built with each estimator (the lab's caps),
          then held for a week, without costs. Compared: the realised volatility of each (lower is better: it is what
          a minimum-variance portfolio is for), the forecast volatility against the realised one (a forecast should
          be neither too low nor too high), and how much the weights change from week to week (stability).
          A paired block bootstrap says whether a difference in realised variance is distinguishable from chance.
  Part B  the rules, with the record's costs: portfolio sizes and rebalancing policies, run through the same
          engine as cse_lab_backtest. Compared: realised volatility, costs, turnover, largest fall.

    DATABASE_URL=... uv run python scripts/research/lab_tournament.py <out.json>     # a file OUTSIDE the repository
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from data_platform.core import db, settings as settings_mod
from data_platform.models import framework
from data_platform.models._lib import cse_backtest as bt
from data_platform.models._lib import cse_covariance as cv
from data_platform.models._lib import cse_estimates as est
from data_platform.models._lib import cse_optimize as opt
from data_platform.models.cse_lab_backtest import compute as backtest

BASE = "identity"
BLOCK, DRAWS, SEED = 5, 4000, 20261113


def weekly_dates(su: backtest.Setup, start: str) -> list[str]:
    """The last session on or before each Wednesday, from the walk-forward start."""
    out = []
    for w in est.wednesdays(start, su.sessions[-1]):
        s = max((x for x in su.sessions if x <= w), default=None)
        if s and s >= start and (not out or s != out[-1]):
            out.append(s)
    return out


def levels(su: backtest.Setup, symbols: list[str], days: list[str]) -> np.ndarray:
    return np.column_stack([est.sample_on_or_before(su.h.tri[s], days).to_numpy() for s in symbols])


def hold(su: backtest.Setup, symbols: list[str], w: np.ndarray, s0: str, s1: str) -> tuple[list[float], np.ndarray]:
    """Daily returns of weights w set at s0's close and left alone until s1's close, and the weights at s1."""
    days = [s for s in su.sessions if s0 <= s <= s1]
    lv = levels(su, symbols, days)
    lv = np.where(np.isfinite(lv), lv, np.nan)
    rel = lv / lv[0]
    rel = np.where(np.isfinite(rel), rel, 1.0)
    value = rel @ w
    end = rel[-1] * w
    return list(value[1:] / value[:-1] - 1), end / end.sum()


def bootstrap_ratio(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Variance of a over variance of b, with a 90 % interval from a paired moving-block bootstrap."""
    rng = np.random.default_rng(SEED)
    n = len(a)
    starts = np.arange(n - BLOCK + 1)
    ratios = []
    for _ in range(DRAWS):
        idx = np.concatenate([np.arange(s, s + BLOCK) for s in rng.choice(starts, size=math.ceil(n / BLOCK))])[:n]
        ratios.append(np.var(a[idx], ddof=1) / np.var(b[idx], ddof=1))
    return float(np.var(a, ddof=1) / np.var(b, ddof=1)), float(np.quantile(ratios, 0.05)), float(np.quantile(ratios, 0.95))


def part_a(su: backtest.Setup, start: str, k: int | None) -> dict:
    """k None: the full minimum-variance portfolio; else the lab's K-name version."""
    dates = weekly_dates(su, start)
    spec, max_w = su.spec, su.ocfg["max_weight"]
    series: dict[str, list[float]] = {m: [] for m in cv.METHODS}
    forecast: dict[str, list[float]] = {m: [] for m in cv.METHODS}
    realised_w: dict[str, list[float]] = {m: [] for m in cv.METHODS}
    turnover: dict[str, list[float]] = {m: [] for m in cv.METHODS}
    names: dict[str, list[float]] = {m: [] for m in cv.METHODS}
    shrink: dict[str, list[float]] = {m: [] for m in cv.METHODS}
    prev: dict[str, tuple[list[str], np.ndarray] | None] = {m: None for m in cv.METHODS}
    prev_names: dict[str, list[str] | None] = {m: None for m in cv.METHODS}
    short: dict[str, int] = {m: 0 for m in cv.METHODS}       # weeks when the K-name portfolio could not be formed
    equal: list[float] = []
    used = []
    for s0, s1 in zip(dates, dates[1:]):
        models = {m: su.model_on(s0, m) for m in cv.METHODS}
        if any(v is None for v in models.values()):
            continue
        used.append(s0)
        for m, dm in models.items():
            p = dm.problem
            if k is None:
                symbols, w = p.symbols, dm.full["min_variance"]
                vol = float(math.sqrt(w @ p.cov @ w))
            else:
                try:
                    tgt = bt.build_target(dm, f"min_variance_{k}", prev_names[m], spec, max_w)
                    prev_names[m] = tgt.names
                    symbols, w, vol = tgt.names, np.array([tgt.weights[x] for x in tgt.names]), tgt.volatility
                except opt.Infeasible:
                    # as the lab does: the portfolio keeps what it had (or, the first time, the full portfolio)
                    short[m] += 1
                    if prev[m] is not None and all(x in p.symbols for x in prev[m][0]):
                        symbols, w = prev[m]
                    else:
                        symbols, w = p.symbols, dm.full["min_variance"]
                    ids = [p.symbols.index(x) for x in symbols]
                    vol = float(math.sqrt(w @ p.cov[np.ix_(ids, ids)] @ w))
            r, end = hold(su, symbols, w, s0, s1)
            series[m] += r
            forecast[m].append(vol)
            realised_w[m].append(float(np.prod(1 + np.array(r)) - 1))
            names[m].append(float(1 / (w ** 2).sum()))
            got = su.estimates_on(s0)[0].estimates
            shrink[m].append(float(got.shrinkage if m == BASE else backtest.covariance_by(m, su.h, got)[1]))
            if prev[m] is not None:
                old = dict(zip(*prev[m]))
                new = dict(zip(symbols, w))
                turnover[m].append(sum(abs(new.get(x, 0) - old.get(x, 0)) for x in set(old) | set(new)) / 2)
            prev[m] = (symbols, end)
        p = models[BASE].problem
        r, _ = hold(su, p.symbols, np.full(len(p.symbols), 1 / len(p.symbols)), s0, s1)
        equal += r
    days = [s for s in su.sessions if used[0] <= s <= dates[-1]]
    years = (np.datetime64(days[-1]) - np.datetime64(days[0])).astype(int) / 365.25
    per_year = (len(days) - 1) / years
    aspi = np.array([su.aspi[s] for s in days])
    out = {"weeks": len(used), "first": used[0], "last": dates[-1], "days": len(series[BASE]), "methods": {},
           "equal_weight_vol": float(np.std(equal, ddof=1) * math.sqrt(per_year)),
           "aspi_vol": float(np.std(aspi[1:] / aspi[:-1] - 1, ddof=1) * math.sqrt(per_year))}
    base = np.array(series[BASE])
    for m in cv.METHODS:
        a = np.array(series[m])
        ratio = bootstrap_ratio(a, base) if m != BASE else (1.0, 1.0, 1.0)
        out["methods"][m] = {
            "realised_vol": float(np.std(a, ddof=1) * math.sqrt(per_year)),
            "realised_vol_weekly": float(np.std(realised_w[m], ddof=1) * math.sqrt(52)),
            "forecast_vol": float(np.mean(forecast[m])),
            "forecast_over_realised": float(np.mean(forecast[m]) / (np.std(a, ddof=1) * math.sqrt(per_year))),
            "weekly_turnover": float(np.mean(turnover[m])) if turnover[m] else None,
            "effective_names": float(np.mean(names[m])), "shrinkage": float(np.mean(shrink[m])),
            "total_return": float(np.prod(1 + a) - 1), "weeks_not_formed": short[m],
            "variance_vs_identity": ratio[0], "ratio_lo": ratio[1], "ratio_hi": ratio[2]}
    return out


def part_b(su: backtest.Setup, start: str, method: str, portfolios: list[str], policies: list[str],
           spec: dict | None = None, **overrides) -> list[dict]:
    rcfg = {**su.rcfg, **overrides}
    res = bt.run(su.sessions, start, lambda s: su.model_on(s, method), su.closes, su.actions, su.aspi, su.rf_on, rcfg,
                 {**su.spec, **(spec or {})}, su.ocfg["max_weight"], portfolios, policies)
    rows = backtest.summaries(res, rcfg)
    for r in rows:
        r.update(covariance=method, start_date=str(r["start_date"]), end_date=str(r["end_date"]), **overrides,
                 **(spec or {}))
    return rows


def sensitivity(su: backtest.Setup, start: str) -> list[dict]:
    """The daily estimator with 0 to 4 days of lagged covariances (2 was fixed before any result was seen): the
    realised volatility of the weekly full minimum-variance portfolio, as in Part A."""
    dates = weekly_dates(su, start)
    out = []
    for lags in (0, 1, 2, 3, 4):
        r_all = []
        for s0, s1 in zip(dates, dates[1:]):
            got = su.estimates_on(s0)
            e = got[0].estimates if got else None
            if e is None:
                continue
            D, per_year = backtest.daily_returns(su.h, e)
            cov, _ = cv.daily(D, per_year, lags)
            prob = opt.make_problem(e.symbols, e.sectors, cov, e.er, e.rf, e.median_turnover, su.ocfg, got[1])
            r, _ = hold(su, e.symbols, opt.min_variance(prob), s0, s1)
            r_all += r
        days = [s for s in su.sessions if dates[0] <= s <= dates[-1]]
        years = (np.datetime64(days[-1]) - np.datetime64(days[0])).astype(int) / 365.25
        out.append({"lags": lags, "realised_vol": float(np.std(r_all, ddof=1) * math.sqrt((len(days) - 1) / years))})
    return out


def main() -> int:
    target = Path(sys.argv[1]).resolve()
    if target.is_relative_to(Path(__file__).resolve().parents[2]):
        raise SystemExit("write the results outside the repository")
    conn = db.connect(settings_mod.load().database_url)
    manifest = framework.load_manifest("cse_lab_backtest")
    su = backtest.setup(framework.Inputs(conn, manifest, manifest.current), None)
    start = su.start()
    out = {"start": start, "end": su.sessions[-1], "part_a_full": part_a(su, start, None),
           "part_a_15": part_a(su, start, 15), "part_b": []}
    for name, a in (("full", out["part_a_full"]), ("15 names", out["part_a_15"])):
        print(f"\nPart A, minimum variance, {name}: {a['weeks']} weeks from {a['first']} to {a['last']}; "
              f"equal weight {a['equal_weight_vol']:.1%}, ASPI {a['aspi_vol']:.1%}")
        print(f"{'method':<14} {'realised':>9} {'weekly':>8} {'forecast':>9} {'f/r':>6} {'turnover':>9} {'eff.N':>6} "
              f"{'shrink':>7} {'var ratio (90 %)':>22}")
        for m, v in a["methods"].items():
            print(f"{m:<14} {v['realised_vol']:>9.2%} {v['realised_vol_weekly']:>8.2%} {v['forecast_vol']:>9.2%} "
                  f"{v['forecast_over_realised']:>6.2f} {v['weekly_turnover']:>9.2%} {v['effective_names']:>6.1f} "
                  f"{v['shrinkage']:>7.2f} {v['variance_vs_identity']:>8.2f} ({v['ratio_lo']:.2f}-{v['ratio_hi']:.2f})")
    out["sensitivity"] = sensitivity(su, start)
    print("\nDaily estimator, lags of covariance added: " + ", ".join(f"{r['lags']}: {r['realised_vol']:.2%}" for r in out["sensitivity"]))
    marginal = {"fill": "marginal"}
    sizes = ["min_variance_10", "min_variance_15", "min_variance_20", "min_variance_25", "equal_weight_15"]
    out["part_b"] += part_b(su, start, BASE, sizes, [bt.QUARTERLY])
    for method in ("constant_corr", "daily"):
        out["part_b"] += part_b(su, start, method, sizes, [bt.QUARTERLY], marginal)
    for tol in (0.01, 0.02, 0.05):
        for method in ("constant_corr", "daily"):
            out["part_b"] += part_b(su, start, method, ["min_variance_15"], [bt.QUARTERLY], {**marginal, "tolerance": tol})
    for te in (0.02, 0.03, 0.05):
        out["part_b"] += part_b(su, start, "daily", ["min_variance_15"], [bt.DYNAMIC], {**marginal, "tolerance": 0.02}, te_threshold=te)
    out["part_b"] += part_b(su, start, "daily", ["min_variance_15"], [bt.QUARTERLY], {**marginal, "tolerance": 0.02, "buffer": 2.0})
    print(f"\nPart B, with costs, from {start} to {su.sessions[-1]}")
    print(f"{'covariance':<14} {'policy':<10} {'portfolio':<16} {'te':>5} {'tol':>5} {'buf':>4} {'return':>8} {'vol':>7} {'fall':>7} "
          f"{'rebal':>5} {'drift':>5} {'turnover':>9} {'costs':>8}")
    for r in out["part_b"]:
        if r["portfolio"] in (bt.BILLS, bt.MARKET) and (r["covariance"] != BASE or r.get("te_threshold") or r.get("tolerance")):
            continue
        print(f"{r['covariance']:<14} {r['policy']:<10} {r['portfolio']:<16} {r.get('te_threshold') or '':>5} "
              f"{r.get('tolerance') or '':>5} {r.get('buffer') or '':>4} {r['total_return']:>8.2%} {r['volatility']:>7.2%} {r['max_drawdown']:>7.2%} {r['n_rebalances'] or 0:>5} "
              f"{r['n_drift'] or 0:>5} {(r['turnover'] or 0):>9.1%} {(r['costs'] or 0):>8,.0f}")
    target.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwritten to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
