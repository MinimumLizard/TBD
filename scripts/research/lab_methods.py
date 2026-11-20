"""Research, not a product feature: the lab review's pre-registered tests (docs/research/portfolio-lab-optimisation-
2026-11.md §7). Walk-forward on the lab's own data and rules (cse_lab_backtest.setup); only what was known on each date
is used to form each portfolio, and the days after judge it.

  Q1  the risk estimate: current (daily, linear shrinkage) against nonlinear shrinkage and an exponentially weighted
      matrix, for the full minimum-variance portfolio and the 15-name version
  Q2  the weighting of the same names: minimum variance against HRP, inverse volatility, equal risk contribution,
      maximum diversification and 1/N, on the 15 names and on the whole universe
  Q3  rebalancing with costs: current against partial adjustment, monthly and half-yearly reviews, a wider drift band

    DATABASE_URL=... uv run python scripts/research/lab_methods.py <out.json>     # a file OUTSIDE the repository
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
from data_platform.models._lib import cse_stats as st
from data_platform.models._lib import cse_weighting as wt
from data_platform.models.cse_lab_backtest import compute as backtest

CURRENT = "daily"


def per_year(su, days):
    years = (np.datetime64(days[-1]) - np.datetime64(days[0])).astype(int) / 365.25
    return (len(days) - 1) / years


def walk(su, start, form) -> tuple[dict[str, list[float]], dict[str, list[float]], list[str]]:
    """Each week, form(s0) -> {candidate: (symbols, weights)}; returns each candidate's daily returns over the next
    week (no costs), its weekly one-way turnover, and the weeks used."""
    dates = backtest.weekly_dates(su, start)
    series: dict[str, list[float]] = {}
    turn: dict[str, list[float]] = {}
    prev: dict[str, dict] = {}
    used = []
    for s0, s1 in zip(dates, dates[1:]):
        got = form(s0)
        if got is None:
            continue
        used.append(s0)
        for name, (symbols, w) in got.items():
            r, end = backtest.left_alone(su, symbols, np.asarray(w, float), s0, s1)
            series.setdefault(name, []).extend(r)
            new = dict(zip(symbols, w))
            if name in prev:
                old = prev[name]
                turn.setdefault(name, []).append(sum(abs(new.get(x, 0) - old.get(x, 0)) for x in set(old) | set(new)) / 2)
            prev[name] = dict(zip(symbols, end))
    return series, turn, used


def judge(series, turn, used, su, baseline) -> dict:
    days = [s for s in su.sessions if used[0] <= s <= backtest.weekly_dates(su, used[0])[-1]]
    ann = math.sqrt(per_year(su, days))
    base = np.array(series[baseline])
    out, pvals = {}, {}
    for name, r in series.items():
        a = np.array(r)
        level = np.cumprod(1 + a)
        peak = np.maximum.accumulate(np.concatenate([[1.0], level]))[1:]  # noqa: copy-lint (numpy name)
        row = {"realised_volatility": float(np.std(a, ddof=1) * ann), "weekly_turnover": float(np.mean(turn.get(name, [0]))),
               "largest_fall": float(np.min(level / peak - 1)), "days": len(a)}
        if name != baseline:
            t = st.variance_test(a, base)
            row.update(variance_ratio=t["ratio"], p_value=t["p_value"])
            pvals[name] = t["p_value"]
        out[name] = row
    for name, p in st.holm(pvals).items():
        out[name]["p_holm"] = p
        out[name]["adopt"] = bool(p < 0.05 and out[name]["variance_ratio"] < 0.95)
    return {"weeks": len(used), "first": used[0], "rows": out}


def q1(su, start, k):
    spec = {**su.spec, "tolerance": 0}
    names_prev: dict[str, list[str] | None] = {}
    def form(s0):
        out = {}
        for m in (CURRENT, "daily_nonlinear", "ewma"):
            dm = su.model_on(s0, m)
            if dm is None:
                return None
            if k is None:
                out[m] = (dm.problem.symbols, dm.full["min_variance"])
            else:
                try:
                    tgt = bt.build_target(dm, f"min_variance_{k}", names_prev.get(m), spec, su.ocfg["max_weight"])
                except Exception:
                    return None
                names_prev[m] = tgt.names
                out[m] = (tgt.names, [tgt.weights[x] for x in tgt.names])
        return out
    return judge(*walk(su, start, form), su, CURRENT)


def q2(su, start, k):
    spec = {**su.spec, "tolerance": 0}
    state = {"names": None}
    def form(s0):
        dm = su.model_on(s0, CURRENT)
        if dm is None:
            return None
        p = dm.problem
        if k is None:
            symbols, cov = p.symbols, p.cov
            out = {"min_variance": (symbols, dm.full["min_variance"])}
        else:
            tgt = bt.build_target(dm, f"min_variance_{k}", state["names"], spec, su.ocfg["max_weight"])
            state["names"] = tgt.names
            idx = [p.symbols.index(x) for x in tgt.names]
            symbols, cov = tgt.names, p.cov[np.ix_(idx, idx)]
            out = {"min_variance": (symbols, [tgt.weights[x] for x in symbols])}
        for name, f in wt.METHODS.items():
            out[name] = (symbols, f(cov))
        return out
    return judge(*walk(su, start, form), su, "min_variance")


def q3(su, start):
    variants = {"current": ({}, {}), "partial_half": ({"partial": 0.5}, {}),
                "monthly": ({}, {"rebalance_months": list(range(1, 13))}), "half_yearly": ({}, {"rebalance_months": [1, 7]}),
                "wider_band": ({}, {"band_relative": 0.5})}
    rows = {}
    for name, (spec_x, rcfg_x) in variants.items():
        rcfg = {**su.rcfg, **rcfg_x}
        res = bt.run(su.sessions, start, lambda s: su.model_on(s, CURRENT), su.closes, su.actions, su.aspi, su.rf_on,
                     rcfg, {**su.spec, **spec_x}, su.ocfg["max_weight"], ["min_variance_15"], [bt.QUARTERLY])
        summ = {r["portfolio"]: r for r in backtest.summaries(res, rcfg)}["min_variance_15"]
        rows[name] = {k: (str(v) if k.endswith("_date") else v) for k, v in summ.items()}
    return rows


def main() -> int:
    target = Path(sys.argv[1]).resolve()
    if target.is_relative_to(Path(__file__).resolve().parents[2]):
        raise SystemExit("write the results outside the repository")
    conn = db.connect(settings_mod.load().database_url)
    manifest = framework.load_manifest("cse_lab_backtest")
    su = backtest.setup(framework.Inputs(conn, manifest, manifest.current), None)
    start = su.start()
    out = {"start": start, "end": su.sessions[-1],
           "q1_full": q1(su, start, None), "q1_15": q1(su, start, 15),
           "q2_15": q2(su, start, 15), "q2_full": q2(su, start, None), "q3": q3(su, start)}
    for key in ("q1_full", "q1_15", "q2_15", "q2_full"):
        r = out[key]
        print(f"\n{key}: {r['weeks']} weeks from {r['first']}")
        print(f"{'candidate':<22}{'vol':>8}{'fall':>9}{'turnover':>10}{'var ratio':>11}{'p':>8}{'p (Holm)':>10}  adopt")
        for name, v in r["rows"].items():
            print(f"{name:<22}{v['realised_volatility']:>8.2%}{v['largest_fall']:>9.2%}{v['weekly_turnover']:>10.2%}"
                  f"{v.get('variance_ratio', 1):>11.3f}{v.get('p_value', float('nan')):>8.3f}{v.get('p_holm', float('nan')):>10.3f}"
                  f"  {v.get('adopt', '')}")
    print(f"\nq3, with costs, minimum variance 15, from {start}")
    for name, v in out["q3"].items():
        print(f"{name:<14} return {v['total_return']:+.2%}  vol {v['volatility']:.2%}  fall {v['max_drawdown']:+.2%}  "
              f"costs Rs {v['costs']:,.0f}  turnover {v['turnover']:.0%}  rebalances {v['n_rebalances']}  drift {v['n_drift']}")
    target.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwritten to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
