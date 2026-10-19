"""Load the old terminal's directors' dealing notices from the raw archive, then reconcile them with its files.

    python -m data_platform.migration.cse_dealings --old-repo <CSE clone> --archive \\
        --report docs/migration/cse-dealings-reconciliation.json
    python -m data_platform.migration.cse_dealings                      # from the archive alone

The old terminal kept every dealing notice it read (old cse/dealings.py):
  * data/raw/dealings/<id>.json             the one-off backfill of older notices (getAnnouncementById responses;
                                            a 204 or empty answer was saved as `{}` so it was not asked again);
  * data/raw/<session>/getAnnouncementById/ the daily job's copy of each new announcement's detail.
The session files are already facts (the history migration replays them, and the corporate-action step loads every
detail response the archive holds). This step does the same for the backfill:

  1. with --archive, archives data/raw/dealings/*.json as the history migration archives every other old file
     (source 'legacy_cse', url git://github.com/MinimumLizard/CSE@<commit>/<path>; an existing catalogue entry is
     reused, so nothing is archived twice);
  2. reads every such file back FROM THE ARCHIVE (not from the clone), through the collector's own parser, into
     cse.announcement_details as getAnnouncementById responses;
  3. with --old-repo, reconciles: every backfill file and every session detail file with a dealing record must be a
     fact with the same SHA-256 (counts and a checksum each side), and the old data/dealings/dealings.csv's notices
     must all be among the facts.

Repeatable: a second run adds nothing.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ..collectors.cse.collector import store_detail
from ..core import db, rawstore, settings as settings_mod

LEGACY = "legacy_cse"
NOTE = "old repo raw file, archived as-is"          # the history migration's note (migration/cse.py archive_other)
BACKFILL = Path("data") / "raw" / "dealings"
ENDPOINT = "getAnnouncementById"
DEALING_TYPE = "DealingsByDirectors"
FILE_RE = re.compile(r"/data/raw/dealings/(\d+)\.json$")


def _commit(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip() or "unknown"


def backfill_files(repo: Path) -> list[Path]:
    return sorted((repo / BACKFILL).glob("*.json"), key=lambda p: int(p.stem))


def archive_backfill(conn, store, repo: Path) -> int:
    """Archive the backfill files as the history migration does. Returns how many catalogue entries are new."""
    commit = _commit(repo)
    before = conn.execute("select count(*) n from ops.raw_fetches where source_id = %s", (LEGACY,)).fetchone()["n"]
    for p in backfill_files(repo):
        db.record_fetch(conn, store, source_id=LEGACY, method="GIT",
                        url=f"git://github.com/MinimumLizard/CSE@{commit}/{p.relative_to(repo)}", params={},
                        http_status=200, body=p.read_bytes(), content_type=None,
                        fetched_at=dt.datetime.now(dt.timezone.utc), origin="migration", note=NOTE)
    conn.commit()
    return conn.execute("select count(*) n from ops.raw_fetches where source_id = %s",
                        (LEGACY,)).fetchone()["n"] - before


def load_from_archive(conn, store) -> Counter:
    """Every archived backfill file that is not a fact yet becomes one (the first catalogue entry of each distinct
    file: the archive catalogues a file once per commit it was archived at)."""
    stats = Counter()
    have = {(r["announcement_id"], r["raw_sha256"]) for r in conn.execute(
        "select announcement_id, raw_sha256 from cse.announcement_details where endpoint = %s", (ENDPOINT,))}
    for r in conn.execute(
            """select fetch_id, url, sha256, fetched_at from ops.raw_fetches
               where source_id = %s and url ~ %s order by fetch_id""", (LEGACY, FILE_RE.pattern)).fetchall():
        aid = int(FILE_RE.search(r["url"]).group(1))
        stats["catalogue_entries"] += 1
        if (aid, r["sha256"]) in have:
            continue
        row = store_detail(conn, db.raw_bytes(conn, store, r["sha256"]), ENDPOINT, str(aid), r["sha256"],
                           r["fetch_id"], r["fetched_at"])
        have.add((aid, r["sha256"]))
        stats["detail_rows_added"] += 1
        stats["with_dealing_record"] += row["d_type"] == DEALING_TYPE
    conn.commit()
    return stats


def _digest(lines) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def _dtype(body: bytes) -> str | None:
    try:
        data = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return None
    return ((data or {}).get("reqBaseAnnouncement") or {}).get("dType") if isinstance(data, dict) else None


def reconcile(conn, repo: Path) -> dict:
    """Counts and checksums: the old backfill and session detail files on one side, the facts on the other."""
    facts = {(r["announcement_id"], r["raw_sha256"]): r["d_type"] for r in conn.execute(
        "select announcement_id, raw_sha256, d_type from cse.announcement_details where endpoint = %s", (ENDPOINT,))}
    report: dict = {}
    sessions = [p for p in sorted(repo.glob(f"data/raw/*/{ENDPOINT}/*.json")) if p.parent.parent.name[:2] == "20"]
    for label, files in (("backfill", backfill_files(repo)),
                         ("session_folders", [p for p in sessions if _dtype(p.read_bytes()) == DEALING_TYPE])):
        old = {(int(p.stem), rawstore.sha256_of(p.read_bytes())): _dtype(p.read_bytes()) for p in files}
        missing = [k for k in old if k not in facts]
        report[label] = {
            "old_files": len(files), "old_with_dealing_record": sum(1 for v in old.values() if v == DEALING_TYPE),
            "facts_matching": len(old) - len(missing),
            "facts_with_dealing_record": sum(1 for k in old if facts.get(k) == DEALING_TYPE),
            "missing_in_new": len(missing),
            "old_sha256": _digest(f"{a}:{s}" for a, s in old), "new_sha256": _digest(f"{a}:{s}" for a, s in old
                                                                                    if (a, s) in facts),
            "ok": not missing and all(facts[k] == v for k, v in old.items() if k in facts)}
    csv_path = repo / "data" / "dealings" / "dealings.csv"
    if csv_path.exists():
        notices = {int(r["announcement_id"]) for r in csv.DictReader(csv_path.open(newline=""))}
        dealing_facts = {a for (a, _), t in facts.items() if t == DEALING_TYPE}
        report["dealings_csv"] = {"old_notices": len(notices), "notices_with_a_fact": len(notices & dealing_facts),
                                  "missing_in_new": len(notices - dealing_facts), "ok": notices <= dealing_facts}
    report["value_conflicts"] = conn.execute(
        "select count(*) n from ops.value_conflicts where table_name = 'cse.announcement_details'").fetchone()["n"]
    report["ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict)) and report["value_conflicts"] == 0
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old-repo", type=Path, help="a read-only clone (or export) of MinimumLizard/CSE to reconcile with")
    ap.add_argument("--archive", action="store_true", help="first archive the clone's backfill files (step 1)")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)
    s = settings_mod.load()
    conn = db.connect(s.database_url)
    db.migrate(conn)
    store = rawstore.from_settings(s)
    out: dict = {}
    if args.archive:
        if not args.old_repo:
            ap.error("--archive needs --old-repo")
        out["old_commit"] = _commit(args.old_repo)
        out["catalogue_entries_added"] = archive_backfill(conn, store, args.old_repo)
    out["loaded"] = dict(load_from_archive(conn, store))
    ok = True
    if args.old_repo:
        out["reconciliation"] = reconcile(conn, args.old_repo)
        ok = out["reconciliation"]["ok"]
    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    text = json.dumps(out, indent=2, default=str) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
