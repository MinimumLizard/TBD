"""Layer 2 access: connections, the migration runner, and the one way facts are written.

Plain SQL through psycopg 3. No ORM: the SQL in db/migrations/ is the schema, and it reads like a spreadsheet's
column list. (For an R user: think DBI + raw SQL, not dbplyr.)
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .settings import REPO_ROOT

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


def connect(url: str) -> psycopg.Connection:
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return psycopg.connect(url, row_factory=dict_row, autocommit=False)


# --- migrations -----------------------------------------------------------------------------------------------

class MigrationChanged(RuntimeError):
    """An already-applied migration file was edited. Add a new numbered file instead."""


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every db/migrations/NNNN_*.sql not yet applied, in order, each in its own transaction.

    Safe to call from every job: a Postgres advisory lock makes concurrent callers wait their turn.
    """
    conn.execute("select pg_advisory_lock(727272)")
    try:
        return _migrate(conn, directory)
    finally:
        conn.execute("select pg_advisory_unlock(727272)")
        conn.commit()


def _migrate(conn: psycopg.Connection, directory: Path) -> list[str]:
    with conn.transaction():
        conn.execute("create schema if not exists ops")
        conn.execute("""create table if not exists ops.schema_migrations (
                          version text primary key, sha256 text not null,
                          applied_at timestamptz not null default now())""")
    applied = {r["version"]: r["sha256"] for r in conn.execute("select version, sha256 from ops.schema_migrations")}
    done = []
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        sql = path.read_text()
        digest = hashlib.sha256(sql.encode()).hexdigest()
        version = path.stem
        if version in applied:
            if applied[version] != digest:
                raise MigrationChanged(f"{path.name} was changed after it was applied; add a new migration instead")
            continue
        with conn.transaction():
            conn.execute(sql)
            conn.execute("insert into ops.schema_migrations (version, sha256) values (%s, %s)", (version, digest))
        done.append(version)
    return done


# --- writing facts -------------------------------------------------------------------------------------------

def _jsonable(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _same(a, b) -> bool:
    """Equality for stored-vs-incoming comparison (numbers compare as floats; dates as dates)."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float, decimal.Decimal)) and isinstance(b, (int, float, decimal.Decimal)):
        return float(a) == float(b)
    if isinstance(a, dt.datetime) and isinstance(b, dt.datetime):
        return a == b
    if isinstance(a, dt.date) and isinstance(b, str):
        return a.isoformat() == b
    return a == b


def insert_facts(conn: psycopg.Connection, table: str, rows: Sequence[dict], key: Sequence[str],
                 compare_ignore: Iterable[str] = ("fetch_id", "fetched_at", "ingested_at", "list_fetch_id",
                                                  "detail_fetch_id"),
                 fetch_id: int | None = None) -> tuple[int, int]:
    """Append rows; never overwrite. Returns (rows added, conflicts recorded).

    A row whose key already exists is not written. If its values differ from the stored ones, the difference
    is recorded in ops.value_conflicts so a person can decide; history itself is untouched.
    """
    if not rows:
        return 0, 0
    cols = list(rows[0].keys())
    ignore = set(compare_ignore)
    placeholders = ", ".join(["%s"] * len(cols))
    col_sql = ", ".join(cols)
    key_sql = ", ".join(key)
    added = conflicts = 0
    for row in rows:
        cur = conn.execute(
            f"insert into {table} ({col_sql}) values ({placeholders}) on conflict ({key_sql}) do nothing",
            [row[c] for c in cols])
        if cur.rowcount == 1:
            added += 1
            continue
        where = " and ".join(f"{k} = %s" for k in key)
        stored = conn.execute(f"select * from {table} where {where}", [row[k] for k in key]).fetchone()
        # A blank incoming value is "not provided in this response", not a disagreement: e.g. the CSE repeats the
        # previous session but cannot give that session's change. Only a different, non-blank value is a conflict.
        diff = {c: (stored.get(c), row[c]) for c in cols
                if c not in ignore and row[c] is not None and not _same(stored.get(c), row[c])}
        if diff:
            conn.execute(
                "insert into ops.value_conflicts (table_name, key, stored, incoming, fetch_id) values (%s,%s,%s,%s,%s)",
                (table, Jsonb({k: _jsonable(row[k]) for k in key}),
                 Jsonb({c: _jsonable(v[0]) for c, v in diff.items()}),
                 Jsonb({c: _jsonable(v[1]) for c, v in diff.items()}), fetch_id))
            conflicts += 1
    return added, conflicts


# --- the raw archive catalogue ----------------------------------------------------------------------------------

def record_fetch(conn: psycopg.Connection, store, *, source_id: str, method: str, url: str, params: dict | None,
                 http_status: int, body: bytes, content_type: str | None, fetched_at: dt.datetime,
                 run_id: int | None = None, origin: str = "live", note: str | None = None,
                 ext: str | None = None) -> tuple[int, str]:
    """Archive `body` (layer 1) and catalogue the request (ops.raw_fetches). Returns (fetch_id, sha256).

    Called for every response BEFORE it is parsed: store first, parse second (architecture §2).
    Migration records (origin 'migration' / 're-download') are idempotent: replaying the same file again reuses
    its existing catalogue entry, so a repeated migration adds nothing anywhere.
    """
    from .rawstore import sniff_ext

    ext = ext or sniff_ext(body, content_type)
    obj = store.put(body, ext)
    conn.execute("""insert into ops.raw_objects (sha256, bytes, content_type, ext, storage_key)
                    values (%s, %s, %s, %s, %s) on conflict (sha256) do nothing""",
                 (obj.sha256, obj.bytes, content_type, obj.ext, obj.key))
    if origin != "live":
        existing = conn.execute(
            """select fetch_id from ops.raw_fetches where source_id = %s and url = %s and params = %s
               and sha256 = %s and origin = %s and note is not distinct from %s limit 1""",
            (source_id, url, Jsonb(params or {}), obj.sha256, origin, note)).fetchone()
        if existing:
            return existing["fetch_id"], obj.sha256
    fetch_id = conn.execute(
        """insert into ops.raw_fetches (source_id, run_id, method, url, params, http_status, fetched_at, sha256,
                                        origin, note)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning fetch_id""",
        (source_id, run_id, method, url, Jsonb(params or {}), http_status, fetched_at, obj.sha256, origin, note),
    ).fetchone()["fetch_id"]
    return fetch_id, obj.sha256


def raw_bytes(conn: psycopg.Connection, store, sha256: str) -> bytes:
    ext = conn.execute("select ext from ops.raw_objects where sha256 = %s", (sha256,)).fetchone()["ext"]
    return store.get(sha256, ext)


def to_json(obj) -> str:
    return json.dumps(obj, default=_jsonable, sort_keys=True)
