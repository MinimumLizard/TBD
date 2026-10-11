"""Backups (decisions 0003, 0004):

    python -m data_platform.jobs.backup replicate   # nightly: copy every archived object to the second store (B2)
    python -m data_platform.jobs.backup export      # nightly: pg_dump of the database to BOTH stores, write-once
    python -m data_platform.jobs.backup verify      # monthly: re-read a random sample from both stores, check hashes

Every copy is verified by fingerprint after it is written. A mismatch is an error, never a warning.
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


def export(database_url: str, stores: list, today: dt.date) -> dict:
    """pg_dump in Postgres' custom format (restorable with pg_restore) to exports/db/<date>.dump in every store."""
    dump = subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", database_url],
                          check=True, capture_output=True).stdout
    key = f"exports/db/{today.isoformat()}.dump"
    for store in stores:
        store.put_named(key, dump)
    return {"key": key, "bytes": len(dump), "sha256": sha256_of(dump)}


def verify(conn, stores: list, sample: int = 200, seed: int | None = None) -> dict:
    rows = conn.execute("select sha256, ext from ops.raw_objects").fetchall()
    picked = random.Random(seed).sample(rows, min(sample, len(rows)))
    for r in picked:
        for store in stores:
            store.get(r["sha256"], r["ext"])                # raises IntegrityError on any mismatch
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
        result = verify(conn, [primary, secondary])
    print(args.action, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
