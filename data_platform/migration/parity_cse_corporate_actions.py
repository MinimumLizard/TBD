"""Parity for CSE corporate actions and total returns, against the old terminal's own output and its own code.

    python -m data_platform.migration.parity cse_corporate_actions --old-code <CSE clone> \\
        --report docs/migration/parity-cse-corporate-actions.json

On the migrated facts (cse.company_announcements, cse.announcement_details, the history migration's tables), the
two models run in memory, with the old repo's own review file. Then:

  1. every row of the old data/history/corporate_actions.csv, every column, as the CSV writes it (exact text);
  2. the old code itself (cse/corpactions.py load_records + parse, imported from the clone) on the old files: every
     row, every column. The old CSV is append-only and keeps the first version of a row, so a row first written by
     an earlier version of the old code can differ from what the old code writes today; (1) reports each such
     note as "explained" only when the new note is the old one plus a clause the later code added;
  3. the actions in use (old effective()) and the rows awaiting confirmation (old pending_review());
  4. total returns: the old build_tris (cse/estimates.py) on the old prices.csv and those actions, every share it
     covered and every traded close, to 1e-9; 2026-10-05 is left out on the new side (the old tool never had it);
  5. (3) and (4) again with an illustrative review file built from the old rows (confirming every row that can be
     confirmed as parsed, rejecting a few), so the review path and the rights-issue formula are compared too. It is
     built in memory, written nowhere, and the database is rolled back.

The report holds counts and differences only, never data rows (the repository is public).
"""
from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path

import yaml

from ..jobs import reviews as reviews_job
from .parity import _keyed, compare, old_code, run_chain

MISSED_SESSION = "2026-10-05"
NAMES = ["cse_corporate_actions", "cse_total_returns"]
CSV_COLS = ["symbol", "type", "ex_date", "amount_per_share", "ratio_new", "ratio_held", "factor",
            "subscription_price", "status", "note", "source_url"]
NEW_COL = {"type": "action_type"}
LATER_CLAUSE = re.compile(r"; terms in announcement \d+$")


def _purge_old_modules() -> None:
    for mod in [m for m in sys.modules if m.split(".")[0] in ("cse", "sklearn")]:
        del sys.modules[mod]


def _sklearn_stub() -> None:
    """cse/estimates.py imports scikit-learn's LedoitWolf for the covariance step, which build_tris never uses; this
    project does not install scikit-learn, so an empty stand-in lets the module (and the real build_tris) import."""
    pkg, cov = types.ModuleType("sklearn"), types.ModuleType("sklearn.covariance")
    cov.LedoitWolf = None
    sys.modules["sklearn"], sys.modules["sklearn.covariance"] = pkg, cov


def _new_csv_row(r: dict, fmt) -> dict:
    """A model row as the old CSV writer would have written it."""
    out = {c: fmt(r[NEW_COL.get(c, c)]) for c in CSV_COLS}
    out["ex_date"] = str(r["ex_date"] or "")
    return out


def _text_compare(name: str, old: dict, new: dict, cols: list[str], explained_note=None) -> dict:
    missing = [k for k in old if k not in new]
    extra = [k for k in new if k not in old]
    differ, notes_exact, notes_explained, notes_unexplained = 0, 0, 0, 0
    for k in old:
        if k not in new:
            continue
        differ += sum(1 for c in cols if c != "note" and old[k][c] != new[k][c])
        if "note" in cols:
            a, b = old[k]["note"], new[k]["note"]
            if a == b:
                notes_exact += 1
            elif explained_note and explained_note(a, b):
                notes_explained += 1
            else:
                notes_unexplained += 1
    return {"table": name, "old_rows": len(old), "new_rows": len(new), "missing_in_new": len(missing),
            "extra_in_new": len(extra), "values_differ": differ, "notes_exact": notes_exact,
            "notes_explained": notes_explained, "notes_unexplained": notes_unexplained,
            "ok": not missing and not extra and not differ and not notes_unexplained}


def _explained(old_note: str, new_note: str) -> bool:
    """The note an earlier version of the old code wrote, which the later code extends by one clause."""
    return bool(LATER_CLAUSE.search(new_note)) and LATER_CLAUSE.sub("", new_note) == old_note


