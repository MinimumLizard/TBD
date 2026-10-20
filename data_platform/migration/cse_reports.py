"""Load the CSE report index and report texts (and each company's financial year end) from the raw archive, then
reconcile them with the old terminal's folders.

    python -m data_platform.migration.cse_reports --old-repo <CSE clone> --archive \\
        --report docs/migration/cse-reports-reconciliation.json
    python -m data_platform.migration.cse_reports                      # from the archive alone

The old terminal's ownership collector kept, in data/raw/ownership/: reports.csv (its index of every interim report
it read), text/<report id>.txt (each report's text, from `pdftotext -layout`; it did not keep the PDFs),
financials/<symbol>.json (each company's report list) and, for the parents evidence, annual_reports.csv and
annual/<id>.json (passages from annual reports). The CSE history migration archived all of them as source
'legacy_cse' (url git://github.com/MinimumLizard/CSE@<commit>/<path>). This step:

  1. with --archive, archives those files exactly as the history migration does, in case they are not in the archive
     yet (a file already catalogued under the same path and commit adds nothing);
  2. reads them back FROM THE ARCHIVE (not from the clone) into cse.financial_reports (one row per index row, with
     the SHA-256 of its text) and cse.report_texts (the text itself, for the models). The report lists and the
     annual-report passages stay archived files: no model reads them (the parents evidence is suggestions only);
  3. reads every archived companyProfile response into cse.company_fiscal_years (the financial year end the
     fundamentals use), with the session whose run fetched it;
  4. with --old-repo, reconciles: every index row and every text file must be a fact, with the same values and the
     same SHA-256 (counts and a checksum each side), and every other ownership file must be in the archive.

Repeatable: a second run adds nothing.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ..collectors.cse import parse
from ..collectors.cse.collector import API
from ..collectors.cse.reports import add_text, store_report
from ..core import db, rawstore, settings as settings_mod

LEGACY = "legacy_cse"
NOTE = "old repo raw file, archived as-is"          # the history migration's note (migration/cse.py archive_other)
OWN = Path("data") / "raw" / "ownership"
INDEX_RE = re.compile(r"@([^/]+)/data/raw/ownership/reports\.csv$")
TEXT_RE = re.compile(r"@([^/]+)/data/raw/ownership/text/(\d+)\.txt$")
SESSION_RE = re.compile(r"data/raw/(\d{4}-\d{2}-\d{2})/companyProfile/")
EXTRACTED_BY = "pdftotext -layout (MinimumLizard/CSE ownership collector; its text file)"
SLT = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _commit(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip() or "unknown"


def own_files(repo: Path) -> list[Path]:
    return sorted(p for p in (repo / OWN).rglob("*") if p.is_file())


def archive_files(conn, store, repo: Path) -> int:
    """Archive the old ownership folder as the history migration does. Returns how many catalogue entries are new."""
    commit = _commit(repo)
    before = conn.execute("select count(*) n from ops.raw_fetches where source_id = %s", (LEGACY,)).fetchone()["n"]
    for p in own_files(repo):
        rel = p.relative_to(repo)
        db.record_fetch(conn, store, source_id=LEGACY, method="GIT",
                        url=f"git://github.com/MinimumLizard/CSE@{commit}/{rel}", params={}, http_status=200,
                        body=p.read_bytes(), content_type=None, fetched_at=dt.datetime.now(dt.timezone.utc),
                        origin="migration", note=NOTE)
    conn.commit()
    return conn.execute("select count(*) n from ops.raw_fetches where source_id = %s",
                        (LEGACY,)).fetchone()["n"] - before


def _ts(s: str) -> dt.datetime | None:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def index_row(r: dict, text_sha: str | None, fetch_id: int) -> dict:
    """One row of the old reports.csv as a cse.financial_reports fact."""
    return {"report_id": int(r["id"]), "code": r["code"], "symbol": r["symbol"], "kind": r["kind"],
            "title": r["title"], "period_date": dt.date.fromisoformat(r["period_date"]) if r["period_date"] else None,
            "uploaded_at": _ts(r["uploaded_utc"]), "url": r["url"],
            "pages": int(r["pages"]) if r["pages"] not in ("", None) else None,
            "words": int(r["words"]) if r["words"] not in ("", None) else None, "status": r["status"],
            "pdf_sha256": None, "text_sha256": text_sha, "extracted_by": EXTRACTED_BY if text_sha else None,
            "fetch_id": fetch_id, "fetched_at": _ts(r["fetched_utc"])}


def load_from_archive(conn, store) -> Counter:
    stats = Counter()
    texts: dict[tuple[str, str], str] = {}          # (commit, report id) -> sha256
    latest_text: dict[str, str] = {}                # report id -> sha256 (the last catalogued)
    for r in conn.execute("""select url, sha256 from ops.raw_fetches where source_id = %s and url ~ %s
                             order by fetch_id""", (LEGACY, TEXT_RE.pattern)):
        commit, rid = TEXT_RE.search(r["url"]).groups()
        texts[(commit, rid)] = latest_text[rid] = r["sha256"]
    have_text = {r["sha256"] for r in conn.execute("select sha256 from cse.report_texts")}
    for sha in sorted(set(latest_text.values()) | set(texts.values())):
        if sha not in have_text:
            add_text(conn, sha, db.raw_bytes(conn, store, sha))
            have_text.add(sha)
            stats["texts_added"] += 1

    seen: set[tuple[str, str]] = set()
    for f in conn.execute("""select fetch_id, url, sha256 from ops.raw_fetches where source_id = %s and url ~ %s
                             order by fetch_id""", (LEGACY, INDEX_RE.pattern)).fetchall():
        commit = INDEX_RE.search(f["url"]).group(1)
        body = db.raw_bytes(conn, store, f["sha256"])
        stats["index_files"] += 1
        for r in csv.DictReader(io.StringIO(body.decode("utf-8"))):
            if (r["id"], r["fetched_utc"]) in seen:       # the same row in another commit's copy of the index
                continue
            seen.add((r["id"], r["fetched_utc"]))
            sha = texts.get((commit, r["id"])) or latest_text.get(r["id"])
            if r["status"] != "download_failed" and sha is None:
                raise RuntimeError(f"report {r['id']}: status {r['status']} but its text file is not in the archive")
            stats["index_rows_added"] += store_report(conn, index_row(r, sha if r["status"] != "download_failed" else None,
                                                                      f["fetch_id"]))
    stats.update(load_fiscal_years(conn, store))
    conn.commit()
    return stats


def load_fiscal_years(conn, store) -> Counter:
    """Every archived companyProfile response (old session folders replayed by the history migration, and live
    end-of-day runs) -> cse.company_fiscal_years, with the session whose run fetched it."""
    stats = Counter()
    have = {(r["symbol"], r["raw_sha256"]) for r in conn.execute("select symbol, raw_sha256 from cse.company_fiscal_years")}
    rows = conn.execute(
        """select f.fetch_id, f.params, f.sha256, f.fetched_at, f.note,
                  (select max(ci.session_date) from cse.company_info_daily ci join ops.raw_fetches g
                     on g.fetch_id = ci.fetch_id where f.run_id is not null and g.run_id = f.run_id) run_session
           from ops.raw_fetches f where f.source_id = 'cse_api' and f.url = %s and f.http_status = 200
           order by f.fetch_id""", (API + "companyProfile",)).fetchall()
    for r in rows:
        symbol = (r["params"] or {}).get("symbol")
        if not symbol or (symbol, r["sha256"]) in have:
            continue
        m = SESSION_RE.search(r["note"] or "")
        session = (dt.date.fromisoformat(m.group(1)) if m else r["run_session"]
                   or r["fetched_at"].astimezone(SLT).date())
        row = dict(parse.fin_year_end(db.raw_bytes(conn, store, r["sha256"]), symbol), raw_sha256=r["sha256"],
                   session_date=session, fetch_id=r["fetch_id"], fetched_at=r["fetched_at"])
        stats["fiscal_year_rows_added"] += db.insert_facts(conn, "cse.company_fiscal_years", [row],
                                                           key=["symbol", "raw_sha256"])[0]
        have.add((symbol, r["sha256"]))
    return stats


# --- reconciliation -------------------------------------------------------------------------------------------

def _digest(lines) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


INDEX_COLS = ["code", "symbol", "kind", "title", "period_date", "uploaded_utc", "url", "pages", "words", "status",
              "fetched_utc"]


def _fact_as_csv(r: dict) -> dict:
    fmt = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""
    return {"code": r["code"], "symbol": r["symbol"], "kind": r["kind"], "title": r["title"],
            "period_date": r["period_date"].isoformat() if r["period_date"] else "",
            "uploaded_utc": fmt(r["uploaded_at"]), "url": r["url"],
            "pages": "" if r["pages"] is None else str(r["pages"]), "words": "" if r["words"] is None else str(r["words"]),
            "status": r["status"], "fetched_utc": fmt(r["fetched_at"])}


def reconcile(conn, repo: Path) -> dict:
    """Counts and checksums: the old ownership folder on one side, the facts and the archive on the other."""
    base = repo / OWN
    report: dict = {}
    old = {r["id"]: {c: r[c] for c in INDEX_COLS} for r in csv.DictReader((base / "reports.csv").open(newline=""))}
    facts = {str(r["report_id"]): r for r in conn.execute("select * from cse.financial_reports_current")}
    new = {k: _fact_as_csv(v) for k, v in facts.items() if k in old}
    missing = [k for k in old if k not in facts]
    differ = [k for k in old if k in new and new[k] != old[k]]
    report["index"] = {"old_rows": len(old), "facts_matching": len(old) - len(missing) - len(differ),
                       "missing_in_new": len(missing), "values_differ": len(differ),
                       "facts_not_in_old_index": len(set(facts) - set(old)),
                       "old_status": dict(Counter(r["status"] for r in old.values())),
                       "old_sha256": _digest(json.dumps([k, v], sort_keys=True) for k, v in old.items()),
                       "new_sha256": _digest(json.dumps([k, v], sort_keys=True) for k, v in new.items()),
                       "ok": not missing and not differ}

    texts = {r["sha256"]: r["body"] for r in conn.execute(
        "select sha256, body from cse.report_texts where sha256 = any(%s)",
        ([r["text_sha256"] for r in facts.values() if r["text_sha256"]],))}
    files = sorted((base / "text").glob("*.txt"))
    linked = same_text = 0
    old_lines, new_lines = [], []
    for p in files:
        body = p.read_bytes()
        sha = rawstore.sha256_of(body)
        old_lines.append(f"{p.stem}:{sha}")
        fact = facts.get(p.stem)
        if fact and fact["text_sha256"] == sha:
            linked += 1
            new_lines.append(f"{p.stem}:{fact['text_sha256']}")
            if texts.get(sha, "").encode("utf-8") == body:
                same_text += 1
    report["texts"] = {"old_files": len(files), "facts_with_same_sha256": linked, "stored_text_identical": same_text,
                       "old_sha256": _digest(old_lines), "new_sha256": _digest(new_lines),
                       "ok": linked == len(files) == same_text}

    archived = {r["sha256"] for r in conn.execute("select sha256 from ops.raw_fetches where source_id = %s", (LEGACY,))}
    for label, pattern in (("financials_lists", "financials/*.json"), ("annual_passages", "annual/*.json"),
                           ("annual_index", "annual_reports.csv")):
        paths = sorted(base.glob(pattern))
        in_archive = sum(1 for p in paths if rawstore.sha256_of(p.read_bytes()) in archived)
        report[f"archived_{label}"] = {"old_files": len(paths), "in_archive": in_archive, "ok": in_archive == len(paths)}

    old_fye = {}
    for p in sorted((repo / "data" / "raw").glob("*/companyProfile/*.json")):
        info = (json.loads(p.read_bytes()).get("reqComSumInfo") or [{}])[0] or {}
        old_fye[(p.stem, rawstore.sha256_of(p.read_bytes()))] = str(info["finYearEnd"]) if info.get("finYearEnd") else None
    new_fye = {(r["symbol"], r["raw_sha256"]): r["fin_year_end"] for r in conn.execute(
        "select symbol, raw_sha256, fin_year_end from cse.company_fiscal_years")}
    fmiss = [k for k in old_fye if k not in new_fye]
    fdiff = [k for k in old_fye if k in new_fye and new_fye[k] != old_fye[k]]
    report["fiscal_years"] = {"old_profiles": len(old_fye), "with_year_end": sum(v is not None for v in old_fye.values()),
                              "missing_in_new": len(fmiss), "values_differ": len(fdiff), "ok": not fmiss and not fdiff}
    report["value_conflicts"] = conn.execute(
        """select count(*) n from ops.value_conflicts
           where table_name in ('cse.financial_reports', 'cse.company_fiscal_years')""").fetchone()["n"]
    report["ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict)) and report["value_conflicts"] == 0
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old-repo", type=Path, help="a read-only clone of MinimumLizard/CSE to reconcile with")
    ap.add_argument("--archive", action="store_true", help="first archive the clone's ownership files (step 1)")
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
        out["catalogue_entries_added"] = archive_files(conn, store, args.old_repo)
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
