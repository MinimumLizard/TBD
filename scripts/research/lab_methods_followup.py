"""Research, not a product feature: follow-ups to the pre-registered tests (the research note, §7.6). Each is labelled
by why it was run after the results were seen; none is used to choose a method on its own.

  D1  diagnostic: nonlinear shrinkage on the plain daily returns (no lagged terms), the form the method was designed
      for, beside the current estimate
  C1  confirmation: HRP within the lab's limits (10 % a share, 30 % a sector, floor 0.5 / K), against minimum
      variance, on the same 15 names: does the advantage survive the limits that any adoption would impose?
  C2  confirmation: the rules that passed (HRP within limits, half-yearly reviews), together, with costs, beside the
      current rules and beside each change alone

    DATABASE_URL=... uv run python scripts/research/lab_methods_followup.py <out.json>
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
from data_platform.models._lib import cse_optimize as opt
from data_platform.models._lib import cse_weighting as wt
from data_platform.models.cse_lab_backtest import compute as backtest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_methods import judge, walk  # noqa: E402


def hrp_target(dm, names, k, max_weight):
    p = dm.problem
    idx = [p.symbols.index(x) for x in names]
    cov = p.cov[np.ix_(idx, idx)]
    w = wt.hrp(cov)
    return wt.within_limits(w, opt.retail_cap(k, max_weight), opt.retail_floor(k), [p.sectors[i] for i in idx],
                            p.max_sector_weight)


def main() -> int:
    target = Path(sys.argv[1]).resolve()
    conn = db.connect(settings_mod.load().database_url)
    manifest = framework.load_manifest("cse_lab_backtest")
    su = backtest.setup(framework.Inputs(conn, manifest, manifest.current), None)
    start = su.start()
    spec = {**su.spec, "tolerance": 0}
    out = {}

    # D1
    def form_d1(s0):
        dm = su.model_on(s0, "daily")
        got = su.estimates_on(s0)
        if dm is None or got is None or got[0].estimates is None:
            return None
        e = got[0].estimates
        D, per_year = backtest.daily_returns(su.h, e)
        X = D - D.mean(axis=0)
        C = cv.nonlinear(X.T @ X / len(X), len(X)) * per_year
        p = dm.problem
        alt = opt.Problem(p.symbols, p.sectors, C, p.er, p.rf, p.caps, p.liq_caps, p.max_weight, p.max_sector_weight,
                          p.groups, p.max_group_weight)
        return {"daily": (p.symbols, dm.full["min_variance"]), "nonlinear_plain": (p.symbols, opt.min_variance(alt))}
    out["d1_full"] = judge(*walk(su, start, form_d1), su, "daily")

    # C1
    state = {"names": None}
    def form_c1(s0):
        dm = su.model_on(s0, "daily")
        if dm is None:
            return None
        tgt = bt.build_target(dm, "min_variance_15", state["names"], spec, su.ocfg["max_weight"])
        state["names"] = tgt.names
        return {"min_variance": (tgt.names, [tgt.weights[x] for x in tgt.names]),
                "hrp_within_limits": (tgt.names, hrp_target(dm, tgt.names, 15, su.ocfg["max_weight"])),
                "hrp_free": (tgt.names, wt.hrp(dm.problem.cov[np.ix_([dm.problem.symbols.index(x) for x in tgt.names],
                                                                      [dm.problem.symbols.index(x) for x in tgt.names])]))}
    out["c1_15"] = judge(*walk(su, start, form_c1), su, "min_variance")

    # C2: with costs, through the engine; HRP weights replace minimum variance's on the same names
    original = bt.build_target

    def build_hrp(dm, portfolio, prev_names, spec_, max_weight, current=None):
        t = original(dm, portfolio, prev_names, {**spec_, "tolerance": 0}, max_weight, current)
        if not portfolio.startswith("min_variance"):
            return t
        k = int(portfolio.rsplit("_", 1)[1])
        w = hrp_target(dm, t.names, k, max_weight)
        weights = dict(zip(t.names, w))
        for h in t.holdings:
            h["weight"] = weights[h["symbol"]]
        idx = [dm.problem.symbols.index(x) for x in t.names]
        vol = float(math.sqrt(w @ dm.problem.cov[np.ix_(idx, idx)] @ w))
        return bt.Target(t.portfolio, t.names, weights, t.holdings, t.binding, vol)

    rows = {}
    for name, hrp_on, months in (("current", False, None), ("hrp", True, None), ("half_yearly", False, [1, 7]),
                                 ("hrp_half_yearly", True, [1, 7])):
        bt.build_target = build_hrp if hrp_on else original
        rcfg = {**su.rcfg, **({"rebalance_months": months} if months else {})}
        res = bt.run(su.sessions, start, lambda s: su.model_on(s, "daily"), su.closes, su.actions, su.aspi, su.rf_on,
                     rcfg, su.spec, su.ocfg["max_weight"], ["min_variance_15"], [bt.QUARTERLY])
        bt.build_target = original
        r = {x["portfolio"]: x for x in backtest.summaries(res, rcfg)}["min_variance_15"]
        rows[name] = {k: (str(v) if k.endswith("_date") else v) for k, v in r.items()}
    out["c2"] = rows

    for key in ("d1_full", "c1_15"):
        r = out[key]
        print(f"\n{key}: {r['weeks']} weeks")
        for name, v in r["rows"].items():
            print(f"  {name:<20} vol {v['realised_volatility']:.2%}  fall {v['largest_fall']:+.2%}  turnover "
                  f"{v['weekly_turnover']:.2%}  ratio {v.get('variance_ratio', 1):.3f}  p {v.get('p_value', float('nan')):.3f}"
                  f"  p(Holm) {v.get('p_holm', float('nan')):.3f}")
    print("\nc2, with costs, 15 names, from", start)
    for name, v in out["c2"].items():
        print(f"  {name:<16} return {v['total_return']:+.2%}  vol {v['volatility']:.2%}  fall {v['max_drawdown']:+.2%}  "
              f"costs Rs {v['costs']:,.0f}  turnover {v['turnover']:.0%}  rebalances {v['n_rebalances']}")
    target.write_text(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
