"""Parity for directors' dealings and money flows, against the old terminal's own file and its own code.

    python -m data_platform.migration.parity cse_dealings --old-code <CSE clone> \\
        --report docs/migration/parity-cse-dealings-flows.json

On the migrated facts (the dealing notices in cse.announcement_details, the security lists), the two models run in
memory. Then:

  1. cse_dealings against the old data/dealings/dealings.csv: the rows not superseded, written as the old CSV writer
     writes them (old cse/storage.py, imported from the clone; the neutral side labels mapped back to the old file's
     words), must equal the old file byte for byte; and the notices the model marks superseded must be exactly those
     the old code (cse/dealings.py drop_refiled, run on the old raw files) leaves out;
  2. cse_flows against the old code (cse/flows.py build(), imported from the clone) run on the old dealings.csv,
     at the old page's date and at earlier dealing dates (the old file cut at each date, in a temporary folder that
     links to the clone's other data). Compared: every company row the old page shows (purchases, disposals, net,
     the distinct accounts on each side by name, cluster), every account row (key, name, kind, sums, number of
     dealings, net by company), the 150 most recent dealings' fields and flags, the counts and the median lag;
  3. the old code run with and without its aliases file at the latest date: the compared numbers must not change
     (version 1 has no aliases; ownership groups only change the group labels and the "own group" flag, which are
     left out).

The old code runs without its aliases file and ownership groups (patched in memory; the clone is never written).
The report holds counts and differences only, never data rows or names (the repository is public).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from ..models.cse_flows import compute as flows_model
from .parity import old_code, run_chain

NAMES = ["cse_dealings", "cse_flows"]
OLD_SIDE = {"purchase": "buy", "sell": "sell", "disposal": "sell", "other": "other"}
WINDOWS = ("30", "90", "365")


def _purge_old_modules() -> None:
    for mod in [m for m in sys.modules if m.split(".")[0] == "cse"]:
        del sys.modules[mod]


def _check(name: str, old_rows: int, new_rows: int, missing: int, extra: int, differ: int, **more) -> dict:
    return {"table": name, "old_rows": old_rows, "new_rows": new_rows, "missing_in_new": missing,
            "extra_in_new": extra, "values_differ": differ, **more,
            "ok": not missing and not extra and not differ and more.get("ok", True)}


# --- 1. cse_dealings ----------------------------------------------------------------------------------------------

def old_csv_text(dealing: list[dict], filed: dict[str, dict], cols: list[str], serialise) -> str:
    """The counted rows as the old CSV writer writes them, in the old order."""
    rows = []
    for r in sorted((r for r in dealing if r["superseded_by"] is None),
                    key=lambda r: (iso(r["deal_date"]), iso(r["announced_date"]), r["announcement_id"], r["line_no"])):
        f = filed[r["transaction_id"]]
        rows.append({"announcement_id": str(r["announcement_id"]), "announced": iso(r["announced_date"]),
                     "symbol": r["symbol"], "company": r["company"], "director": f["director"],
                     "director_role": f["director_role"], "account_type": r["account_type"], "account": f["account"],
                     "trade_date": iso(r["trade_date"]), "side": OLD_SIDE[r["side"]], "trans_type": f["trans_type"],
                     "quantity": r["quantity"], "price": r["price"], "value": r["value"], "lag_days": r["lag_days"],
                     "url": f["source_url"]})
    return ",".join(cols) + "\n" + serialise(cols, rows)


def iso(d) -> str:
    """A date as the old CSV's text: ISO, or '' when missing (the model hands back dates or ISO strings)."""
    return d.isoformat() if isinstance(d, dt.date) else (d or "")


NUMERIC = ("quantity", "price", "value")


def _csv_compare(name: str, old_text: str, new_text: str) -> dict:
    """Row by row, in order, every column as text. One exception, counted separately: the old writer formatted a
    value from the unrounded product (5200 x 10.2 = 53039.99999999999 -> "53040.0"), so a whole number can read
    "53040.0" in the old file where the stored, rounded number reads "53040"; those cells must be the same number."""
    old, new = list(csv.DictReader(io.StringIO(old_text))), list(csv.DictReader(io.StringIO(new_text)))
    differ = same_number = 0
    for a, b in zip(old, new):
        for c in a:
            if a[c] == b[c]:
                continue
            if c in NUMERIC and a[c] and b[c] and float(a[c]) == float(b[c]):
                same_number += 1
            else:
                differ += 1
    lines = sum(1 for a, b in zip(old_text.splitlines(), new_text.splitlines()) if a == b)
    return _check(name, len(old), len(new), max(0, len(old) - len(new)), max(0, len(new) - len(old)), differ,
                  identical_lines=lines - 1, cells_same_number_other_text=same_number,
                  columns=len(old[0]) if old else 0)


# --- 2. cse_flows -------------------------------------------------------------------------------------------------

