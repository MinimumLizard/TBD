"""cse_portfolio_lab: the model portfolios per estimate date (audit C10) and, from version 1.1.0, the versions with
fewer names (docs/plan-retail-features.md §6). INTERNAL RESEARCH: unpublished (config/entitlements.yaml); no page or
API route reads it; the owner reads it through the lab report job.

Version 1.0.0 ports MinimumLizard/CSE@e05c6f3 cse/optimize.py and the optimising half of cse/lab.py compute() (the
arithmetic in data_platform/models/_lib/cse_optimize.py): for every estimate date of cse_risk_estimates, the caps
(10 % per share, 30 % per sector, 20 % per ownership group, a liquidity cap for the portfolio size), the feasibility
check naming what binds, minimum variance, risk parity, maximum Sharpe, equal weight, and the constrained efficient
frontier. The portfolio size is the owner's (private settings); without them version 1.0.0 computes nothing.
Version 1.1.0: the liquidity caps for a stated neutral notional (Rs 1 mn); the market (ASPI) as a reference row; and
the versions with K names (10 and 15): minimum variance, maximum Sharpe and equal weight on the K largest names of the
full portfolio of the same kind (a name already in stays while it ranks in the top 1.5 K), re-optimised with the same
sector, group and liquidity caps, a per-share cap of max(10 %, 1.5 / K) and a floor of 0.5 / K, set on the first
estimate date and then only on the quarterly rebalance dates.

Reuse: every date's inputs (its estimates and weekly returns, the parameters, the previous rebalance date's names
for the versions with fewer names, and this code) are fingerprinted (models.cse_lab_summary.inputs_sha256). A date
whose fingerprint has not changed keeps its stored rows; any other date is computed afresh. The result is the same as
computing every date again (tested); it only saves time.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .._lib import cse_optimize as opt
from .._lib.cse_calendar import ASPI, excluded_sessions, session_filter
from .._lib.cse_estimates import ledoit_wolf
from .._lib.cse_record import is_scheduled

OUTPUTS = ("models.cse_lab_summary", "models.cse_lab_cap", "models.cse_lab_portfolio", "models.cse_lab_weight",
           "models.cse_lab_exposure", "models.cse_lab_frontier")
_LIB = Path(__file__).resolve().parents[1] / "_lib"
CODE_SHA256 = hashlib.sha256(b"".join(p.read_bytes() for p in (
    Path(__file__), _LIB / "cse_optimize.py", _LIB / "cse_estimates.py"))).hexdigest()


def _f(v):
    return None if v is None else float(v)


# --- reading -----------------------------------------------------------------------------------------------------

def risk_inputs(inputs, as_of):
    """cse_risk_estimates' rows: summaries by date, estimates by date, weekly returns by series."""
    where, params = session_filter(as_of, "as_of")
    summaries = sorted(inputs.rows("models.cse_risk_summary", "*", where=where, params=params),
                       key=lambda r: r["as_of"])
    est: dict[dt.date, list[dict]] = defaultdict(list)
    for r in inputs.rows("models.cse_risk_estimate", "*", where=where, params=params, order_by="as_of, symbol"):
        est[r["as_of"]].append(r)
    weekly: dict[str, dict[str, float]] = defaultdict(dict)
    wwhere, wparams = session_filter(as_of, "week_end")
    for r in inputs.rows("models.cse_weekly_return", "series, week_end, weekly_return", where=wwhere,
                         params=wparams):
        weekly[r["series"]][r["week_end"].isoformat()] = r["weekly_return"]
    return summaries, est, weekly


def stored_outputs(inputs, as_of) -> dict[str, dict[dt.date, list[dict]]]:
    """This version's own stored rows, by table and date (for reuse)."""
    v = inputs.version.method_version
    where = "method_version = %s" + (" and as_of <= %s" if as_of else "")
    out = {}
    for table in OUTPUTS:
        by: dict[dt.date, list[dict]] = defaultdict(list)
        for r in inputs.rows(table, "*", where=where, params=(v, as_of) if as_of else (v,)):
            r.pop("run_id", None)
            r.pop("method_version", None)
            by[r["as_of"]].append(r)
        out[table] = by
    return out