def _used_compare(name: str, old_eff: list[dict], new_used: list[dict], fmt) -> dict:
    old = {r["id"]: {c: fmt(r[c]) if c != "ex_date" else str(r["ex_date"]) for c in CSV_COLS} for r in old_eff}
    new = {r["action_id"]: {c: fmt(r[NEW_COL.get(c, c)]) if c != "ex_date" else str(r["ex_date"])
                            for c in CSV_COLS} for r in new_used}
    return _text_compare(name, old, new, CSV_COLS, _explained)


def _tr_compare(name: str, old_tris: dict, new_rows: list[dict]) -> dict:
    old = {}
    for sym, df in old_tris.items():
        prev = None
        for date, r in df.iterrows():
            close_ = float(r["close"])
            old[(sym, date)] = {"close": close_, "total_return": None if r["ret"] != r["ret"] else float(r["ret"]),
                                "tri": float(r["tri"]), "events": r["events"],
                                "price_return": None if prev is None else close_ / prev - 1}
            prev = close_
    symbols = set(old_tris)
    new = {k: v for k, v in _keyed(new_rows, ["symbol", "session_date"]).items() if k[0] in symbols}
    out = compare(name, old, new, ["close", "total_return", "tri", "events", "price_return"])
    out["shares"] = len(symbols)
    out["shares_only_in_new"] = len({r["symbol"] for r in new_rows} - symbols)
    out["sessions_with_actions"] = sum(1 for v in old.values() if v["events"])
    return out


def illustrative_review(old_rows: list[dict], pending: list[dict]) -> tuple[dict, list]:
    """Confirm every pending row that is complete as parsed; give a rights issue without a price a stand-in price
    of 1 rupee, so the rights formula runs; reject the first three confirmed dividends. For the comparison only."""
    confirm: dict[str, dict] = {}
    for r in pending:
        if not r["ex_date"]:
            continue
        need = {"cash_dividend": ["amount_per_share"], "scrip": ["factor"], "subdivision": ["factor"],
                "rights": ["ratio_new", "ratio_held"]}.get(r["type"], ["?"])
        if all(r.get(k) not in (None, "") for k in need):
            confirm[r["id"]] = {} if r["type"] != "rights" or r["subscription_price"] else {"subscription_price": 1.0}
    reject = [r["id"] for r in old_rows if r["type"] == "cash_dividend" and r["status"] == "confirmed"][:3]
    return confirm, reject


def _old_side(load, root: Path, review: tuple[dict, set] | None):
    corpactions, storage, metrics, estimates = (load("cse.corpactions"), load("cse.storage"), load("cse.metrics"),
                                                load("cse.estimates"))
    csv_rows = storage.read_rows(root / "data" / "history" / "corporate_actions.csv")
    review = review or corpactions.load_reviews(root / "config" / "corporate_actions_review.yaml")
    eff = corpactions.effective(csv_rows, review)
    pending = corpactions.pending_review(csv_rows, review)
    cfg = yaml.safe_load((root / "config" / "portfolio.yaml").read_text())
    prices = metrics.load_prices(root / "data" / "history" / "prices.csv")
    # the old lab's latest_securities (cse/lab.py; that module needs the optimiser, so it is not imported)
    raw = root / "data" / "raw"
    latest = sorted(p for p in raw.iterdir() if (p / "allSecurityCode.json").exists())[-1]
    models = load("cse.models")
    securities = models.validate(models.SecurityList, json.loads((latest / "allSecurityCode.json").read_bytes()),
                                 "allSecurityCode").root
    equities = [s.symbol for s in securities if s.symbol.endswith((".N0000", ".X0000"))]
    try:
        tris, error = estimates.build_tris(prices, eff, equities, cfg["dividend_withholding"],
                                           cfg["history_adjusted"]), None
    except load("cse.returns").AdjustmentMismatch as exc:
        tris, error = {}, str(exc)
    return csv_rows, eff, pending, tris, error


