"""Migrate the bond history: replay every PDMO original through the new parsers, then reconcile with the old DB.

    python -m data_platform.migration.bonds \\
        --old-db <Nelson-Siegel clone>/data/sgcp.sqlite \\
        --old-history <archive>/bond_db_history.sqlite \\
        --pdmo-archive <archive>/pdmo \\
        --report docs/migration/bonds.json

Inputs are the read-only safety copies made on 2026-10-11 (CHANGELOG): the PDMO originals were re-downloaded
and each matched the SHA-256 the old database recorded when it first parsed the file.

What it does:
  1. Archives the old database file and its full row history (rebuilt from git) as raw objects, so Phase 3's
     parity tests can read exactly what the old pipeline computed.
  2. For each of the old `files` rows: checks the archived original against the old database's fingerprint,
     records it as a re-download, and stores its facts through the live collector's store_file().
  3. Reconciles, table by table, the new "current" views against the old database (see reconcile()).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from ..collectors.pdmo import index
from ..collectors.pdmo.collector import BASE, INDEX_PAGES, KIND_ORDER, store_file
from ..core import db, rawstore, settings as settings_mod
from ..core.http import PoliteClient

LEGACY_SOURCE = "legacy_nelson_siegel"
OLD_COMMIT = "1c33084"


def _d(value) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def archive_legacy_file(conn, store, path: Path, label: str, commit: str = OLD_COMMIT) -> str:
    body = path.read_bytes()
    _, digest = db.record_fetch(
        conn, store, source_id=LEGACY_SOURCE, method="GIT", url=f"git://github.com/MinimumLizard/Nelson-Siegel@{commit}/{label}",
        params={}, http_status=200, body=body, content_type="application/vnd.sqlite3",
        fetched_at=dt.datetime.now(dt.timezone.utc), origin="migration", note=f"old repo file {label}", ext="sqlite")
    return digest


def index_entries(conn, store, http: PoliteClient, today: dt.date) -> dict[str, tuple[index.IndexEntry, int]]:
    """Today's PDMO index pages (archived like any fetch) → {url: (entry, index_year)}: kinds, posted/label dates."""
    out = {}
    for label, path, parse in INDEX_PAGES:
        for year in range(2025, today.year + 1):
            url = BASE + path.format(year=year)
            r = http.get(url)
            db.record_fetch(conn, store, source_id="pdmo", method="GET", url=url, params={}, http_status=r.status,
                            body=r.body, content_type=r.content_type, fetched_at=r.fetched_at, origin="migration",
                            note=f"{label} index {year} (migration)")
            for entry in parse(r.body):
                out.setdefault(entry.url, (entry, year))
    conn.commit()
    return out


def load(conn, store, old_db: Path, pdmo_archive: Path, http: PoliteClient | None, today: dt.date) -> dict:
    old = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    files = [dict(r) for r in old.execute("select * from files")]
    manifest = {r["url"]: r for r in csv.DictReader((pdmo_archive / "manifest.csv").open())}
    by_sha = {p.stem: p for p in (pdmo_archive / "files").iterdir()}
    listed = index_entries(conn, store, http, today) if http else {}

    plan = []
    for f in files:
        entry, year = listed.get(f["url"], (None, None))
        if entry is None:   # no longer listed: rebuild the entry from what the old database recorded
            entry = index.IndexEntry(f["url"], f["file_type"], None, _d(f["posted_date"]))
            year = (_d(f["report_date"]) or dt.date(2025, 12, 1)).year
        plan.append((f, entry, year))
    plan.sort(key=lambda p: (KIND_ORDER[p[1].kind], p[1].posted_date or p[1].label_date or dt.date.min))

    stats = Counter()
    for f, entry, year in plan:
        m = manifest.get(f["url"])
        if m is None or not m["status"].startswith("match"):
            stats["missing_original"] += 1
            continue
        body = by_sha[m["got_sha256"]].read_bytes()
        if rawstore.sha256_of(body) != f["sha256"]:
            raise RuntimeError(f"{f['url']}: archived original does not match the old database's fingerprint")
        fetch_id, digest = db.record_fetch(
            conn, store, source_id="pdmo", method="GET", url=f["url"], params={}, http_status=200, body=body,
            content_type=m["content_type"] or None, fetched_at=dt.datetime.fromisoformat(m["fetched_at_utc"]),
            origin="re-download", note=f"migration: original re-downloaded 2026-10-11, matches old sha256")
        status, added = store_file(conn, entry=entry, index_year=year, fetch_id=fetch_id, sha256=digest,
                                   fetched_at=dt.datetime.fromisoformat(m["fetched_at_utc"]), body=body)
        conn.commit()
        stats[f"parse_{status}"] += 1
        stats["rows_added"] += added
        if entry.kind != f["file_type"]:
            stats["kind_mismatch"] += 1
    return dict(stats)


