"""Research, not a product feature: can the old CSE terminal's model portfolios hold fewer names without losing
what they are for? (docs/plan-retail-features.md §6)

Runs the old terminal's own code (cse/lab.py, cse/optimize.py) on its own data, read-only and in memory, then
re-optimises each portfolio on only its K largest names, with
    per-stock cap  max(10%, 1.5 / K)      (10 names at a 10% cap would leave no choice at all)
    floor          0.5 / K                (every name is worth holding)
    the same sector (30%), ownership-group (20%) and liquidity caps as the full portfolio.
It compares each with the full portfolio on the old tool's own estimates (in-sample: see the plan's caveats).

Needs the old repo's environment (cvxpy, clarabel), not this repo's:
    uv venv /tmp/labvenv && VIRTUAL_ENV=/tmp/labvenv uv pip install -r <CSE clone>/requirements.txt
    /tmp/labvenv/bin/python -I scripts/research/fewer_names.py <CSE clone> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cvxpy as cp
import numpy as np

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from cse import corpactions, lab, metrics, optimize, storage  # noqa: E402
from cse.config import load_universe  # noqa: E402
from cse.estimates import all_wednesdays, build_tris, select_universe, trading_sessions  # noqa: E402
from cse.ownership import groups as ownership_groups  # noqa: E402

SIZES = (5, 6, 8, 10, 12, 15, 20, 25)


def setup():
    """The old lab's run(), up to its optimisation, without touching the record or any file."""
    paths, cfg = lab.Paths(ROOT), lab.load_config(ROOT)
    prices, indices = metrics.load_prices(paths.prices), metrics.load_indices(paths.indices)
    sessions = trading_sessions(indices)
    session = storage.last_daily_session(paths.prices) or sessions[-1]
    securities = lab.latest_securities(paths)
    equities = [s.symbol for s in securities if s.symbol.endswith(lab.EQUITY_SUFFIXES)]
    actions = corpactions.effective(storage.read_rows(paths.history / "corporate_actions.csv"),
                                    corpactions.load_reviews(ROOT / "config" / "corporate_actions_review.yaml"))
    sectors, _ = lab.sector_map(paths, equities)
    group_map, _ = ownership_groups.for_symbols(ROOT, equities)
    tris = build_tris(prices, actions, equities, cfg["dividend_withholding"], cfg["history_adjusted"])
    weeks_all = all_wednesdays(sessions, session)
    universe = select_universe(securities, prices, sessions, tris, sectors,
                               set(load_universe(ROOT / "config" / "universe.yaml").excluded), cfg, session, weeks_all)
    _, prob, weights = lab.compute({}, universe, tris, prices, indices, sectors, cfg, session, weeks_all, group_map)
    return session, cfg, prob, weights


def stats(w, prob):
    er, vol = float(w @ prob.er), float(np.sqrt(w @ prob.cov @ w))
    return {"expected_return": er, "volatility": vol, "sharpe": (er - prob.rf) / vol}


def subproblem(prob, idx, cap):
    return optimize.Problem(
        symbols=[prob.symbols[i] for i in idx], sectors=[prob.sectors[i] for i in idx],
        cov=prob.cov[np.ix_(idx, idx)], er=prob.er[idx], rf=prob.rf,
        caps=np.minimum(cap, prob.liq_caps[idx]), liq_caps=prob.liq_caps[idx], max_weight=cap,
        max_sector_weight=prob.max_sector_weight,
        groups=[prob.groups[i] for i in idx] if prob.groups else None, max_group_weight=prob.max_group_weight)


def solve(kind, p, floor):
    n = len(p.symbols)
    if kind == "max_sharpe":   # the old optimize.max_sharpe, homogenised, plus the floor
        y, k = cp.Variable(n), cp.Variable(nonneg=True)
        cons = optimize._constraints(p, y, k) + [cp.sum(y) == k, (p.er - p.rf) @ y == 1, y >= floor * k]
        problem = cp.Problem(cp.Minimize(cp.quad_form(y, cp.psd_wrap(p.cov))), cons)
        problem.solve(solver=optimize.SOLVER)
        ok = problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)
        return optimize._clean(y.value / k.value) if ok else None
    x = cp.Variable(n)
    problem = cp.Problem(cp.Minimize(cp.quad_form(x, cp.psd_wrap(p.cov))),
                         optimize._constraints(p, x) + [cp.sum(x) == 1, x >= floor])
    problem.solve(solver=optimize.SOLVER)
    return optimize._clean(x.value) if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) else None


def main() -> None:
    session, cfg, prob, weights = setup()
    report = {"session": session, "universe": len(prob.symbols), "risk_free": prob.rf, "portfolios": {}}
    for kind in ("max_sharpe", "min_variance"):
        full = weights[kind]
        base = {"names": int((full > 1e-6).sum()), **stats(full, prob)}
        rows = []
        for k in SIZES:
            cap, floor, idx = max(cfg["max_weight"], 1.5 / k), 0.5 / k, list(np.argsort(-full)[:k])
            w_k = solve(kind, subproblem(prob, idx, cap), floor)
            if w_k is None:
                rows.append({"names": k, "status": "infeasible: the sector or group caps cannot all hold"})
                continue
            w = np.zeros(len(prob.symbols))
            w[idx] = w_k
            diff = w - full
            rows.append({"names": k, "status": "ok", "cap": cap, "floor": floor, **stats(w, prob),
                         "tracking_error_vs_full": float(np.sqrt(diff @ prob.cov @ diff)),
                         "sectors": len({prob.sectors[i] for i in idx})})
        report["portfolios"][kind] = {"full": base, "fewer_names": rows}
    Path(sys.argv[2]).write_text(json.dumps(report, indent=1))
    for kind, r in report["portfolios"].items():
        f = r["full"]
        print(f"{kind}: full portfolio {f['names']} names, volatility {f['volatility']:.1%}, Sharpe {f['sharpe']:.3f}")
        for row in r["fewer_names"]:
            if row["status"] != "ok":
                print(f"  {row['names']:2d} names: {row['status']}")
                continue
            print(f"  {row['names']:2d} names: volatility {row['volatility']:.1%}, Sharpe {row['sharpe']:.3f} "
                  f"({row['sharpe'] / f['sharpe']:.0%} of full), tracking error {row['tracking_error_vs_full']:.1%}, "
                  f"{row['sectors']} sectors")


if __name__ == "__main__":
    main()