def notional(inputs, p: dict, as_of) -> float | None:
    if p.get("notional") != "private":
        return float(p["notional_lkr"])
    sub = "(select max(version_id) from cse.lab_private_settings" + (
        " where loaded_at < (%s::date + 1))" if as_of else ")")
    rows = inputs.rows("cse.lab_private_settings", "settings", where=f"version_id = {sub}",
                       params=(as_of,) if as_of else ())
    size = rows[0]["settings"].get("portfolio_size_lkr") if rows else None
    return float(size) if size else None


def calendar(inputs, as_of, skip) -> list[str]:
    where, params = session_filter(as_of)
    return sorted(r["session_date"].isoformat() for r in inputs.rows(
        "cse.indices_daily_current", "session_date", where=" and ".join(filter(None, ["index_code = %s", where])),
        params=(ASPI, *params)) if r["session_date"] not in skip)


# --- one date ----------------------------------------------------------------------------------------------------

def returns_window(summary: dict, symbols: list[str], weekly: dict) -> pd.DataFrame:
    """The T x N weekly returns the estimates used: the weeks from first_week to last_week, as the old R."""
    first, last = summary["first_week"].isoformat(), summary["last_week"].isoformat()
    cols = {}
    for s in symbols:
        series = {w: v for w, v in sorted(weekly[s].items()) if first <= w <= last}
        cols[s] = pd.Series(series)
    return pd.DataFrame(cols)


def problem_of(summary: dict, rows: list[dict], weekly: dict, cfg: dict) -> tuple[opt.Problem, pd.DataFrame]:
    symbols = [r["symbol"] for r in rows]
    R = returns_window(summary, symbols, weekly)
    cov, shrinkage = ledoit_wolf(R)
    if shrinkage != summary["shrinkage"]:
        raise RuntimeError(f"{summary['as_of']}: the covariance rebuilt from the stored weekly returns has shrinkage "
                           f"{shrinkage!r}, the estimates stored {summary['shrinkage']!r}")
    er = pd.Series({r["symbol"]: r["expected_return"] for r in rows})
    med = pd.Series({r["symbol"]: r["median_turnover"] for r in rows})
    sectors = {r["symbol"]: r["sector"] for r in rows}
    groups = {r["symbol"]: r["group_key"] for r in rows}
    return opt.make_problem(symbols, sectors, cov, er, summary["risk_free"], med, cfg, groups), R


def fingerprint(summary: dict, rows: list[dict], R: pd.DataFrame | None, extra: dict) -> str:
    body = {"code": CODE_SHA256, "summary": {k: v for k, v in summary.items() if k not in ("run_id",)},
            "estimates": [{k: v for k, v in r.items() if k != "run_id"} for r in rows],
            "returns": None if R is None else [list(R.index), list(R.columns), R.to_numpy().tolist()],
            "extra": extra}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=repr).encode()).hexdigest()


