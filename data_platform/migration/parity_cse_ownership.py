"""Parity for CSE ownership and company figures, against the old terminal's own code and its stored CSVs.

    python -m data_platform.migration.parity cse_ownership --old-code <CSE clone> \\
        --report docs/migration/parity-cse-ownership-fundamentals.json

On the migrated facts (the CSE history, the corporate-action facts and the report texts), with the old repo's own
confirmation files stored in memory (rolled back afterwards), for every session the old terminal kept raw files for:

  1. the OLD code (cse/ownership/analyse.py build() and write(), groups.py group_of(), cse/fundamentals.py build(),
     imported from the read-only clone) runs on a scratch copy of the old repo's layout that holds only the sessions
     up to that one (links to the clone's folders, which are only read; prices.csv cut at that session), exactly as
     the old daily job would have seen them on that day;
  2. the new models' code runs as at the same session; holdings, companies, owners, ownership groups, report figures
     and the per-company ratios must agree row for row, column for column (text exactly, numbers to 1e-9);
  3. the model OUTPUT tables at the latest session (what the database stores) are compared with the old code too;
  4. the CSVs the old repo stored at the audited commit are compared, as its CSV writer formats numbers, with the
     session they were written from: data/ownership/*.csv (written on 2026-10-11 from the 2026-10-09 session) and
     data/fundamentals/*.csv (written on 2026-10-15 from that session).

2026-10-05 is left out on the new side for the share prices (the old terminal never had that session).
The report holds counts and differences only, never data rows (the repository is public, and the tables name
private individuals).
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

from ..jobs import reviews as reviews_job
from ..models import registry
from ..models.cse_fundamentals import compute as fc
from ..models.cse_ownership import compute as oc
from ..models.framework import Inputs, output_owners
from ..models._lib import cse_ownership as own
from .parity import close, compare, old_code, run_chain

MISSED_SESSION = "2026-10-05"
OWNERSHIP_CSV_SESSION = "2026-10-09"
FUNDAMENTALS_CSV_SESSION = "2026-10-15"
REPORT_COLS = ["report_id", "code", "period_date", "fye", "shares", "eps", "eps_class", "eps_status", "profit", "unit",
               "eps_line", "nav", "nav_status", "equity", "nav_line", "url"]
LATEST_COLS = ["code", "price", "price_date", "shares", "fye", "nav", "nav_period", "pb", "ttm_profit", "ttm_eps",
               "ttm_to", "ttm_note", "earnings_yield", "pe", "roe", "div_ttm", "dy"]


def _purge_old_modules() -> None:
    for mod in [m for m in sys.modules if m.split(".")[0] == "cse"]:
        del sys.modules[mod]


# --- the old side -----------------------------------------------------------------------------------------------

def old_sessions(repo: Path) -> list[str]:
    return sorted(p.name for p in (repo / "data" / "raw").iterdir()
                  if p.is_dir() and p.name[:2] == "20" and (p / "tradeSummary.json").exists())


def scratch_root(repo: Path, session: str, base: Path) -> Path:
    """The old repo's layout as it stood after `session`: links to the clone's folders (read only), a cut prices.csv,
    and empty folders for the old code's own outputs (written here, never into the clone)."""
    root = base / session
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    for p in (repo / "data" / "raw").iterdir():
        if p.name[:2] == "20" and p.name <= session:
            os.symlink(p, raw / p.name)
    os.symlink(repo / "data" / "raw" / "ownership", raw / "ownership")
    os.symlink(repo / "config", root / "config")
    hist = root / "data" / "history"
    hist.mkdir()
    os.symlink(repo / "data" / "history" / "corporate_actions.csv", hist / "corporate_actions.csv")
    with (repo / "data" / "history" / "prices.csv").open(newline="") as src, (hist / "prices.csv").open("w", newline="") as dst:
        rows = csv.reader(src)
        w = csv.writer(dst, lineterminator="\n")
        header = next(rows)
        w.writerow(header)
        i = header.index("date")
        w.writerows(r for r in rows if r[i] <= session)
    return root


def old_side(load, root: Path) -> dict:
    analyse, groups, fundamentals = load("cse.ownership.analyse"), load("cse.ownership.groups"), load("cse.fundamentals")
    res = analyse.build(root)
    analyse.write(res, root)                       # the holdings.csv the old fundamentals step reads
    g, labels = groups.group_of(root)
    rows, latest = fundamentals.build(root)
    return {"res": res, "groups": g, "labels": labels, "rows": rows, "latest": latest}


# --- comparing --------------------------------------------------------------------------------------------------

def _holdings_keyed(holdings: list[dict]) -> dict:
    out, n = {}, {}
    for h in holdings:
        k = (str(h["report_id"]), h["class"])
        n[k] = n.get(k, 0) + 1
        out[k + (n[k],)] = h
    return out