def _new_side(conn):
    try:
        new = run_chain(conn, NAMES, {"cse_total_returns": {"exclude_sessions": [MISSED_SESSION]}})
        return new, None
    except Exception as exc:  # noqa: BLE001 - an AdjustmentMismatch on both sides is parity, not failure
        conn.rollback()
        return None, f"{type(exc).__name__}: {exc}"


def ca_parity(conn, old_code_dir: Path) -> dict:
    root = Path(old_code_dir)
    review_file = root / "config" / "corporate_actions_review.yaml"
    reviews_job.sync(conn, review_file, code_version="parity", commit=False)
    checks = []
    _purge_old_modules()
    _sklearn_stub()
    try:
        with old_code(root) as load:
            corpactions, storage, fetch = load("cse.corpactions"), load("cse.storage"), load("cse.fetch")
            fmt = storage.fmt
            paths = fetch.Paths(root)
            code_rows = corpactions.parse(corpactions.load_records(paths), corpactions.share_classes(paths),
                                          corpactions.shares_outstanding(paths))
            csv_rows, eff, pending, tris, old_error = _old_side(load, root, None)

            new, new_error = _new_side(conn)
            if new is None:
                raise RuntimeError(f"the models failed: {new_error}")
            actions = new["models.cse_corporate_action"]
            new_csv = {(r["action_id"],): _new_csv_row(r, fmt) for r in actions}
            old_csv = {(r["id"],): {c: r[c] for c in CSV_COLS} for r in csv_rows}
            checks.append(_text_compare("cse_corporate_actions: old corporate_actions.csv", old_csv, new_csv,
                                        CSV_COLS, _explained))
            first = {}
            for r in code_rows:
                first.setdefault((r["id"],), {c: fmt(r.get(c)) for c in CSV_COLS})
            checks.append(_text_compare("cse_corporate_actions: old code (load_records + parse)", first, new_csv,
                                        CSV_COLS))
            checks.append(_used_compare("cse_corporate_actions: actions in use (old effective())", eff,
                                        new["models.cse_corporate_action_used"], fmt))
            old_pending = {(r["id"],): {} for r in pending}
            new_pending = {(r["action_id"],): {} for r in actions if r["use_status"] == "awaiting_confirmation"}
            checks.append(compare("cse_corporate_actions: awaiting confirmation (old pending_review())",
                                  old_pending, new_pending, []))
            checks.append(_tr_compare("cse_total_returns: old build_tris", tris, new["models.cse_total_return"]))
            checks[-1]["old_error"], checks[-1]["ok"] = old_error, checks[-1]["ok"] and old_error is None

            # 5. an illustrative review, applied on both sides
            confirm, reject = illustrative_review(csv_rows, pending)
            reviews_job.store(conn, confirm, reject, "illustrative", review_file, "parity", commit=False)
            _, eff2, pending2, tris2, old_error2 = _old_side(load, root, (confirm, set(reject)))
            new2, new_error2 = _new_side(conn)
            both_refused = old_error2 is not None and new_error2 is not None and \
                old_error2.split(":")[0] in new_error2
            if new2 is not None:
                used = _used_compare("illustrative review: actions in use", eff2,
                                     new2["models.cse_corporate_action_used"], fmt)
                used["confirmed"], used["rejected"] = len(confirm), len(reject)
                used["rights_in_use"] = sum(1 for r in eff2 if r["type"] == "rights")
                checks.append(used)
                awaiting = {(r["action_id"],): {} for r in new2["models.cse_corporate_action"]
                            if r["use_status"] == "awaiting_confirmation"}
                checks.append(compare("illustrative review: awaiting confirmation", {(r["id"],): {} for r in pending2},
                                      awaiting, []))
                tr = _tr_compare("illustrative review: total returns", tris2, new2["models.cse_total_return"])
                tr["old_error"], tr["ok"] = old_error2, tr["ok"] and old_error2 is None
                checks.append(tr)
            else:
                checks.append({"table": "illustrative review", "old_error": old_error2, "new_error": new_error2,
                               "ok": both_refused})
    finally:
        _purge_old_modules()
    for c in checks:
        c.pop("examples", None)             # counts only: the repository is public
    return {"checks": checks, "ok": all(c["ok"] for c in checks), "old_code_compared": True,
            "excluded_sessions_new_side": [MISSED_SESSION]}