def _cut_root(clone: Path, tmp: Path, csv_text: str, day: str | None) -> Path:
    """A folder the old build() reads as its repository: the old dealings.csv cut at `day`, and links to the clone's
    raw data, configuration and ownership tables (read-only)."""
    root = tmp / (day or "all")
    (root / "data" / "dealings").mkdir(parents=True)
    for rel in ("data/raw", "data/ownership", "config"):
        os.symlink(clone / rel, root / rel)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    keep = [r for r in rows if day is None or (r["trade_date"] or r["announced"]) <= day]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(keep)
    (root / "data" / "dealings" / "dealings.csv").write_text(buf.getvalue())
    return root


def _new_side(new: dict, conn) -> tuple[list[dict], dict]:
    """The model's own intermediate rows (accounts per dealing), rebuilt from the in-memory outputs, so the parity can
    compare the names of the accounts on each side, which the published table only counts."""
    dealing = [r for r in new["models.cse_dealing"] if r["superseded_by"] is None]
    for r in dealing:
        for k in ("trade_date", "deal_date", "announced_date"):
            if isinstance(r[k], str):
                r[k] = dt.date.fromisoformat(r[k])
    dealing.sort(key=lambda r: (flows_model._iso(r["deal_date"]), flows_model._iso(r["announced_date"]),
                                r["announcement_id"], r["line_no"]))
    filed = {r["transaction_id"]: r for r in new["models.cse_dealing_as_filed"]}
    lists = flows_model.Lists([dict(r) for r in conn.execute(
        "select session_date, symbol, name from cse.security_list order by session_date, symbol")])
    return flows_model.deals(dealing, filed, lists), filed


def _flows_compare(day: str, old: dict, deals: list[dict], new: dict) -> list[dict]:
    end = dt.date.fromisoformat(day)
    out = []
    by_company = {(iso(r["as_of"]), r["window_days"], r["symbol"]): r for r in new["models.cse_flow_company"]}
    by_actor = {(iso(r["as_of"]), r["window_days"], r["actor_key"]): r for r in new["models.cse_flow_actor"]}
    for w in WINDOWS:
        rows_w = flows_model.window(deals, end, int(w))
        mine = {c["symbol"]: c for c in flows_model.per_company(rows_w)}
        missing = differ = 0
        for c in old["companies"][w]:
            n, t = mine.get(c["symbol"]), by_company.get((day, int(w), c["symbol"]))
            if n is None or t is None:
                missing += 1
                continue
            differ += sum([c["company"] != n["company"] or c["company"] != t["company"], c["buy"] != n["purchases"],
                           c["sell"] != n["disposals"], c["net"] != n["net"], c["buyers"] != n["purchasers"],
                           c["sellers"] != n["disposers"], c["cluster"] != n["cluster"],
                           t["purchase_value"] != c["buy"], t["disposal_value"] != c["sell"],
                           t["net_value"] != c["net"], t["n_purchasers"] != len(c["buyers"]),
                           t["n_disposers"] != len(c["sellers"]), t["cluster"] != c["cluster"]])
        top_old = sorted(abs(c["net"]) for c in old["companies"][w])
        top_new = sorted(abs(c["net"]) for c in sorted(mine.values(), key=lambda c: -abs(c["net"]))[:len(top_old)])
        out.append(_check(f"cse_flows {day} {w} days: companies", len(old["companies"][w]), len(mine), missing, 0,
                          differ, same_top_rows=top_old == top_new, ok=top_old == top_new))
        missing = differ = 0
        for a in old["actors"][w]:
            t = by_actor.get((day, int(w), a["key"]))
            if t is None:
                missing += 1
                continue
            codes = {k: v for k, v in json.loads(t["companies"])}
            differ += sum([t["actor"] != a["name"], t["actor_type"] != a["type"], t["purchase_value"] != a["buy"],
                           t["disposal_value"] != a["sell"], t["net_value"] != a["net"],
                           t["n_transactions"] != a["n"], codes != a["codes"],
                           list(codes) != list(a["codes"])])
        n_new = sum(1 for k in by_actor if k[0] == day and k[1] == int(w))
        top_old = sorted(abs(a["net"]) for a in old["actors"][w])
        top_new = sorted(abs(r["net_value"]) for k, r in by_actor.items() if k[0] == day and k[1] == int(w))
        top_new = sorted(top_new, reverse=True)[:len(top_old)]
        out.append(_check(f"cse_flows {day} {w} days: accounts", len(old["actors"][w]), n_new, missing, 0, differ,
                          same_top_rows=top_old == sorted(top_new), ok=top_old == sorted(top_new)))
    # the 150 most recent dealings (old feed), in the old order, with their flags
    recent = sorted((d for d in deals if d["date"] and d["date"] <= day),
                    key=lambda d: (d["date"], flows_model._iso(d["announced_date"])), reverse=True)[:150]
    flags = {r["transaction_id"]: r for r in new["models.cse_flow_dealing"]}
    differ = 0
    for o, d in zip(old["feed"], recent):
        f = flags[d["transaction_id"]]
        old_flags = {x for x in o["flags"] if x in ("large", "related account")}
        new_flags = {x for x, on in (("large", f["large"]), ("related account", f["related_account"])) if on}
        differ += sum([o["date"] != d["date"], o["announced"] != flows_model._iso(d["announced_date"]),
                       o["symbol"] != d["symbol"], o["company"] != d["company"], o["actor"] != d["actor"],
                       o["actor_type"] != d["actor_type"] or o["actor_type"] != f["actor_type"],
                       o["account_type"] != d["account_type"], OLD_SIDE[d["side"]] != o["side"],
                       o["value"] != d["value"], str(o["lag_days"] or "") != str(d["lag_days"] if d["lag_days"]
                                                                                   is not None else ""),
                       old_flags != new_flags])
    out.append(_check(f"cse_flows {day}: recent dealings and flags", len(old["feed"]), len(recent),
                      max(0, len(old["feed"]) - len(recent)), max(0, len(recent) - len(old["feed"])), differ))
    s = next((r for r in new["models.cse_flow_summary"]
              if iso(r["as_of"]) == day), None)
    differ = 1 if s is None else sum([s["n_dealings"] != old["n_dealings"], s["n_trades"] != old["n_trades"],
                                      s["lag_median"] != old["lag_median"]])
    out.append(_check(f"cse_flows {day}: counts and median lag", 1, int(s is not None), 0, 0, differ))
    out[-1]["old_asof"] = old["asof"]
    out[-1]["ok"] = out[-1]["ok"] and old["asof"] == day
    return out