LEGACY_REFERENCE_COLUMNS = ("isin", "coupon_pct", "maturity_date", "tenor_years", "series_label", "issue_date",
                            "coupon_dates", "first_seen_date", "notes")


def load_legacy_reference(conn, old_db: Path, source_sha256: str) -> dict:
    """Copy the old database's `bonds` table into bonds.legacy_reference (once; repeat runs add nothing) and check
    the copy row for row. bond_identity version 1 starts from it (decision 0015)."""
    old = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    rows = [{c: r[c] for c in LEGACY_REFERENCE_COLUMNS} for r in old.execute("select * from bonds order by isin")]
    added, conflicts = db.insert_facts(
        conn, "bonds.legacy_reference", [{**r, "source_sha256": source_sha256} for r in rows],
        key=("source_sha256", "isin"))
    conn.commit()
    stored = {r["isin"]: r for r in conn.execute(
        "select * from bonds.legacy_reference where source_sha256 = %s", (source_sha256,))}
    differ = [r["isin"] for r in rows if r["isin"] not in stored
              or any(str(_d(r[c]) if c.endswith("_date") else r[c]) != str(stored[r["isin"]][c])
                     for c in LEGACY_REFERENCE_COLUMNS if c not in ("isin",))]
    return {"old": len(rows), "stored": len(stored), "added_now": added, "conflicts": conflicts,
            "values_differ": differ[:5], "ok": len(rows) == len(stored) and not differ and not conflicts}


# --- reconciliation -------------------------------------------------------------------------------------------

def _f(x):
    return None if x is None else float(x)