def portfolio_rows(day: dt.date, name: str, family: str, w: np.ndarray, p: opt.Problem, *, k: int | None = None,
                   formed_on: dt.date | None = None, full: np.ndarray | None = None, floor: float | None = None,
                   check: bool = True, labels: dict | None = None, message: str | None = None) -> dict:
    """The rows of one portfolio at one date: its summary, weights and exposures (old summary())."""
    s = opt.summary(opt.LABELS.get(name, name), w, p)
    rep = opt.constraint_report(w, p) if check else None
    port = {"as_of": day, "portfolio": name, "family": family, "names_target": k, "status": "ok", "message": message,
            "formed_on": formed_on or day, "n_names": s["n"], "expected_return": s["er"], "volatility": s["vol"],
            "sharpe": s["sharpe"], "tracking_error": opt.tracking_error(w, full, p.cov) if full is not None else None,
            "weight_sum": rep["sum"] if rep else None, "min_weight": rep["min"] if rep else None,
            "max_over_cap": rep["max_over_cap"] if rep else None,
            "max_sector_over": rep["max_sector_over"] if rep else None,
            "max_group_over": rep["max_group_over"] if rep else None, "constraints_ok": rep["ok"] if rep else None,
            "binding": "; ".join(opt.binding(w, p, floor)) if check else None}
    idx = {sym: i for i, sym in enumerate(p.symbols)}
    weights = [{"as_of": day, "portfolio": name, "symbol": h["symbol"], "weight": h["weight"],
                "risk_contribution": h["risk_contribution"], "cap": h["cap"], "sector": h["sector"],
                "group_key": p.groups[idx[h["symbol"]]] if p.groups else h["symbol"], "expected_return": h["er"],
                "at_cap": check and h["weight"] >= h["cap"] - opt.AT_CAP} for h in s["holdings"]]
    exposure = [{"as_of": day, "portfolio": name, "kind": "sector", "name": sec, "label": None, "weight": v,
                 "at_cap": check and v >= p.max_sector_weight - opt.AT_CAP} for sec, v in s["sectors"].items()]
    exposure += [{"as_of": day, "portfolio": name, "kind": "group", "name": g, "label": (labels or {}).get(g),
                  "weight": v, "at_cap": check and v >= p.max_group_weight - opt.AT_CAP}
                 for g, v in s["groups"].items()]
    return {"models.cse_lab_portfolio": [port], "models.cse_lab_weight": weights, "models.cse_lab_exposure": exposure}


def market_row(day: dt.date, summary: dict, weekly: dict) -> dict:
    """The ASPI as a reference (new in 1.1.0): beta 1, so E[R] = r_f + premium; volatility from its weekly returns over
    the same weeks (sample standard deviation x sqrt 52)."""
    first, last = summary["first_week"].isoformat(), summary["last_week"].isoformat()
    m = np.array([v for w, v in sorted(weekly.get(ASPI, {}).items()) if first <= w <= last])
    vol = float(np.std(m, ddof=1) * np.sqrt(52)) if len(m) > 1 else None
    er = summary["risk_free"] + summary["equity_risk_premium"]
    return {"as_of": day, "portfolio": "market", "family": "market", "names_target": None, "status": "ok",
            "message": "the ASPI (a price index), as a reference: beta 1 by definition", "formed_on": day,
            "n_names": None, "expected_return": er, "volatility": vol,
            "sharpe": (er - summary["risk_free"]) / vol if vol else None, "tracking_error": None, "weight_sum": None,
            "min_weight": None, "max_over_cap": None, "max_sector_over": None, "max_group_over": None,
            "constraints_ok": None, "binding": None}


