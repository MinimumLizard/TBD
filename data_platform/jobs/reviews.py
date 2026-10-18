"""Store the owner's corporate-action confirmations in the database:  python -m data_platform.jobs.reviews

config/corporate_actions_review.yaml is the owner's file, in the old terminal's format: `confirm` accepts a row that
needs review (optionally correcting fields), `reject` ignores a row. Models never read files, so the models job
calls sync() before every run: if the file differs from the version stored last, its new version is added to
cse.corporate_action_reviews (append-only, with the file's SHA-256 and the git commit it was read at). The
cse_corporate_actions model reads the latest version, so a changed confirmation changes the outputs on the next
run, every version stays on record, and each model run's input fingerprint names the version it used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

import yaml
from psycopg.types.json import Jsonb

from ..core import db, settings as settings_mod
from ..core.collector import code_version as current_code_version
from ..core.settings import REPO_ROOT

REVIEW_FILE = REPO_ROOT / "config" / "corporate_actions_review.yaml"
FIELDS = {"id", "symbol", "type", "ex_date", "amount_per_share", "ratio_new", "ratio_held", "factor",
          "subscription_price", "status", "note", "source_url"}


def _plain(v):
    return v.isoformat()[:10] if isinstance(v, (dt.date, dt.datetime)) else v


def read(path: Path = REVIEW_FILE) -> tuple[dict, list, str]:
    """(confirm, reject, sha256 of the file). The same checks as the old terminal's load_reviews: unknown fields
    are an error, never ignored. YAML dates (ex_date: 2026-04-02) are kept as the ISO text they were written as."""
    body = path.read_bytes() if path.exists() else b""
    data = yaml.safe_load(body) or {}
    if not isinstance(data, dict) or set(data) - {"confirm", "reject"}:
        raise ValueError(f"{path.name}: expected only `confirm` and `reject`")
    confirm = {str(k): {f: _plain(v) for f, v in (fields or {}).items()} for k, fields in (data.get("confirm") or {}).items()}
    unknown = {f for fields in confirm.values() for f in fields} - FIELDS
    if unknown:
        raise ValueError(f"{path.name}: unknown fields {sorted(unknown)}")
    reject = sorted({str(x) for x in (data.get("reject") or [])})
    return confirm, reject, hashlib.sha256(body).hexdigest()


def sync(conn, path: Path = REVIEW_FILE, code_version: str | None = None, commit: bool = True) -> int | None:
    """Add the file's current version if it differs from the last one stored. Returns the new version_id, or None
    when nothing changed. Commits, unless commit=False (parity runs, which roll back)."""
    confirm, reject, sha = read(path)
    return store(conn, confirm, reject, sha, path, code_version, commit)


def store(conn, confirm: dict, reject: list, sha: str, path: Path, code_version: str | None = None,
          commit: bool = True) -> int | None:
    last = conn.execute("select file_sha256 from cse.corporate_action_reviews order by version_id desc limit 1").fetchone()
    if last and last["file_sha256"] == sha:
        return None
    try:
        source = str(path.relative_to(REPO_ROOT))
    except ValueError:
        source = str(path)
    version = conn.execute(
        """insert into cse.corporate_action_reviews (file_sha256, source_path, confirm, reject, code_version)
           values (%s, %s, %s, %s, %s) returning version_id""",
        (sha, source, Jsonb(confirm), Jsonb(reject), code_version or current_code_version())).fetchone()["version_id"]
    if commit:
        conn.commit()
    return version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", type=Path, default=REVIEW_FILE)
    args = ap.parse_args(argv)
    conn = db.connect(settings_mod.load().database_url)
    version = sync(conn, args.file)
    print(f"stored as version {version}" if version else "unchanged: the latest stored version is this file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
