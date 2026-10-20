"""Store the owner's confirmations in the database:  python -m data_platform.jobs.reviews

Two kinds: corporate actions (below) and ownership (sync_ownership: config/ownership_aliases.yaml,
config/ownership_parents.yaml and the private file named by OWNERSHIP_PRIVATE_FILE, stored in
cse.ownership_confirmations for the cse_ownership model, the same way).

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
import os
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


# --- the owner's ownership confirmations (cse_ownership) ---------------------------------------------------------

ALIASES_FILE = REPO_ROOT / "config" / "ownership_aliases.yaml"
PARENTS_FILE = REPO_ROOT / "config" / "ownership_parents.yaml"
PRIVATE_ENV = "OWNERSHIP_PRIVATE_FILE"
ALIAS_FIELDS = {"variants", "type", "symbol"}
PARENT_FIELDS = {"owner", "owner_type", "pct", "source", "quote", "note"}
PERSONAL_TYPES = {"individual", "joint", "estate", "trust"}   # may name a private person: private file only


def _ownership_sections(data, name: str) -> tuple[dict, dict]:
    if not isinstance(data, dict) or set(data) - {"aliases", "parents"}:
        raise ValueError(f"{name}: expected only `aliases` and `parents`")
    aliases = {str(k): dict(v or {}) for k, v in (data.get("aliases") or {}).items()}
    parents = {str(k): {f: _plain(x) for f, x in (v or {}).items()} for k, v in (data.get("parents") or {}).items()}
    unknown = ({f for v in aliases.values() for f in v} - ALIAS_FIELDS) | ({f for v in parents.values() for f in v}
                                                                         - PARENT_FIELDS)
    if unknown:
        raise ValueError(f"{name}: unknown fields {sorted(unknown)}")
    for k, v in aliases.items():
        if not isinstance(v.get("variants", []), list):
            raise ValueError(f"{name}: '{k}' variants must be a list")
    return aliases, parents


def read_public(aliases_path: Path = ALIASES_FILE, parents_path: Path = PARENTS_FILE) -> tuple[dict, str]:
    """The repository's two files. They are PUBLIC, so an entry that could name a private individual is refused: an
    alias whose type (given, or as the tracker would classify the name) is individual, joint, estate or trust, and a
    parent whose owner is one."""
    from ..models._lib import cse_names

    a_body = aliases_path.read_bytes() if aliases_path.exists() else b""
    p_body = parents_path.read_bytes() if parents_path.exists() else b""
    aliases, _ = _ownership_sections(yaml.safe_load(a_body) or {}, aliases_path.name)
    _, parents = _ownership_sections(yaml.safe_load(p_body) or {}, parents_path.name)
    for name, spec in aliases.items():
        typ = spec.get("type") or cse_names.classify(name, {})[0]
        if typ in PERSONAL_TYPES:
            raise ValueError(f"{aliases_path.name}: '{name}' is of type {typ}; it may name a private individual, so it "
                             f"belongs in the private file ({PRIVATE_ENV}), not in the public repository")
    for holder, spec in parents.items():
        typ = spec.get("owner_type") or cse_names.classify(str(spec.get("owner", "")), {})[0]
        if typ in PERSONAL_TYPES:
            raise ValueError(f"{parents_path.name}: the owner of '{holder}' is of type {typ}; it belongs in the "
                             f"private file ({PRIVATE_ENV}), not in the public repository")
    return {"aliases": aliases, "parents": parents}, hashlib.sha256(a_body + b"\x00" + p_body).hexdigest()


def read_private(path: Path) -> tuple[dict, str]:
    body = path.read_bytes()
    aliases, parents = _ownership_sections(yaml.safe_load(body) or {}, PRIVATE_ENV)
    return {"aliases": aliases, "parents": parents}, hashlib.sha256(body).hexdigest()


def sync_ownership(conn, aliases_path: Path = ALIASES_FILE, parents_path: Path = PARENTS_FILE,
                   private_path: Path | None | str = "env", code_version: str | None = None,
                   commit: bool = True) -> int | None:
    """Store the confirmations if they differ from the last version stored. Returns the new version_id or None.
    private_path "env" (the default) reads OWNERSHIP_PRIVATE_FILE; when there is none, the last stored private part
    is kept, so a run without the private file never undoes the owner's confirmations."""
    public, public_sha = read_public(aliases_path, parents_path)
    if private_path == "env":
        private_path = Path(os.environ[PRIVATE_ENV]) if os.environ.get(PRIVATE_ENV) else None
    last = conn.execute("""select private_sha256, private from cse.ownership_confirmations
                           order by version_id desc limit 1""").fetchone()
    if private_path is not None:
        private, private_sha = read_private(Path(private_path))
    elif last:
        private, private_sha = last["private"], last["private_sha256"]
    else:
        private, private_sha = {"aliases": {}, "parents": {}}, None
    return store_ownership(conn, public, public_sha, private, private_sha, code_version, commit)


def store_ownership(conn, public: dict, public_sha: str, private: dict, private_sha: str | None,
                    code_version: str | None = None, commit: bool = True) -> int | None:
    last = conn.execute("""select public_sha256, private_sha256 from cse.ownership_confirmations
                           order by version_id desc limit 1""").fetchone()
    if last and last["public_sha256"] == public_sha and last["private_sha256"] == private_sha:
        return None
    version = conn.execute(
        """insert into cse.ownership_confirmations (public_sha256, public, private_sha256, private, code_version)
           values (%s, %s, %s, %s, %s) returning version_id""",
        (public_sha, Jsonb(public), private_sha, Jsonb(private), code_version or current_code_version())
    ).fetchone()["version_id"]
    if commit:
        conn.commit()
    return version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", type=Path, default=REVIEW_FILE)
    args = ap.parse_args(argv)
    conn = db.connect(settings_mod.load().database_url)
    version = sync(conn, args.file)
    print(f"corporate actions: stored as version {version}" if version else
          "corporate actions: unchanged (the latest stored version is this file)")
    version = sync_ownership(conn)
    print(f"ownership: stored as version {version}" if version else "ownership: unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