def _comparable(result: dict) -> dict:
    """What version 1 reproduces from build(): no group labels, no watchlist, no "own group" flag."""
    return {"actors": {w: [{k: v for k, v in a.items() if k != "group"} for a in result["actors"][w]]
                       for w in WINDOWS},
            "companies": {w: [{k: v for k, v in c.items() if k != "watch"} for c in result["companies"][w]]
                          for w in WINDOWS},
            "feed": [{k: (v if k != "flags" else [x for x in v if x in ("large", "related account")])
                      for k, v in f.items() if k != "actor_group_name"} for f in result["feed"]],
            "counts": [result["n_dealings"], result["n_trades"], result["lag_median"]]}


def dealings_parity(conn, old_code_dir: Path, every: int = 20) -> dict:
    root = Path(old_code_dir)
    checks: list[dict] = []
    new = run_chain(conn, NAMES)
    _purge_old_modules()
    try:
        with old_code(root) as load:
            dealings, storage = load("cse.dealings"), load("cse.storage")
            flows, names, groups = load("cse.flows"), load("cse.ownership.names"), load("cse.ownership.groups")

            # 1. the table, as text, and the re-filed notices
            filed = {r["transaction_id"]: r for r in new["models.cse_dealing_as_filed"]}
            new_text = old_csv_text(new["models.cse_dealing"], filed, dealings.COLS, storage._serialise)
            old_text = (root / "data" / "dealings" / "dealings.csv").read_text()
            checks.append(_csv_compare("cse_dealings: old dealings.csv (every row, every column, as text)",
                                        old_text, new_text))
            parsed = []
            for aid, f in dealings.raw_files(root).items():
                try:
                    parsed += dealings.parse(aid, json.loads(f.read_bytes() or b"{}"))
                except json.JSONDecodeError:
                    continue
            kept = {r["announcement_id"] for r in dealings.drop_refiled(parsed)}
            old_dropped = {int(r["announcement_id"]) for r in parsed} - {int(a) for a in kept}
            new_superseded = {r["announcement_id"] for r in new["models.cse_dealing"] if r["superseded_by"]}
            checks.append(_check("cse_dealings: re-filed notices (old drop_refiled)", len(old_dropped),
                                 len(new_superseded), len(old_dropped - new_superseded),
                                 len(new_superseded - old_dropped), 0,
                                 old_transactions=len(parsed), new_transactions=len(new["models.cse_dealing"])))
            checks[-1]["ok"] = checks[-1]["ok"] and len(parsed) == len(new["models.cse_dealing"])

            # 3. the aliases file changes nothing that version 1 compares (at the latest date)
            with_aliases = _comparable(flows.build(root))
            names.load_aliases = lambda path: {}
            groups.group_of = lambda r: ({}, {})
            without = _comparable(flows.build(root))
            checks.append({"table": "old code: with and without its aliases file", "ok": with_aliases == without,
                           "identical": with_aliases == without})

            # 2. flows, at the old page's date and earlier dealing dates
            deals, _ = _new_side(new, conn)
            days = sorted({d["date"] for d in deals if d["date"]})
            picked = sorted(set(days[::every]) | {days[-1]})
            with tempfile.TemporaryDirectory() as tmp:
                for day in picked:
                    cut = _cut_root(root, Path(tmp), old_text, None if day == days[-1] else day)
                    checks.extend(_flows_compare(day, flows.build(cut), deals, new))
    finally:
        _purge_old_modules()
    flow_checks = [c for c in checks if c["table"].startswith("cse_flows")]
    return {"checks": checks, "ok": all(c["ok"] for c in checks), "old_code_compared": True,
            "flows_dates_compared": len({c["table"].split()[1].rstrip(":") for c in flow_checks}),
            "flows_rows_compared": sum(c["old_rows"] for c in flow_checks)}