def reconcile(conn, old_db: Path) -> dict:
    """Compare the new current views with the old database, table by table. Every check reports counts and the
    first few differences; `ok` is true only when there are none (or only the documented, expected ones)."""
    old = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    report = {}

    # 1. files: every old file parsed ok, same report date
    old_files = {r["url"]: dict(r) for r in old.execute("select url, file_type, report_date from files")}
    new_files = {r["url"]: r for r in conn.execute("select url, kind, report_date, parse_status from bonds.files_latest_parse")}
    missing = [u for u in old_files if u not in new_files]
    date_diff = [u for u, r in old_files.items() if u in new_files and str(new_files[u]["report_date"]) != r["report_date"]]
    report["files"] = {"old": len(old_files), "new_parsed_ok": len(new_files), "missing": missing[:5],
                       "n_missing": len(missing), "report_date_differs": date_diff[:5], "n_date_differs": len(date_diff),
                       "ok": not missing and not date_diff}

    # 2. trades: exact, by (date, isin)
    old_t = {(r["obs_date"], r["isin"]): tuple(dict(r)[c] for c in
             ("security_type", "open_yield", "close_yield", "high_yield", "low_yield", "wavg_yield", "volume_lkr", "n_trades"))
             for r in old.execute("select * from trade_summary")}
    new_t = {(str(r["obs_date"]), r["isin"]): (r["security_type"], *(_f(r[c]) for c in
             ("open_yield", "close_yield", "high_yield", "low_yield", "wavg_yield")), r["volume_lkr"], r["n_trades"])
             for r in conn.execute("select * from bonds.trades_current")}
    report["trades"] = _compare(old_t, new_t)

    # 3. volumes: exact, by (date, isin)
    old_v = {(r["obs_date"], r["isin"]): r["volume_lkr"] for r in old.execute(
        "select obs_date, isin, volume_lkr from observations where source='pdmo_daily' and volume_lkr is not null")}
    new_v = {(str(r["obs_date"]), r["isin"]): r["volume_lkr"] for r in conn.execute("select * from bonds.volumes_current")}
    report["volumes"] = _compare(old_v, new_v)

    # 4. auctions: results and announcements, by (date, isin, kind)
    old_a = {(r["auction_date"], r["isin"], r["kind"]): (r["settlement_date"], _f(r["way_pct"]), r["offered_lkr"],
                                                         r["bids_lkr"], r["accepted_lkr"], _f(r["accrued_per_100"]))
             for r in old.execute("select * from auctions")}
    new_a = {(str(r["auction_date"]), r["isin"], r["kind"]): (str(r["settlement_date"]) if r["settlement_date"] else None,
             _f(r["way_pct"]), r["offered_lkr"], r["bids_lkr"], r["accepted_lkr"], None)
             for r in conn.execute("select * from bonds.auction_results_current")}
    new_a.update({(str(r["auction_date"]), r["isin"], "announced"): (
                  str(r["settlement_date"]) if r["settlement_date"] else None, None, r["offered_lkr"], None, None,
                  _f(r["accrued_per_100"]))
                  for r in conn.execute("select * from bonds.auction_announcements_current")})
    report["auctions"] = _compare(old_a, new_a)

    # 5. quotes: the old DB kept only quotes it could tie to a bond; every one of them must appear, with identical
    #    values, among the new rows for that day. The new rows it did not keep must number exactly what the old
    #    parse notes said were "left out" (administered or one-way quotes), day by day.
    maturity = {r["isin"]: r["maturity_date"] for r in old.execute("select isin, maturity_date from bonds")}
    old_q = Counter()
    for r in old.execute("""select obs_date, isin, bid_yield, offer_yield, bid_price, offer_price from observations
                            where source='pdmo_daily' and (bid_yield is not null or offer_yield is not null)"""):
        old_q[(r["obs_date"], maturity[r["isin"]], _f(r["bid_yield"]), _f(r["offer_yield"]),
               _f(r["bid_price"]), _f(r["offer_price"]))] += 1
    new_q = Counter()
    per_day_new = Counter()
    for r in conn.execute("select * from bonds.quotes_current"):
        key = (str(r["report_date"]), str(r["maturity_date"]), _f(r["bid_yield"]), _f(r["offer_yield"]),
               _f(r["bid_price"]), _f(r["offer_price"]))
        new_q[key] += 1
        per_day_new[str(r["report_date"])] += 1
    unmatched_old = old_q - new_q
    left_out_new = Counter()
    for key, n in (new_q - old_q).items():
        left_out_new[key[0]] += n
    # The old parse note says how many quotes were matched to a bond and how many were left out. Matched quotes
    # that resolved to the SAME bond overwrote each other (an upsert), so the old table holds fewer rows than
    # "matched". Those overwritten quotes are also missing from the old table; they are counted separately.
    old_stored_per_day = Counter(k[0] for k in old_q.elements())
    expected_left_out, overwritten = {}, {}
    for r in old.execute("select report_date, parse_note from files where file_type='daily_summary'"):
        note = r["parse_note"] or ""
        if "left out" in note:
            matched = int(note.split(" ")[0])
            left_out = int(note.split(";")[-1].strip().split(" ")[0])
            overwritten[r["report_date"]] = matched - old_stored_per_day.get(r["report_date"], 0)
            expected_left_out[r["report_date"]] = left_out + overwritten[r["report_date"]]
    day_mismatch = {d: (left_out_new.get(d, 0), n) for d, n in expected_left_out.items() if left_out_new.get(d, 0) != n}
    report["quotes"] = {
        "old_rows": sum(old_q.values()), "new_rows": sum(new_q.values()),
        "old_rows_not_found_in_new": sum(unmatched_old.values()), "examples": [list(k) for k in list(unmatched_old)[:5]],
        "new_rows_old_did_not_keep": sum(left_out_new.values()),
        "of_which_left_out_by_old_filter": sum(expected_left_out.values()) - sum(overwritten.values()),
        "of_which_overwritten_in_old_db": sum(overwritten.values()),
        "days_with_overwrites": sum(1 for v in overwritten.values() if v),
        "days_where_counts_differ": len(day_mismatch),
        "examples_day_mismatch": dict(list(day_mismatch.items())[:5]),
        "ok": not unmatched_old and not day_mismatch,
    }
    report["ok"] = all(v.get("ok") for k, v in report.items() if isinstance(v, dict))
    return report


