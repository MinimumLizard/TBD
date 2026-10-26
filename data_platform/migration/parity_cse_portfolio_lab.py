"""Parity for the portfolio lab (risk estimates, model portfolios, the record), against the old terminal's own code
and its stored outputs.

    python -m data_platform.migration.parity cse_portfolio_lab --old-code <CSE clone> \\
        --report docs/migration/parity-cse-portfolio-lab.json

On the migrated facts, with the old repo's own inputs stored in memory and rolled back afterwards (its corporate-action
confirmations, ownership aliases and parents, sector assignments, and the personal settings the lab needs: the
conflict-of-interest list from config/universe.yaml and the portfolio size from config/portfolio.yaml), the models
run in memory, version 1.0.0, with 2026-10-05 left out (the old terminal never had that session). Then:

  1. for every session the old terminal kept (9), the OLD code (cse/lab.py run(), dry run, imported from the
     read-only clone) on a scratch copy of the old repo's layout cut at that session, as its daily job saw it: the
     universe and every reason, each share's estimates and caps, the weeks, shrinkage and risk-free rate, the
     ownership groups and their names, every portfolio (weights, risk contributions, caps, sectors, expected return,
     sector and group totals, expected return, volatility, Sharpe, the constraint report) and the frontier;
  2. the JSON files the old lab stored (data/lab/<session>.json, 8 sessions, and latest.json), the same fields. The
     file of 2026-10-02 predates the ownership-group cap (series v0-52w), so it is compared with the model run
     without that cap; and two stored risk-parity solutions differ from the old code's own rerun at the solver's
     tolerance (see TOLERANCE);
  3. the record: every row of the old record/nav.csv, holdings.csv and trades.csv, as the old CSV writer formats
     them: series v1-52w-grp20 from the model's record, and v0-52w (one session, 2026-10-07) from the record
     started that day on the portfolios without the group cap, as the old tool did;
  4. docs/plan-retail-features.md §6: the versions with fewer names on the 2026-10-15 inputs, against the numbers
     that table states (rounded as it rounds them) and against the research script's own calculation.

The report holds counts and differences only, never data rows (the repository is public, and the old personal
settings are not to be published).
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml

from ..jobs import reviews as reviews_job
from ..models import registry
from ..models._lib import cse_optimize as opt
from ..models._lib import cse_record as rec
from ..models.cse_lab_record import compute as record_model
from ..models.cse_portfolio_lab import compute as lab_model
from ..models.framework import Inputs, output_owners
from .parity import old_code, run_chain
from .parity_cse_dealings import old_aliases

MISSED_SESSION = "2026-10-05"
NAMES = ["cse_corporate_actions", "cse_total_returns", "cse_ownership", "cse_risk_estimates", "cse_portfolio_lab",
         "cse_lab_record"]
EXCLUDE = {n: {"exclude_sessions": [MISSED_SESSION]} for n in ("cse_total_returns", "cse_risk_estimates",
                                                                 "cse_portfolio_lab", "cse_lab_record")}
TOL = 1e-9
# Risk parity is solved through an exponential cone; Clarabel stops at its tolerance, and the old tool's own stored
# runs on identical inputs (2026-10-09 and 2026-10-12 against 2026-10-13: the same weeks, universe and estimates)
# differ by up to 3.3e-6 in a weight. Those two stored files are compared within this, risk parity only.
RISK_PARITY_STORED_TOL = 1e-5
RISK_PARITY_RERUN_SESSIONS = ("2026-10-09", "2026-10-12")
V0_SERIES = "v0-52w"
SKIP_KEYS = {"generated_utc", "series", "config", "needs_review", "actions_used", "record_status", "record_written",
             "trade_lists", "message", "labels"}
# docs/plan-retail-features.md §6, session 2026-10-15 (rounded as the table rounds them): names -> (volatility %,
# Sharpe, tracking error %) for maximum Sharpe, and (volatility %, tracking error %) for minimum variance.
PLAN_TABLE = {
    "max_sharpe": {"full": (20.5, 0.533, None), 25: (20.2, 0.529, 2.4), 20: (19.7, 0.521, 4.3), 15: (20.0, 0.513, 5.5),
                   12: (20.4, 0.507, 6.3), 10: (20.7, 0.499, 7.3), 8: (22.4, 0.486, 9.2), 6: (28.8, 0.430, 17.2),
                   5: None},
    "min_variance": {"full": (11.1, None, None), 25: (11.1, None, 1.0), 20: (11.2, None, 1.6), 15: (11.4, None, 2.6),
                     12: (11.5, None, 3.5), 10: (11.9, None, 4.7), 8: (12.4, None, 6.1), 6: (13.4, None, 7.9),
                     5: (14.2, None, 9.3)},
}
PLAN_FULL_NAMES = {"max_sharpe": 37, "min_variance": 31}


def _purge_old_modules() -> None:
    for mod in [m for m in sys.modules if m.split(".")[0] == "cse"]:
        del sys.modules[mod]


def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat()[:10] if hasattr(v, "isoformat") else str(v)[:10]


# --- the old repo's inputs ---------------------------------------------------------------------------------------

def private_settings(repo: Path) -> dict:
    """The old personal settings the lab needs (kept in memory only; never written to this repository)."""
    universe = yaml.safe_load((repo / "config" / "universe.yaml").read_text()) or {}
    portfolio = yaml.safe_load((repo / "config" / "portfolio.yaml").read_text()) or {}
    return {"excluded": sorted(set(universe.get("excluded") or [])),
            "portfolio_size_lkr": portfolio["portfolio_size_lkr"]}


def store_old_inputs(conn, repo: Path) -> None:
    """Every owner input the lab reads, as the old repo had it, stored without committing (the caller rolls back)."""
    from psycopg.types.json import Jsonb

    reviews_job.sync(conn, repo / "config" / "corporate_actions_review.yaml", code_version="parity", commit=False)
    reviews_job.store_ownership(conn, {"aliases": {}, "parents": {}}, "parity", old_aliases(repo), "parity-old-repo",
                                "parity", commit=False)
    reviews_job.sync_sector_overrides(conn, repo / "config" / "sector_overrides.yaml", code_version="parity",
                                      commit=False)
    conn.execute("insert into cse.lab_private_settings (file_sha256, settings, code_version) values (%s, %s, %s)",
                 ("parity-old-repo", Jsonb(private_settings(repo)), "parity"))


# --- the old side ------------------------------------------------------------------------------------------------

def old_sessions(repo: Path) -> list[str]:
    return sorted(p.name for p in (repo / "data" / "raw").iterdir()
                  if p.is_dir() and p.name[:2] == "20" and (p / "tradeSummary.json").exists())


def _cut_csv(src: Path, dst: Path, session: str) -> None:
    with src.open(newline="") as f, dst.open("w", newline="") as g:
        rows = csv.reader(f)
        w = csv.writer(g, lineterminator="\n")
        header = next(rows)
        w.writerow(header)
        i = header.index("date")
        w.writerows(r for r in rows if r[i] <= session)


def scratch_root(repo: Path, session: str, base: Path, config_override: dict | None = None) -> Path:
    """The old repo's layout as its daily job saw it after `session`: links to the clone's folders (read only), the
    price and index files cut at the session, a copy of its configuration and an empty record (the dry run writes
    nothing; the old code's outputs go to a scratch folder, never into the clone)."""
    root = base / (session + ("-v0" if config_override else ""))
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    for p in (repo / "data" / "raw").iterdir():
        if p.name[:2] == "20" and p.name <= session:
            os.symlink(p, raw / p.name)
    hist = root / "data" / "history"
    hist.mkdir()
    for f in ("prices.csv", "indices.csv"):
        _cut_csv(repo / "data" / "history" / f, hist / f, session)
    os.symlink(repo / "data" / "history" / "corporate_actions.csv", hist / "corporate_actions.csv")
    os.symlink(repo / "data" / "ownership", root / "data" / "ownership")
    shutil.copytree(repo / "config", root / "config")
    if config_override is not None:
        p = root / "config" / "portfolio.yaml"
        cfg = yaml.safe_load(p.read_text())
        for k, v in config_override.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        p.write_text(yaml.safe_dump(cfg))
    (root / "record").mkdir()
    return root


def old_lab(load, root: Path, session: str, out: Path) -> dict:
    lab = load("cse.lab")
    lab.run(root, dry_run=True, out_dir=out)
    return json.loads((out / f"{session}.json").read_text())


# --- the new side, in the old file's shape -----------------------------------------------------------------------

def _by_date(rows: list[dict], key: str = "as_of") -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(_iso(r[key]), []).append(r)
    return out


def new_lab_json(session: str, out: dict) -> dict:
    """The model outputs for one session, in the old data/lab/<session>.json's shape (the fields both have)."""
    summary = next(r for r in out["models.cse_risk_summary"] if _iso(r["as_of"]) == session)
    lab = next(r for r in out["models.cse_lab_summary"] if _iso(r["as_of"]) == session)
    uni = [r for r in out["models.cse_risk_universe"] if _iso(r["as_of"]) == session]
    est = sorted((r for r in out["models.cse_risk_estimate"] if _iso(r["as_of"]) == session),
                 key=lambda r: r["symbol"])
    caps = {r["symbol"]: r for r in out["models.cse_lab_cap"] if _iso(r["as_of"]) == session}
    res = {"session": session, "market_proxy": summary["market_proxy"],
           "universe": sorted(r["symbol"] for r in uni if r["included"]),
           "dropped": [{"symbol": r["symbol"], "name": r["name"], "reason": r["reason"]}
                       for r in sorted(uni, key=lambda r: r["symbol"]) if not r["included"]],
           "weeks_available": summary["max_weeks_available"]}
    included = set(res["universe"])
    labels = {r["group_key"]: r["group_name"] for r in est}
    groups_of = {r["symbol"]: r["group_key"] for r in est}
    res["group_labels"] = {g: labels.get(g, g) for g in sorted({groups_of.get(s, s) for s in included})} \
        if included else {}
    if summary["preview"]:
        res["preview"] = {"weeks": summary["history_weeks"], "universe": len(est)}
    if est:
        res["stocks"] = [{"symbol": r["symbol"], "sector": r["sector"], "group": r["group_key"],
                          "er": r["expected_return"], "vol": r["volatility"], "beta": r["beta"],
                          "beta_current": r["beta_current"], "beta_lag": r["beta_lag"], "amihud": r["amihud"],
                          "median_turnover": r["median_turnover"], "turnover_source": r["turnover_source"],
                          "cap": caps[r["symbol"]]["cap"], "liq_cap": caps[r["symbol"]]["liquidity_cap"]}
                         for r in est]
        res["weeks"] = [_iso(summary["first_week"]), _iso(summary["last_week"])]
        res["n_weeks"] = summary["history_weeks"]
        res["shrinkage"] = summary["shrinkage"]
        res["rf"] = summary["risk_free"]
    if lab["status"] == "ok":
        ports = {r["portfolio"]: r for r in out["models.cse_lab_portfolio"]
                 if _iso(r["as_of"]) == session and r["family"] == "full"}
        res["portfolios"] = {}
        for name in opt.FULL:
            p = ports[name]
            hold = sorted((w for w in out["models.cse_lab_weight"] if _iso(w["as_of"]) == session
                           and w["portfolio"] == name), key=lambda w: -w["weight"])
            exp = [e for e in out["models.cse_lab_exposure"] if _iso(e["as_of"]) == session and e["portfolio"] == name]
            res["portfolios"][name] = {
                "groups": {e["name"]: e["weight"] for e in sorted(exp, key=lambda e: -e["weight"])
                           if e["kind"] == "group"},
                "name": opt.LABELS[name], "er": p["expected_return"], "vol": p["volatility"], "sharpe": p["sharpe"],
                "holdings": [{"symbol": w["symbol"], "weight": w["weight"], "risk_contribution": w["risk_contribution"],
                              "cap": w["cap"], "sector": w["sector"], "er": w["expected_return"]} for w in hold],
                "sectors": {e["name"]: e["weight"] for e in sorted(exp, key=lambda e: -e["weight"])
                            if e["kind"] == "sector"},
                "n": p["n_names"],
                "constraints": None if name == "equal_weight" else {
                    "sum": p["weight_sum"], "min": p["min_weight"], "max_over_cap": p["max_over_cap"],
                    "max_sector_over": p["max_sector_over"], "max_group_over": p["max_group_over"],
                    "ok": p["constraints_ok"]}}
        res["frontier"] = [{"er": f["expected_return"], "vol": f["volatility"]}
                           for f in sorted((f for f in out["models.cse_lab_frontier"] if _iso(f["as_of"]) == session),
                                           key=lambda f: f["point"])]
    elif lab["status"] == "infeasible":
        res["infeasible"] = lab["message"]
    return res


# --- comparing ---------------------------------------------------------------------------------------------------

class Tally:
    def __init__(self):
        self.values = self.differ = self.missing = self.extra = 0
        self.worst = 0.0
        self.examples: list[str] = []

    def walk(self, old, new, path: str, tol, loose: tuple[str, float] | None = None) -> None:
        if isinstance(old, dict):
            if not isinstance(new, dict):
                self._diff(path, "not a mapping")
                return
            for k in old:
                if k not in new:
                    self.missing += 1
                    self._example(f"{path}/{k} missing")
                    continue
                self.walk(old[k], new[k], f"{path}/{k}", tol, loose)
            for k in new:
                if k not in old:
                    self.extra += 1
                    self._example(f"{path}/{k} extra")
            return
        if isinstance(old, list):
            if not isinstance(new, list) or len(old) != len(new):
                self._diff(path, f"length {len(old)} vs {len(new) if isinstance(new, list) else type(new).__name__}")
                return
            for i, (a, b) in enumerate(zip(old, new)):
                self.walk(a, b, f"{path}[{i}]", tol, loose)
            return
        self.values += 1
        if isinstance(old, (int, float)) and not isinstance(old, bool) and isinstance(new, (int, float)) \
                and not isinstance(new, bool):
            d = abs(float(old) - float(new))
            if math.isnan(d):
                d = 0.0 if math.isnan(float(old)) and math.isnan(float(new)) else math.inf
            self.worst = max(self.worst, d)
            t = loose[1] if loose and loose[0] in path else tol
            if d > t and d > t * max(abs(float(old)), abs(float(new))):
                self._diff(path, f"{old!r} vs {new!r}")
        elif old != new:
            self._diff(path, "text differs")

    def _diff(self, path: str, what: str) -> None:
        self.differ += 1
        self._example(f"{path}: {what}")

    def _example(self, text: str) -> None:
        if len(self.examples) < 5:
            # names of securities may appear in a path; numbers never do (the report is counts only)
            self.examples.append(text.split(":")[0])

    def report(self, name: str, **more) -> dict:
        return {"table": name, "values_compared": self.values, "values_differ": self.differ,
                "missing_in_new": self.missing, "extra_in_new": self.extra, "max_abs_difference": self.worst,
                "ok": not self.differ and not self.missing and not self.extra, **more}


def _comparable(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in SKIP_KEYS and k != "status"}


def compare_lab(name: str, old: dict, new: dict, tol: float = TOL, loose: tuple[str, float] | None = None) -> dict:
    t = Tally()
    t.walk(_comparable(old), _comparable(new), "", tol, loose)
    return t.report(name, old_status=old.get("status"))


# --- the record --------------------------------------------------------------------------------------------------

NAV_COLS = ["date", "series", "portfolio", "nav", "cash", "holdings_value", "note"]
HOLD_COLS = ["date", "series", "portfolio", "symbol", "shares", "price", "value", "weight", "target_weight", "flag"]
TRADE_COLS = ["date", "series", "portfolio", "symbol", "action", "shares", "price", "value", "cost", "reason"]
OLD_ACTION = {rec.INCREASE: "buy", rec.DECREASE: "sell"}   # the old file's words for the two directions


def _fmt(v) -> str:
    """The old CSV writer (cse/storage.py fmt)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return repr(round(v, 8))
    return str(v)


def old_record_text(rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The model's record rows as the old files' rows (text, as the old writer formatted them)."""
    nav = [{"date": _iso(r["session_date"]), "series": r["series"], "portfolio": r["portfolio"], "nav": r["nav"],
            "cash": r["cash"], "holdings_value": r["holdings_value"], "note": r["note"]} for r in rows[record_model.NAV]]
    hold = [{"date": _iso(r["session_date"]), "series": r["series"], "portfolio": r["portfolio"],
             "symbol": r["symbol"], "shares": r["shares"], "price": r["price"], "value": r["value"],
             "weight": r["weight"], "target_weight": r["target_weight"], "flag": "1" if r["outside_band"] else "0"}
            for r in rows[record_model.HOLDING]]
    trades = [{"date": _iso(r["session_date"]), "series": r["series"], "portfolio": r["portfolio"],
               "symbol": r["symbol"], "action": OLD_ACTION.get(r["action"], r["action"]), "shares": r["shares"],
               "price": r["price"], "value": r["value"], "cost": r["cost"], "reason": r["reason"]}
              for r in sorted(rows[record_model.TRADE], key=lambda r: (_iso(r["session_date"]), r["series"],
                                                                        r["seq"]))]
    return {"nav.csv": nav, "holdings.csv": hold, "trades.csv": trades}


def record_check(name: str, path: Path, cols: list[str], key, new_rows: list[dict], series: set[str]) -> dict:
    """The stored CSV's rows of these series against the model's, every column as the old writer formats it."""
    old_rows = [r for r in csv.DictReader(path.open(newline="")) if r["series"] in series]
    old, new = {}, {}
    for rows, out, fmt in ((old_rows, old, str), (new_rows, new, _fmt)):
        seen: dict = {}
        for r in rows:
            k = key(r)
            seen[k] = seen.get(k, 0) + 1
            out[k + (seen[k],)] = {c: fmt(r[c]) if fmt is _fmt else r[c] for c in cols}
    missing = [k for k in old if k not in new]
    extra = [k for k in new if k not in old]
    exact = same_number = differ = 0
    for k in old:
        if k in new:
            for c in cols:
                a, b = old[k][c], new[k][c]
                if a == b:
                    exact += 1
                elif _same_number(a, b):
                    same_number += 1
                else:
                    differ += 1
    return {"table": name, "old_rows": len(old), "new_rows": len(new), "missing_in_new": len(missing),
            "extra_in_new": len(extra), "cells_exact": exact, "cells_same_number_other_text": same_number,
            "values_differ": differ, "ok": not missing and not extra and not differ}


def _same_number(a: str, b: str) -> bool:
    """The old writer printed a whole number computed as 9760573.999999999 as "9760574.0" (it rounded after testing
    for a whole number); the record keeps the rounded number, which prints "9760574". The same number either way."""
    try:
        return float(a) == float(b)
    except ValueError:
        return False


# --- docs/plan-retail-features.md §6 -----------------------------------------------------------------------------

def plan_table_check(session: str, out: dict, cfg: dict, load=None) -> list[dict]:
    """The fewer-names test of plan §6 on the model's inputs for `session`: the K largest names of the full portfolio,
    re-optimised with the per-share cap max(10 %, 1.5/K) and the floor 0.5/K (no buffer: the first formation). The
    numbers must round to the table's; with the old code available, they must also equal the research script's own
    calculation (the old optimiser's problem and constraints)."""
    summary = next(r for r in out["models.cse_risk_summary"] if _iso(r["as_of"]) == session)
    rows = sorted((r for r in out["models.cse_risk_estimate"] if _iso(r["as_of"]) == session), key=lambda r: r["symbol"])
    weekly: dict[str, dict] = {}
    for r in out["models.cse_weekly_return"]:
        weekly.setdefault(r["series"], {})[_iso(r["week_end"])] = r["weekly_return"]
    summary = {**summary, "as_of": dt.date.fromisoformat(session),
               "first_week": dt.date.fromisoformat(_iso(summary["first_week"])),
               "last_week": dt.date.fromisoformat(_iso(summary["last_week"]))}
    prob, _ = lab_model.problem_of(summary, rows, weekly, cfg)
    full = opt.solve_full(prob)
    checks = []
    for kind, table in PLAN_TABLE.items():
        t = Tally()
        w_full = full[kind]
        base = opt.stats(w_full, prob)
        n_full = int((w_full > 1e-6).sum())
        t.walk({"names": PLAN_FULL_NAMES[kind], "vol": table["full"][0]},
               {"names": n_full, "vol": round(base["volatility"] * 100, 1)}, "/full", 1e-12)
        if table["full"][1] is not None:
            t.walk(table["full"][1], round(base["sharpe"], 3), "/full/sharpe", 1e-12)
        for k, expected in table.items():
            if k == "full":
                continue
            cap, floor = opt.retail_cap(k, cfg["max_weight"]), opt.retail_floor(k)
            names = opt.retail_names(opt.ranking(w_full, prob.symbols), k, None, 1.5)
            idx = [prob.symbols.index(s) for s in names]
            try:
                w_k = opt.solve_retail(kind, opt.subproblem(prob, idx, cap), floor)
            except opt.Infeasible:
                t.walk(expected is None, True, f"/{k}/infeasible", 0)
                continue
            w = np.zeros(len(prob.symbols))
            w[idx] = w_k
            s = opt.stats(w, prob)
            got = (round(s["volatility"] * 100, 1), round(s["sharpe"], 3) if expected and expected[1] is not None
                   else None, round(opt.tracking_error(w, w_full, prob.cov) * 100, 1))
            t.walk(list(expected) if expected else None, list(got), f"/{k}", 1e-12)
        checks.append(t.report(f"plan §6 table, {kind}, {session} (rounded as the table)"))
    return checks


# --- the run -----------------------------------------------------------------------------------------------------

def _inputs(conn, name: str, relations: dict, params: dict | None = None):
    manifests = registry.load_all()
    m = manifests[name]
    v = next(x for x in m.versions if x.parity is not None)
    v = v.model_copy(update={"parameters": {**v.parameters, **(params or {})}})
    return Inputs(conn, m, v, output_owners(), relations)


@contextlib.contextmanager
def _scratch():
    base = Path(tempfile.mkdtemp(prefix="cse-lab-parity-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def lab_parity(conn, old_code_dir: Path) -> dict:
    repo = Path(old_code_dir)
    store_old_inputs(conn, repo)
    out = run_chain(conn, NAMES, EXCLUDE)
    relations = {t: "parity_" + t.split(".", 1)[1] for t in out if t != "models.model_stats"}
    sessions = old_sessions(repo)
    checks: list[dict] = []

    # the model without the group cap (the old series v0-52w): the stored 2026-10-02 file and the v0 record
    v0_lab = lab_model.compute(_inputs(conn, "cse_portfolio_lab", relations,
                                       {**EXCLUDE["cse_portfolio_lab"], "max_group_weight": None}), None)
    v0 = {**out, **v0_lab}

    _purge_old_modules()
    try:
        with old_code(repo) as load, _scratch() as base:
            # 1. the old code on the old repo cut at each session
            for s in sessions:
                old = old_lab(load, scratch_root(repo, s, base), s, base / "out" / s)
                checks.append(compare_lab(f"{s}: old code (cse/lab.py) on the old files cut at the session", old,
                                          new_lab_json(s, out)))
            # 4. plan §6 (needs no old code: the model's inputs, the research script's rules)
            cfg = {"max_weight": 0.10, "max_sector_weight": 0.30, "max_group_weight": 0.20, "participation": 0.20,
                   "days_to_build": 10, "notional_lkr": float(private_settings(repo)["portfolio_size_lkr"])}
            checks += plan_table_check("2026-10-15", out, cfg)
    finally:
        _purge_old_modules()

    # 2. the stored JSON files
    lab_dir = repo / "data" / "lab"
    for f in sorted(lab_dir.glob("*.json")):
        stored = json.loads(f.read_text())
        s = stored["session"]
        has_groups = "max_group_weight" in stored["config"]
        new = new_lab_json(s, out if has_groups else v0)
        if not has_groups:      # written before the group cap: it has no group fields
            new.pop("group_labels", None)
            for st in new.get("stocks", []):
                st.pop("group", None)
            for p in new.get("portfolios", {}).values():
                p.pop("groups", None)
                if p.get("constraints"):
                    p["constraints"].pop("max_group_over", None)
        loose = ("/portfolios/risk_parity", RISK_PARITY_STORED_TOL) if s in RISK_PARITY_RERUN_SESSIONS else None
        checks.append(compare_lab(f"stored data/lab/{f.name}" + ("" if has_groups else " (before the group cap)"),
                                  stored, new, loose=loose))

    # 3. the record files
    rows = {t: out[t] for t in record_model.OUTPUTS}
    record_dir = repo / "record"
    old_v0 = {}
    for r in csv.DictReader((record_dir / "holdings.csv").open(newline="")):
        if r["series"] == V0_SERIES and r["portfolio"] == "risk_parity" and float(r["target_weight"]) > 0:
            old_v0[r["symbol"]] = float(r["target_weight"])
    v0_rows, v0_rp_gap = v0_record(conn, v0, relations, old_v0)
    checks.append({"table": "v0-52w risk parity: the stored model weights against the model's own (2026-10-07)",
                   "values_compared": len(old_v0), "max_abs_difference": v0_rp_gap,
                   "ok": v0_rp_gap <= RISK_PARITY_STORED_TOL})
    text = {k: a + b for (k, a), b in zip(old_record_text(rows).items(), old_record_text(v0_rows).values())}
    series = {"v1-52w-grp20", V0_SERIES}
    checks.append(record_check("stored record/nav.csv", record_dir / "nav.csv", NAV_COLS,
                               lambda r: (r["date"], r["series"], r["portfolio"]), text["nav.csv"], series))
    checks.append(record_check("stored record/holdings.csv", record_dir / "holdings.csv", HOLD_COLS,
                               lambda r: (r["date"], r["series"], r["portfolio"], r["symbol"]), text["holdings.csv"],
                               series))
    checks.append(record_check("stored record/trades.csv", record_dir / "trades.csv", TRADE_COLS,
                               lambda r: (r["date"], r["series"], r["portfolio"], r["symbol"], r["action"]),
                               text["trades.csv"], series))
    for c in checks:
        c.pop("examples", None)
    return {"checks": checks, "ok": all(c["ok"] for c in checks), "old_code_compared": True, "sessions": sessions,
            "excluded_sessions_new_side": [MISSED_SESSION],
            "tolerance": {"default": TOL, "risk_parity_stored_2026_10_09_and_12": RISK_PARITY_STORED_TOL}}


def v0_record(conn, v0: dict, relations: dict, stored_risk_parity: dict[str, float]) -> tuple[dict, float]:
    """The old series v0-52w: the record started on 2026-10-07 on the portfolios without the group cap, as the old
    tool did that morning (it changed series the same day). Its risk-parity weights came from a solve that stopped
    at the solver's tolerance up to 1.9e-6 away from today's (the same as the stored files of 2026-10-09 and 12), and
    whole shares turn such a difference into a share more or less; so risk parity's rows are rebuilt from the weights
    the old record stored (8 decimals), which checks the record's own arithmetic exactly, and the gap between the two
    sets of weights is returned and reported."""
    inputs = _inputs(conn, "cse_lab_record", relations, EXCLUDE["cse_lab_record"])
    p = inputs.params
    sessions, aspi, closes, actions = record_model.market_facts(inputs, None, {dt.date.fromisoformat(MISSED_SESSION)})
    targets = {}
    ok = {_iso(r["as_of"]) for r in v0["models.cse_lab_summary"] if r["status"] == "ok" and not r["preview"]}
    for w in v0["models.cse_lab_weight"]:
        d = _iso(w["as_of"])
        if d in ok and w["weight"] > 1e-6:
            targets.setdefault(d, {}).setdefault(w["portfolio"], {})[w["symbol"]] = w["weight"]
    cfg = {k: p[k] for k in ("record_notional_lkr", "cost_per_side", "dividend_withholding", "rebalance_months",
                             "band_relative", "band_absolute", "min_trade_lkr")}
    model_rp = targets["2026-10-07"]["risk_parity"]
    gap = max(abs(stored_risk_parity.get(s, 0.0) - model_rp.get(s, 0.0)) for s in set(model_rp) | set(stored_risk_parity))
    empty = {t: [] for t in record_model.OUTPUTS}
    rows, _ = record_model.advance(empty, ["2026-10-07"], sessions, targets, aspi, closes, actions, cfg, V0_SERIES,
                                   tuple(p["portfolios"]), p["digits"], wait_for_targets=False)
    stored = {"2026-10-07": {**targets["2026-10-07"], "risk_parity": stored_risk_parity}}
    rp, _ = record_model.advance(empty, ["2026-10-07"], sessions, stored, aspi, closes, actions, cfg, V0_SERIES,
                                 tuple(p["portfolios"]), p["digits"], wait_for_targets=False)
    rows = {t: [r for r in rows[t] if r["portfolio"] != "risk_parity"] + [r for r in rp[t]
                                                                          if r["portfolio"] == "risk_parity"]
            for t in record_model.OUTPUTS}
    return rows, gap