def build_checks(session: str, old: dict, new_res: dict, new_fund: tuple[list, list]) -> list[dict]:
    o, n = old["res"], new_res
    checks = [
        compare(f"{session} holdings", _holdings_keyed(o["holdings"]), _holdings_keyed(n["holdings"]), own.HOLDING_COLS),
        compare(f"{session} companies", {(k,): v for k, v in o["companies"].items()},
                {(k,): v for k, v in n["companies"].items()}, own.COMPANY_COLS),
        compare(f"{session} owners", {(k,): v for k, v in o["owners"].items()}, {(k,): v for k, v in n["owners"].items()},
                own.OWNER_COLS),
    ]
    new_groups, new_labels, _ = own.group_of(n["companies"])
    checks.append(compare(f"{session} ownership groups", {(k,): {"group": v, "label": old["labels"].get(v)}
                                                          for k, v in old["groups"].items()},
                          {(k,): {"group": v, "label": new_labels.get(v)} for k, v in new_groups.items()},
                          ["group", "label"]))
    rows, latest = new_fund
    checks.append(compare(f"{session} report figures", {(r["report_id"],): r for r in old["rows"]},
                          {(r["report_id"],): r for r in rows}, REPORT_COLS))
    checks.append(compare(f"{session} company ratios", {(r["code"],): r for r in old["latest"]},
                          {(r["code"],): r for r in latest}, LATEST_COLS))
    checks.append({"table": f"{session} graph totals", "ok": all(close(o["graph"][k], n["graph"][k]) for k in
                                                                ("covered_cap", "total_cap", "attributed_value",
                                                                 "listed_passthrough"))
                   and o["graph"]["covered"] == n["graph"]["covered"]})
    return checks


def _iso(v) -> str:
    """A date as text ('' for none): the models hand back dates or ISO text, as the framework accepts both."""
    if v is None or v == "":
        return ""
    return v.isoformat()[:10] if hasattr(v, "isoformat") else str(v)[:10]


def output_checks(session: str, old: dict, outputs: dict) -> list[dict]:
    """The model output tables at the latest session against the old code's rows."""
    hold = {}
    for h in outputs["models.cse_holding"]:
        hold[(str(h["report_id"]), h["share_class"], h["row_no"])] = {
            **h, "report_id": str(h["report_id"]), "class": h["share_class"],
            "period_date": _iso(h["period_date"])}
    detail = {}
    for r in outputs["models.cse_ownership_detail"]:
        if _iso(r["session_date"]) != session:
            continue
        detail[(r["code"],)] = {"code": r["code"], "name": r["name"], "report_id": str(r["report_id"] or ""),
                                "report_status": r["report_status"], "status_N": r["status_n"] or "",
                                "note_N": r["note_n"] or "", "status_X": r["status_x"] or "",
                                "note_X": r["note_x"] or "", "controller_key": r["controller_key"] or "",
                                "control_pct": "" if r["control_pct"] is None else r["control_pct"],
                                "control_level": r["control_level"] or "", "chain": r["chain"] or "",
                                "group": r["group_key"]}
    old_detail = {(k,): {**v, "group": old["groups"][k]} for k, v in old["res"]["companies"].items()}
    figs = {(str(r["report_id"]),): {**r, "report_id": str(r["report_id"]), "url": r["source_url"],
                                      "period_date": _iso(r["period_date"])} for r in outputs["models.cse_report_figures"]}
    ratios = {}
    for r in outputs["models.cse_fundamentals"]:
        if _iso(r["session_date"]) == session:
            ratios[(r["code"],)] = {**r, **{c: _iso(r[c]) for c in ("price_date", "nav_period", "ttm_to")}}
    return [
        compare(f"output models.cse_holding ({session})", _holdings_keyed(old["res"]["holdings"]), hold,
                [c for c in own.HOLDING_COLS]),
        compare(f"output models.cse_ownership_detail ({session})", old_detail, detail,
                ["name", "report_id", "report_status", "status_N", "note_N", "status_X", "note_X", "controller_key",
                 "control_pct", "control_level", "chain", "group"]),
        compare(f"output models.cse_report_figures ({session})", {(r["report_id"],): r for r in old["rows"]}, figs,
                [c for c in REPORT_COLS if c != "report_id"]),
        compare(f"output models.cse_fundamentals ({session})", {(r["code"],): r for r in old["latest"]}, ratios,
                [c for c in LATEST_COLS if c != "code"]),
    ]


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


def csv_check(name: str, path: Path, key, cols: list[str], new_rows: list[dict]) -> dict:
    """The stored CSV against new rows formatted as the old writer did: text equal, or (counted apart) numbers that
    differ only in the last of the 8 decimals the writer kept."""
    old_rows = list(csv.DictReader(path.open(newline="")))
    old, new = {}, {}
    for rows, out in ((old_rows, old), (new_rows, new)):
        seen: dict = {}
        for r in rows:
            k = key(r)
            seen[k] = seen.get(k, 0) + 1
            out[k + (seen[k],)] = r
    missing = [k for k in old if k not in new]
    extra = [k for k in new if k not in old]
    exact = rounding = differ = 0
    for k in old:
        if k not in new:
            continue
        for c in cols:
            a, b = old[k][c], _fmt(new[k][c])
            if a == b:
                exact += 1
                continue
            try:
                fa, fb = float(a), float(b)
                if abs(fa - fb) <= max(1.01e-8, 1e-9 * max(abs(fa), abs(fb))):
                    rounding += 1
                    continue
            except ValueError:
                pass
            differ += 1
    return {"table": name, "old_rows": len(old), "new_rows": len(new), "missing_in_new": len(missing),
            "extra_in_new": len(extra), "cells_exact": exact, "cells_last_decimal": rounding, "values_differ": differ,
            "ok": not missing and not extra and not differ}