def _compare(old: dict, new: dict) -> dict:
    missing = [k for k in old if k not in new]
    extra = [k for k in new if k not in old]
    differ = [k for k in old if k in new and _norm(old[k]) != _norm(new[k])]
    return {"old": len(old), "new": len(new), "missing_in_new": len(missing), "extra_in_new": len(extra),
            "values_differ": len(differ),
            "examples": {"missing": [list(map(str, k)) for k in missing[:3]],
                         "extra": [list(map(str, k)) for k in extra[:3]],
                         "differ": [[list(map(str, k)), list(map(str, _norm(old[k]))), list(map(str, _norm(new[k])))]
                                    for k in differ[:3]]},
            "ok": not missing and not extra and not differ}


def _norm(v):
    if isinstance(v, tuple):
        return tuple(_norm(x) for x in v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Migrate and reconcile the bond history")
    ap.add_argument("--old-db", type=Path, required=True)
    ap.add_argument("--old-history", type=Path)
    ap.add_argument("--pdmo-archive", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--no-network", action="store_true", help="don't read today's index pages (label dates unknown)")
    ap.add_argument("--old-commit", default=OLD_COMMIT, help="the Nelson-Siegel commit --old-db was taken from")
    ap.add_argument("--legacy-reference-db", type=Path,
                    help="the old database whose bond list bond_identity v1 starts from (default: --old-db). The "
                         "manifest pins the audited one, 1c33084: git show 1c33084:data/sgcp.sqlite > file")
    args = ap.parse_args(argv)
    s = settings_mod.load()
    conn = db.connect(s.database_url)
    db.migrate(conn)
    store = rawstore.from_settings(s)
    old_db_sha = archive_legacy_file(conn, store, args.old_db, "data/sgcp.sqlite", args.old_commit)
    ref_db = args.legacy_reference_db or args.old_db
    ref_sha = (archive_legacy_file(conn, store, ref_db, "data/sgcp.sqlite") if args.legacy_reference_db
               else old_db_sha)
    if args.old_history:
        archive_legacy_file(conn, store, args.old_history, "bond_db_history.sqlite (rebuilt from git, verified)")
    conn.commit()
    loaded = load(conn, store, args.old_db, args.pdmo_archive, None if args.no_network else PoliteClient(min_interval=1.5),
                  dt.date.today())
    reconciliation = reconcile(conn, args.old_db)
    reconciliation["legacy_reference"] = load_legacy_reference(conn, ref_db, ref_sha)
    reconciliation["ok"] = reconciliation["ok"] and reconciliation["legacy_reference"]["ok"]
    report = {"loaded": loaded, "reconciliation": reconciliation,
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "old_db_sha256": rawstore.sha256_of(args.old_db.read_bytes())}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report["reconciliation"], indent=2, default=str)[:3000])
    return 0 if report["reconciliation"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