class FewerNames:
    """The versions with K names, along the dates: what each holds, and when it was set."""

    def __init__(self, spec: dict, sessions: list[str], max_weight: float):
        self.spec, self.sessions, self.max_weight = spec, sessions, max_weight
        self.state: dict[str, dict] = {}         # portfolio -> {"names", "weights", "formed_on"}

    def snapshot(self) -> dict:
        return {k: {"names": v["names"], "weights": v["weights"], "formed_on": v["formed_on"].isoformat()}
                for k, v in sorted(self.state.items())}

    def restore(self, rows: list[dict], weights: list[dict]) -> None:
        """The state after a reused date, from its stored rows."""
        by = defaultdict(dict)
        for w in weights:
            by[w["portfolio"]][w["symbol"]] = w["weight"]
        for r in rows:
            if r["family"] == "fewer_names" and r["status"] == "ok" and r["portfolio"] in by:
                self.state[r["portfolio"]] = {"names": sorted(by[r["portfolio"]]), "weights": by[r["portfolio"]],
                                              "formed_on": r["formed_on"]}

    def rows(self, day: dt.date, p: opt.Problem, full: dict[str, np.ndarray] | None, form: bool,
             labels: dict) -> tuple[dict, list[str]]:
        """Form the portfolios (when `form`) and return the rows of each one in force at `day`."""
        out: dict[str, list[dict]] = defaultdict(list)
        notes = []
        idx = {s: i for i, s in enumerate(p.symbols)}
        for k in self.spec["sizes"]:
            cap, floor = opt.retail_cap(k, self.max_weight), opt.retail_floor(k)
            chosen: dict[str, list[str]] = {}
            for kind in self.spec["kinds"]:
                name = f"{kind}_{k}"
                prev = self.state.get(name)
                if form and full is not None:
                    source = "min_variance" if kind == "equal_weight" else kind
                    if source in chosen:
                        names = chosen[source]
                    else:
                        ranked = opt.ranking(full[source], p.symbols)
                        prev_names = (self.state.get(f"{source}_{k}") or {}).get("names")
                        names = opt.retail_names(ranked, k, prev_names, self.spec["buffer"])
                        chosen[source] = names
                    try:
                        if len(names) < k:
                            raise opt.Infeasible(f"the full portfolio holds only {len(names)} names")
                        sub = opt.subproblem(p, [idx[s] for s in names], cap)     # in ranking order
                        w = opt.solve_retail(kind, sub, floor)
                        weights = {s: float(x) for s, x in zip(names, w) if x > 0}
                        self.state[name] = {"names": sorted(weights), "weights": weights, "formed_on": day}
                    except opt.Infeasible as exc:
                        notes.append(f"{name}: {exc}")
                        if prev is None:
                            out["models.cse_lab_portfolio"].append(not_formed(day, name, k, str(exc)))
                            continue
                elif prev is None:
                    out["models.cse_lab_portfolio"].append(not_formed(day, name, k, "not formed yet"))
                    continue
                st = self.state[name]
                missing = [s for s in st["names"] if s not in idx]
                message = None if st["formed_on"] == day else f"weights set on {st['formed_on']}"
                if missing:
                    out["models.cse_lab_portfolio"].append({
                        **not_formed(day, name, k, f"{len(missing)} of its names are not in today's universe; "
                                                   f"weights set on {st['formed_on']}"),
                        "status": "ok", "formed_on": st["formed_on"], "n_names": len(st["names"])})
                    out["models.cse_lab_weight"] += [
                        {"as_of": day, "portfolio": name, "symbol": s, "weight": st["weights"][s],
                         "risk_contribution": None, "cap": None, "sector": None, "group_key": None,
                         "expected_return": None, "at_cap": False} for s in st["names"]]
                    continue
                ids = [idx[s] for s in st["names"]]
                sub = opt.subproblem(p, ids, cap)
                w = np.array([st["weights"][s] for s in st["names"]])
                te = None
                if full is not None:            # against the full portfolio of the same kind, as at this date
                    wide = np.zeros(len(p.symbols))
                    wide[ids] = w
                    te = opt.tracking_error(wide, full[kind], p.cov)
                rows = portfolio_rows(day, name, "fewer_names", w, sub, k=k, formed_on=st["formed_on"],
                                      floor=None if kind == "equal_weight" else floor,
                                      check=kind != "equal_weight", labels=labels, message=message)
                rows["models.cse_lab_portfolio"][0]["tracking_error"] = te
                for t, r in rows.items():
                    out[t] += r
        return out, notes


def not_formed(day: dt.date, name: str, k: int, message: str) -> dict:
    return {"as_of": day, "portfolio": name, "family": "fewer_names", "names_target": k, "status": "not_formed",
            "message": message, "formed_on": None, "n_names": None, "expected_return": None, "volatility": None,
            "sharpe": None, "tracking_error": None, "weight_sum": None, "min_weight": None, "max_over_cap": None,
            "max_sector_over": None, "max_group_over": None, "constraints_ok": None, "binding": None}


