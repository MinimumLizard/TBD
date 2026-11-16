"""Research, not a product feature: which covariance estimator and which rebalancing rule should the portfolio lab
use? (decision 0025; results in docs/research/portfolio-lab-optimisation-2026-11.md)

Everything is walk-forward: on each date only the facts up to that date are read (the lab's own loaders and rules,
through cse_lab_backtest.setup). Nothing is chosen on returns: with a few months of history a difference in return
between two methods is noise. The estimators are compared on what can be measured, RISK:

  Part A  the estimators (the model's own risk test, cse_lab_backtest.risk_test). Every week the minimum-variance
          portfolio is built with each estimator (the lab's caps), then held for a week, without costs. Compared: the
          realised volatility of each (lower is better: it is what a minimum-variance portfolio is for), the forecast
          volatility against the realised one, and how much the weights change from week to week. A paired block
          bootstrap says whether a difference in realised variance is distinguishable from chance. Then the daily
          estimator with 0 to 4 lagged days (2 was fixed in advance).
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

from data_platform.core import db
from data_platform.core import settings as settings_mod
from data_platform.models import framework
from data_platform.models._lib import cse_backtest as bt
from data_platform.models._lib import cse_covariance as cv
from data_platform.models._lib import cse_optimize as opt
from data_platform.models.cse_lab_backtest import compute as backtest

BASE = "identity"


def part_a(su: backtest.Setup, start: str, k: int | None) -> list[dict]:
    """The model's own risk test (cse_lab_backtest.risk_test), which version 1.1.0 stores with every run."""
    return [{**r, "start_date": str(r["start_date"]), "end_date": str(r["end_date"])} for r in backtest.risk_test(su, start, k)]


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
    dates = backtest.weekly_dates(su, start)
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
            r, _ = backtest.left_alone(su, e.symbols, opt.min_variance(prob), s0, s1)
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
    for name, rows in (("full", out["part_a_full"]), ("15 names", out["part_a_15"])):
        print(f"\nPart A, minimum variance, {name}: {rows[0]['n_weeks']} weeks from {rows[0]['start_date']} to {rows[0]['end_date']}")
        print(f"{'estimator':<18} {'realised':>9} {'forecast':>9} {'turnover':>9} {'eff.N':>6} {'variance ratio (90 %)':>24}")
        for r in rows:
            ratio = "" if r.get("variance_ratio") is None else f"{r['variance_ratio']:.2f} ({r['ratio_low']:.2f}-{r['ratio_high']:.2f})"
            f = lambda v, spec: "" if v is None else format(v, spec)
            print(f"{r['estimator']:<18} {r['realised_volatility']:>9.2%} {f(r.get('forecast_volatility'), '.2%'):>9} "
                  f"{f(r.get('weekly_turnover'), '.2%'):>9} {f(r.get('effective_names'), '.1f'):>6} {ratio:>24}")
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