# --- the run ----------------------------------------------------------------------------------------------------

def _store_old_confirmations(conn, root: Path) -> None:
    reviews_job.sync(conn, root / "config" / "corporate_actions_review.yaml", code_version="parity", commit=False)
    data = {}
    for f in ("ownership_aliases.yaml", "ownership_parents.yaml"):
        p = root / "config" / f
        data.update(yaml.safe_load(p.read_text()) or {} if p.exists() else {})
    merged = {"aliases": data.get("aliases") or {}, "parents": data.get("parents") or {}}
    reviews_job.store_ownership(conn, {"aliases": {}, "parents": {}}, "parity", merged, "parity-old-repo", "parity",
                                commit=False)


def ownership_parity(conn, old_code_dir: Path) -> dict:
    repo = Path(old_code_dir)
    _store_old_confirmations(conn, repo)
    sessions = old_sessions(repo)
    wanted = {dt.date.fromisoformat(s) for s in sessions}
    # the corporate actions in use (in memory), then the two models' own outputs for the output-table checks
    outputs = run_chain(conn, ["cse_corporate_actions", "cse_ownership", "cse_fundamentals"],
                        {"cse_fundamentals": {"exclude_sessions": [MISSED_SESSION]}},
                        as_of=None)
    manifests, owners_map = registry.load_all(), output_owners()
    relations = {"models.cse_corporate_action_used": "parity_cse_corporate_action_used"}

    def inputs(name, params=None):
        m = manifests[name]
        v = m.current.model_copy(update={"parameters": {**m.current.parameters, **(params or {})}})
        return Inputs(conn, m, v, owners_map, relations)

    new_own = oc.run(inputs("cse_ownership"), None, wanted)
    new_fund = fc.run(inputs("cse_fundamentals", {"exclude_sessions": [MISSED_SESSION]}), None, wanted)
    checks: list[dict] = []
    stored: dict[str, dict] = {}
    _purge_old_modules()
    base = Path(tempfile.mkdtemp(prefix="cse-own-parity-"))
    try:
        with old_code(repo) as load:
            for s in sessions:
                d = dt.date.fromisoformat(s)
                old = old_side(load, scratch_root(repo, s, base))
                checks += build_checks(s, old, new_own[d], new_fund[d])
                if s == sessions[-1]:
                    checks += output_checks(s, old, outputs)
                if s in (OWNERSHIP_CSV_SESSION, FUNDAMENTALS_CSV_SESSION):
                    stored[s] = {"own": new_own[d], "fund": new_fund[d]}
    finally:
        _purge_old_modules()
        shutil.rmtree(base, ignore_errors=True)
    own_dir, fund_dir = repo / "data" / "ownership", repo / "data" / "fundamentals"
    o = stored[OWNERSHIP_CSV_SESSION]["own"]
    checks.append(csv_check(f"stored data/ownership/holdings.csv vs {OWNERSHIP_CSV_SESSION}", own_dir / "holdings.csv",
                            lambda r: (str(r["report_id"]), r["class"]), own.HOLDING_COLS, o["holdings"]))
    checks.append(csv_check(f"stored data/ownership/companies.csv vs {OWNERSHIP_CSV_SESSION}", own_dir / "companies.csv",
                            lambda r: (r["code"],), own.COMPANY_COLS, list(o["companies"].values())))
    checks.append(csv_check(f"stored data/ownership/owners.csv vs {OWNERSHIP_CSV_SESSION}", own_dir / "owners.csv",
                            lambda r: (r["key"],), own.OWNER_COLS, own.owner_rows(o["owners"])))
    rows, latest = stored[FUNDAMENTALS_CSV_SESSION]["fund"]
    checks.append(csv_check(f"stored data/fundamentals/reports.csv vs {FUNDAMENTALS_CSV_SESSION}",
                            fund_dir / "reports.csv", lambda r: (str(r["report_id"]),), REPORT_COLS, rows))
    checks.append(csv_check(f"stored data/fundamentals/latest.csv vs {FUNDAMENTALS_CSV_SESSION}",
                            fund_dir / "latest.csv", lambda r: (r["code"],), LATEST_COLS, latest))
    for c in checks:
        c.pop("examples", None)             # counts only: the repository is public and the rows name people
    return {"checks": checks, "ok": all(c["ok"] for c in checks), "old_code_compared": True,
            "sessions": sessions, "excluded_sessions_new_side": [MISSED_SESSION]}