def compute_date(summary: dict, rows: list[dict], weekly: dict, cfg: dict, p: dict, fewer: FewerNames | None,
                 form: bool) -> dict[str, list[dict]]:
    day = summary["as_of"]
    out: dict[str, list[dict]] = defaultdict(list)
    labels = {r["group_key"]: r["group_name"] for r in rows}
    prob, _ = problem_of(summary, rows, weekly, cfg)
    out["models.cse_lab_cap"] = [{"as_of": day, "symbol": s, "cap": c, "liquidity_cap": lc}
                                 for s, c, lc in zip(prob.symbols, prob.caps, prob.liq_caps)]
    status, message, full = "ok", f"{len(prob.symbols)} stocks, {summary['history_weeks']} weekly returns", None
    try:
        full = opt.solve_full(prob)
    except opt.Infeasible as exc:
        status, message = "infeasible", str(exc)
    if full is not None:
        for name, w in full.items():
            for t, r in portfolio_rows(day, name, "full", w, prob, check=name != "equal_weight",
                                       labels=labels).items():
                out[t] += r
        out["models.cse_lab_frontier"] = [{"as_of": day, "point": i, "expected_return": f["er"],
                                           "volatility": f["vol"]}
                                          for i, f in enumerate(opt.frontier(prob, int(p["frontier_points"])))]
    if p.get("market_row"):
        out["models.cse_lab_portfolio"].append(market_row(day, summary, weekly))
    if fewer is not None:
        rows_k, notes = fewer.rows(day, prob, full, form and full is not None, labels)
        for t, r in rows_k.items():
            out[t] += r
        if notes:
            message += "; " + "; ".join(notes)
    out["models.cse_lab_summary"] = [{"as_of": day, "status": status, "message": message,
                                      "preview": summary["preview"], "n_universe": len(prob.symbols),
                                      "notional_lkr": cfg["notional_lkr"]}]
    return out


def compute(inputs, as_of):
    p = inputs.params
    out: dict[str, list[dict]] = {t: [] for t in OUTPUTS}
    size = notional(inputs, p, as_of)
    if size is None:                 # version 1.0.0 needs the owner's portfolio size
        return out
    cfg = {k: p[k] for k in ("max_weight", "max_sector_weight", "max_group_weight", "participation",
                             "days_to_build")}
    cfg["notional_lkr"] = size
    if cfg["max_group_weight"] is None:
        cfg.pop("max_group_weight")
    summaries, estimates, weekly = risk_inputs(inputs, as_of)
    stored = stored_outputs(inputs, as_of)
    sessions = calendar(inputs, as_of, excluded_sessions(inputs))
    spec = p.get("fewer_names")
    fewer = FewerNames(spec, sessions, cfg["max_weight"]) if spec else None
    for summary in summaries:
        day = summary["as_of"]
        rows = estimates.get(day, [])
        if not rows:
            out["models.cse_lab_summary"].append({
                "as_of": day, "status": "waiting", "message": summary["message"], "preview": False, "n_universe": 0,
                "notional_lkr": size, "inputs_sha256": fingerprint(summary, [], None, {"params": p})})
            continue
        preview = summary["preview"]
        use_fewer = fewer is not None and not preview
        form = use_fewer and (not fewer.state or is_scheduled(day.isoformat(), sessions, spec["rebalance_months"]))
        symbols = [r["symbol"] for r in rows]
        R = returns_window(summary, symbols, weekly)
        key = fingerprint(summary, rows, R, {"params": p, "notional": size, "form": form,
                                             "fewer": fewer.snapshot() if use_fewer else None})
        old = stored["models.cse_lab_summary"].get(day)
        if old and old[0]["inputs_sha256"] == key:
            for t in OUTPUTS:
                out[t] += [dict(r) for r in stored[t].get(day, [])]
            if use_fewer:
                fewer.restore(stored["models.cse_lab_portfolio"].get(day, []), stored["models.cse_lab_weight"].get(day, []))
            continue
        rows_d = compute_date(summary, rows, weekly, cfg, p, fewer if use_fewer else None, form)
        rows_d["models.cse_lab_summary"][0]["inputs_sha256"] = key
        for t in OUTPUTS:
            out[t] += rows_d.get(t, [])
    return out
