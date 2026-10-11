"""Archive the three old repositories completely, and check the archive against the audit's baselines.

    python -m data_platform.migration.legacy --cse <clone> --ns <clone> --crypto <clone> \\
        --bundles <dir with CSE.bundle, Nelson-Siegel.bundle, Crypto.bundle> --report docs/migration/legacy.json

Two layers, so nothing exists only on GitHub (audit F5):
  * every file at the audited commit of every branch that holds data, archived individually (source
    'legacy_<repo>', url git://github.com/MinimumLizard/<repo>@<commit>/<path>). This covers the files the bond and
    CSE migrations do not replay: CSE model outputs (corporate actions, dealings, ownership, fundamentals, the
    portfolio record) and the owner's hand-written confirmations in config/; the crypto history store; the old
    sites' code. Phase 3's parity tests read their golden inputs from here.
  * the complete history of each repo as a verified git bundle (every commit, every branch).

The check: recompute the audit's Appendix A fingerprints from the ARCHIVED bytes, not from the clones.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from ..core import db, rawstore, settings as settings_mod

AUDIT_BASELINES = {   # docs/audit.md Appendix A (first 16 hex characters of SHA-256)
    ("CSE", "data/history/prices.csv"): "7b72e1c8540e3499",
    ("CSE", "data/history/indices.csv"): "89dcfd3c8ebff51c",
    ("CSE", "data/history/market.csv"): "434a3d9b04ca3623",
    ("CSE", "data/history/announcements.csv"): "14c3a29dbba276ae",
    ("CSE", "data/history/corporate_actions.csv"): "5e057486d5645da8",
    ("CSE", "data/dealings/dealings.csv"): "1ca96bc44597272d",
    ("CSE", "data/fundamentals/latest.csv"): "d0e765389912a392",
    ("CSE", "data/fundamentals/reports.csv"): "5e076da582cc8fbc",
    ("CSE", "data/ownership/companies.csv"): "3590633966fb1173",
    ("CSE", "data/ownership/holdings.csv"): "8b331e1da828e3f7",
    ("CSE", "data/ownership/owners.csv"): "efadefd82ac7c8fa",
    ("CSE", "data/raw/ownership/annual_reports.csv"): "a9853f17ce57eb4b",
    ("CSE", "data/raw/ownership/reports.csv"): "aaa0a57508a82ec2",
    ("CSE", "record/holdings.csv"): "3502b393706d6964",
    ("CSE", "record/nav.csv"): "77013c928eb1fae3",
    ("CSE", "record/trades.csv"): "dbee4fa1712f9e5e",
    ("CSE", "data/runs.csv"): "389384458ef01f3a",
    ("Nelson-Siegel", "data/sgcp.sqlite"): "34ec862c837f334d",
}
# The commits the audit fingerprinted (docs/audit.md). The baselines are checked against these, whatever the old
# repos' latest commit is by the time the migration runs (they keep collecting daily until cut-over).
AUDITED = {"CSE": ("CSE", "f263830"), "Nelson-Siegel": ("Nelson-Siegel", "1c33084"),
           "Crypto": ("Crypto", "4dc446a"), "Crypto@data": ("Crypto", "fce882b")}

GROUP_BASELINES = {   # hash of the sorted "sha256  <path>" lines exactly as `sha256sum` printed them in the audit
    # (repo, path prefix, how the audit's `find` wrote the path): expected
    ("CSE", "data/raw/", "data/raw/"): "414cd7d24b457932",   # find data/raw -type f, run from the repo root
    ("Crypto@data", "", "./"): "50653dc65730bb56",           # find . -name '*.parquet', run on the data branch
}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def archive_tree(conn, store, repo: Path, name: str, ref: str, files: dict, key: str | None = None) -> int:
    """Archive every file of `repo` at `ref`; record {(key, path): sha256} in `files` (key defaults to name)."""
    commit = git(repo, "rev-parse", "--short", ref).decode().strip()
    n = 0
    for line in git(repo, "ls-tree", "-r", "-z", ref).split(b"\0"):
        if not line:
            continue
        meta, path = line.split(b"\t", 1)
        mode, kind, blob = meta.split()
        if kind != b"blob" or mode == b"160000":
            continue
        path = path.decode()
        body = git(repo, "cat-file", "blob", blob.decode())
        db.record_fetch(conn, store, source_id=f"legacy_{name.lower().replace('-', '_')}", method="GIT",
                        url=f"git://github.com/MinimumLizard/{name}@{commit}/{path}", params={"ref": ref},
                        http_status=200, body=body, content_type=None, fetched_at=dt.datetime.now(dt.timezone.utc),
                        origin="migration", note=f"old repo file at {commit}")
        files[(key or name, path)] = rawstore.sha256_of(body)
        n += 1
    conn.commit()
    return n


def archive_bundle(conn, store, path: Path, name: str) -> str:
    subprocess.run(["git", "bundle", "verify", str(path)], check=True, capture_output=True)
    body = path.read_bytes()
    _, sha = db.record_fetch(conn, store, source_id=f"legacy_{name.lower().replace('-', '_')}", method="GIT",
                             url=f"git-bundle://github.com/MinimumLizard/{name}", params={}, http_status=200,
                             body=body, content_type="application/x-git-bundle",
                             fetched_at=dt.datetime.now(dt.timezone.utc), origin="migration",
                             note="complete history (every branch), verified with git bundle verify", ext="bundle")
    conn.commit()
    return sha


def check_baselines(conn, store, files: dict) -> dict:
    """Recompute the audit fingerprints from the ARCHIVED bytes."""
    out = {}
    for key, expected in AUDIT_BASELINES.items():
        sha = files.get(key)
        got = rawstore.sha256_of(db.raw_bytes(conn, store, sha))[:16] if sha else None
        out["/".join(key)] = {"expected": expected, "archived": got, "ok": got == expected}
    for (name, prefix, shown), expected in GROUP_BASELINES.items():
        lines = []
        for (n, path), sha in files.items():
            if n != name or not path.startswith(prefix):
                continue
            if name == "Crypto@data" and not path.endswith(".parquet"):
                continue
            lines.append(f"{rawstore.sha256_of(db.raw_bytes(conn, store, sha))}  {shown}{path[len(prefix):]}")
        listing = "".join(line + "\n" for line in sorted(lines, key=lambda s: s.split("  ", 1)[1]))
        got = hashlib.sha256(listing.encode()).hexdigest()[:16]
        out[f"{name}/{prefix}*"] = {"expected": expected, "archived": got, "files": len(lines), "ok": got == expected}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cse", type=Path, required=True)
    ap.add_argument("--ns", type=Path, required=True)
    ap.add_argument("--crypto", type=Path, required=True)
    ap.add_argument("--bundles", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    s = settings_mod.load()
    conn = db.connect(s.database_url)
    db.migrate(conn)
    store = rawstore.from_settings(s)
    clones = {"CSE": args.cse, "Nelson-Siegel": args.ns, "Crypto": args.crypto}
    files: dict = {}
    latest: dict = {}
    counts = {}
    for key, (name, commit) in AUDITED.items():           # the audited commits: checked against the baselines
        counts[f"{key} @{commit}"] = archive_tree(conn, store, clones[name], name, commit, files, key=key)
    for key, ref in (("CSE", "HEAD"), ("Nelson-Siegel", "HEAD"), ("Crypto", "HEAD"), ("Crypto@data", "origin/data")):
        name = AUDITED[key][0]                              # and the latest state, which may be newer
        head = git(clones[name], "rev-parse", "--short", ref).decode().strip()
        if head != AUDITED[key][1]:
            counts[f"{key} @{head} (latest)"] = archive_tree(conn, store, clones[name], name, ref, latest, key=key)
    bundles = {name: archive_bundle(conn, store, args.bundles / f"{name}.bundle", name)
               for name in ("CSE", "Nelson-Siegel", "Crypto")}
    checks = check_baselines(conn, store, files)
    report = {"files_archived": counts, "bundles_sha256": bundles, "audit_baselines": checks,
              "ok": all(c["ok"] for c in checks.values()),
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
