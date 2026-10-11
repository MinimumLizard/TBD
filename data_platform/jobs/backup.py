"""Backups (decisions 0003, 0004):

    python -m data_platform.jobs.backup replicate   # nightly: copy every archived object to the second store (B2)
    python -m data_platform.jobs.backup export      # nightly: pg_dump of the database to BOTH stores, write-once
    python -m data_platform.jobs.backup verify      # monthly: re-read a random sample from both stores, check hashes

Every copy is verified by fingerprint after it is written. A mismatch is an error, never a warning.

Retention: raw objects (raw/...) are kept forever (R2 bucket lock on the raw/ prefix). Database exports
(exports/db/...) are kept 90 days by a bucket lifecycle rule, so the lock must not cover them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import subprocess
import sys

from ..core import db, rawstore, settings as settings_mod
from ..core.rawstore import IntegrityError, sha256_of


def replicate(conn, primary, secondary) -> dict:
    copied = present = 0
    for r in conn.execute("select sha256, ext from ops.raw_objects order by first_stored_at"):
        if secondary.exists(r["sha256"], r["ext"]):
            present += 1
            continue
        data = primary.get(r["sha256"], r["ext"])           # get() verifies the primary copy's fingerprint
        secondary.put(data, r["ext"])
        if sha256_of(secondary.get(r["sha256"], r["ext"])) != r["sha256"]:
            raise IntegrityError(f"{r['sha256']}: second copy does not match after writing")
        copied += 1
    return {"copied": copied, "already_present": present}


def export_key(day: dt.date) -> str:
    return f"exports/db/{day.isoformat()}.dump"


def export(database_url: str, stores: list, today: dt.date, dump_fn=None) -> dict:
    """pg_dump in Postgres' custom format (restorable with pg_restore) to exports/db/<date>.dump in every store.

    Write-once per day. A re-run on the same day (e.g. after the second store failed) does not dump again: it copies
    the day's existing export to any store still missing it. Every copy is read back and checked."""
    key = export_key(today)
    existing = next((s for s in stores if s.has_key(key)), None)
    if existing is not None:
        dump = existing.get_named(key)
    else:
        dump = (dump_fn or _pg_dump)(database_url)
    digest = sha256_of(dump)
    for store in stores:
        if not store.has_key(key):
            store.put_named(key, dump)
        if sha256_of(store.get_named(key)) != digest:
            raise IntegrityError(f"{key}: a stored copy does not match the export")
    return {"key": key, "bytes": len(dump), "sha256": digest, "reused": existing is not None}


def _pg_dump(database_url: str) -> bytes:
    return subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", database_url],
                          check=True, capture_output=True).stdout


def verify(conn, stores: list, today: dt.date, sample: int = 200, seed: int | None = None) -> dict:
    """Re-read a random sample of archived objects from every store, and check each store holds a recent export.
    An empty archive, or no export in the last two days, is a failure, not a pass."""
    rows = conn.execute("select sha256, ext from ops.raw_objects").fetchall()
    if not rows:
        raise IntegrityError("the archive catalogue is empty: nothing to verify")
    picked = random.Random(seed).sample(rows, min(sample, len(rows)))
    for r in picked:
        for store in stores:
            store.get(r["sha256"], r["ext"])                # raises IntegrityError on any mismatch
    for i, store in enumerate(stores):
        if not any(store.has_key(export_key(today - dt.timedelta(days=d))) for d in range(3)):
            raise IntegrityError(f"store {i + 1} holds no database export from the last two days")
    return {"checked": len(picked), "stores": len(stores)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=["replicate", "export", "verify"])
    args = ap.parse_args(argv)
    s = settings_mod.load()
    conn = db.connect(s.database_url)
    primary, secondary = rawstore.from_settings(s), rawstore.from_settings(s, secondary=True)
    if args.action == "replicate":
        result = replicate(conn, primary, secondary)
    elif args.action == "export":
        result = export(s.database_url, [primary, secondary], dt.date.today())
    else:
        result = verify(conn, [primary, secondary], dt.date.today())
    print(args.action, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
