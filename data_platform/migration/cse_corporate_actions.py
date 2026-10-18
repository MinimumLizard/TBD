"""Load the CSE corporate-action facts from the raw archive, then reconcile them with the old terminal's caches.

    python -m data_platform.migration.cse_corporate_actions --old-repo <CSE clone> --archive \\
        --report docs/migration/cse-corporate-actions-reconciliation.json
    python -m data_platform.migration.cse_corporate_actions                      # from the archive alone

The old terminal cached every response its corporate-action collection received (data/raw/announcements/byCompany,
getAnnouncementById, getGeneralAnnouncementById), and its daily job kept the detail of each new announcement in its
session folders (data/raw/<session>/getAnnouncementById, ...). The CSE history migration already archived all of
them: the caches as source 'legacy_cse' (url git://github.com/MinimumLizard/CSE@<commit>/<path>), the session files
as the replayed 'cse_api' requests. This step:

  1. with --archive, archives the cache files exactly as the history migration does (the same catalogue entries are
     reused, so nothing is archived twice), in case they are not in the archive yet;
  2. reads every such file back FROM THE ARCHIVE (not from the clone), through the collector's own parsers, into
     cse.company_announcements and cse.announcement_details; also any live detail or list response the archive
     holds that is not yet a fact;
  3. with --old-repo, reconciles: every cache file and every session detail file must be a fact, with the same
     SHA-256 and, for list rows, the same category and date (counts and a checksum each side).

Repeatable: a second run adds nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ..collectors.cse import parse
from ..collectors.cse.collector import API, store_company_announcements, store_detail
from ..core import db, rawstore, settings as settings_mod

LEGACY = "legacy_cse"
NOTE = "old repo raw file, archived as-is"          # the history migration's note (migration/cse.py archive_other)
CACHE = Path("data") / "raw" / "announcements"
LIST_DIR = "byCompany"
DETAIL_RE = re.compile(r"/data/raw/(announcements|\d{4}-\d{2}-\d{2})/(getAnnouncementById|getGeneralAnnouncementById)"
                       r"/(\d+)\.json$")
LIST_RE = re.compile(r"/data/raw/announcements/byCompany/([^/_]+)_[^/]*\.json$")


def _commit(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip() or "unknown"


def cache_files(repo: Path) -> list[Path]:
    root = repo / CACHE
    return sorted(p for sub in (LIST_DIR, *parse.DETAIL_ENDPOINTS) for p in (root / sub).glob("*.json"))


def archive_cache(conn, store, repo: Path) -> int:
    """Archive the old cache files as the history migration does. Returns how many catalogue entries are new."""
    commit = _commit(repo)
    before = conn.execute("select count(*) n from ops.raw_fetches where source_id = %s", (LEGACY,)).fetchone()["n"]
    for p in cache_files(repo):
        rel = p.relative_to(repo)
        db.record_fetch(conn, store, source_id=LEGACY, method="GIT",
                        url=f"git://github.com/MinimumLizard/CSE@{commit}/{rel}", params={}, http_status=200,
                        body=p.read_bytes(), content_type=None, fetched_at=dt.datetime.now(dt.timezone.utc),
                        origin="migration", note=NOTE)
    conn.commit()
    return conn.execute("select count(*) n from ops.raw_fetches where source_id = %s",
                        (LEGACY,)).fetchone()["n"] - before


def _first_per_file(rows: list[dict], path_of) -> list[dict]:
    """The archive can hold one file several times (catalogued once per commit and per archiving step); its bytes
    are the same (same SHA-256), so the first catalogue entry for each (path, content) is used."""
    seen, out = set(), []
    for r in rows:
        k = (path_of(r), r["sha256"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def load_from_archive(conn, store) -> Counter:
    stats = Counter()
    have = {(r["announcement_id"], r["endpoint"], r["raw_sha256"]) for r in conn.execute(
        "select announcement_id, endpoint, raw_sha256 from cse.announcement_details")}

    # company lists: the old caches, and any live list
    lists = conn.execute(
        """select fetch_id, url, params, sha256, fetched_at, source_id from ops.raw_fetches
           where (source_id = %s and url ~ '/data/raw/announcements/byCompany/[^/]+\\.json$')
              or (source_id = 'cse_api' and url = %s and http_status in (200, 204))
           order by fetch_id""", (LEGACY, API + "getAnnouncementByCompany")).fetchall()
    for r in _first_per_file(lists, lambda r: r["url"].split("@", 1)[-1].split("/", 1)[-1]
                             if r["source_id"] == LEGACY else (r["url"], json.dumps(r["params"], sort_keys=True))):
        symbol = LIST_RE.search(r["url"]).group(1) if r["source_id"] == LEGACY else r["params"]["symbol"]
        rows = parse.company_announcements(db.raw_bytes(conn, store, r["sha256"]), symbol)
        stats["list_files"] += 1
        stats["list_rows_added"] += store_company_announcements(conn, rows, r["fetch_id"], r["fetched_at"])

    # details: the old caches, the old session folders' files, and every live or replayed detail request
    details = conn.execute(
        """select fetch_id, url, params, sha256, fetched_at, source_id from ops.raw_fetches
           where (source_id = %s and url ~ %s) or (source_id = 'cse_api' and url = any(%s))
           order by fetch_id""",
        (LEGACY, DETAIL_RE.pattern, [API + ep for ep in parse.DETAIL_ENDPOINTS])).fetchall()
    for r in details:
        if r["source_id"] == LEGACY:
            _, endpoint, aid = DETAIL_RE.search(r["url"]).groups()
        else:
            endpoint, aid = r["url"].rsplit("/", 1)[-1], str(r["params"]["announcementId"])
        if (int(aid), endpoint, r["sha256"]) in have:
            continue
        store_detail(conn, db.raw_bytes(conn, store, r["sha256"]), endpoint, aid, r["sha256"], r["fetch_id"],
                     r["fetched_at"])
        have.add((int(aid), endpoint, r["sha256"]))
        stats["detail_rows_added"] += 1
    conn.commit()
    return stats


def _digest(lines) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def reconcile(conn, repo: Path) -> dict:
    """Counts and checksums: the old caches and session detail files on one side, the facts on the other."""
    report: dict = {}
    facts = {(r["announcement_id"], r["endpoint"], r["raw_sha256"]): r["has_detail"] for r in conn.execute(
        "select announcement_id, endpoint, raw_sha256, has_detail from cse.announcement_details")}
    for label, pattern in (("cache", CACHE / "{ep}"), ("session_folders", Path("data") / "raw" / "*" / "{ep}")):
        for ep in parse.DETAIL_ENDPOINTS:
            files = [p for p in sorted(repo.glob(str(pattern).format(ep=ep) + "/*.json"))
                     if label == "cache" or p.parent.parent.name[:2] == "20"]
            old = {(int(p.stem), ep, rawstore.sha256_of(p.read_bytes())) for p in files}
            with_detail = sum(1 for p in files if parse.detail_fact(p.read_bytes(), ep, p.stem)["has_detail"])
            missing = old - set(facts)
            report[f"details_{label}_{ep}"] = {
                "old_files": len(files), "old_with_detail": with_detail, "facts_matching": len(old) - len(missing),
                "facts_with_detail": sum(1 for k in old if facts.get(k)), "missing_in_new": len(missing),
                "old_sha256": _digest(f"{a}:{e}:{s}" for a, e, s in old),
                "new_sha256": _digest(f"{a}:{e}:{s}" for a, e, s in old if (a, e, s) in facts),
                "ok": not missing and with_detail == sum(1 for k in old if facts.get(k))}

    new_lists = {(r["symbol"], r["announcement_id"]): (r["category"], r["announced_date"]) for r in conn.execute(
        "select symbol, announcement_id, category, announced_date from cse.company_announcements")}
    old_lists, files, ca = {}, 0, 0
    for p in sorted((repo / CACHE / LIST_DIR).glob("*.json")):
        files += 1
        symbol = p.name.split("_")[0]
        body = p.read_bytes()
        for a in (json.loads(body) if body.strip() else {}).get("reqCompanyAnnouncement", []):
            old_lists[(symbol, int(a["announcementId"]))] = (
                (a.get("announcementCategory") or "").strip(), parse.announcement_date(a.get("dateOfAnnouncement")))
            ca += parse.is_ca_category(a.get("announcementCategory", ""))
    missing = [k for k in old_lists if k not in new_lists]
    differ = [k for k in old_lists if k in new_lists and new_lists[k] != old_lists[k]]
    report["company_lists"] = {
        "old_files": files, "old_rows": len(old_lists), "old_corporate_action_rows": ca, "new_rows_matching":
        len(old_lists) - len(missing), "missing_in_new": len(missing), "values_differ": len(differ),
        "old_sha256": _digest(f"{s}:{a}:{c}:{d}" for (s, a), (c, d) in old_lists.items()),
        "new_sha256": _digest(f"{s}:{a}:{c}:{d}" for (s, a), (c, d) in new_lists.items() if (s, a) in old_lists),
        "ok": not missing and not differ}
    report["value_conflicts"] = conn.execute(
        """select count(*) n from ops.value_conflicts
           where table_name in ('cse.company_announcements', 'cse.announcement_details')""").fetchone()["n"]
    report["ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict)) and report["value_conflicts"] == 0
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old-repo", type=Path, help="a read-only clone (or export) of MinimumLizard/CSE to reconcile with")
    ap.add_argument("--archive", action="store_true", help="first archive the clone's cache files (step 1)")
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
        out["catalogue_entries_added"] = archive_cache(conn, store, args.old_repo)
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
