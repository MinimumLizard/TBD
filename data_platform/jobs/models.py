"""Run the model plug-ins:  python -m data_platform.jobs.models [--market lk_bonds|cse|lk_savings] [--model NAME ...]

Each model is recomputed in full from the facts and its pinned dependencies (they are small, and a full recompute
can never leave half the history under old rules). The writer only touches rows whose value changed, and keeps
the old value in models.revisions. Models run in dependency order; every active version runs (the current one
the site shows, and any reference version kept beside it).

Before computing, the owner's corporate-action confirmations (config/corporate_actions_review.yaml) are stored in
the database if they changed (data_platform.jobs.reviews): models read only the database.

Scheduled after the collectors. A failure exits non-zero and pings Healthchecks.io's fail URL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from ..core import db, settings as settings_mod
from ..core.collector import code_version, ping
from ..models import registry
from ..models.framework import output_owners, run_version
from . import reviews

log = logging.getLogger(__name__)


def run(conn, names: list[str] | None = None, market: str | None = None, version: str | None = None) -> list:
    """Every active version of every chosen model, dependencies first and, within a model, the version the site
    shows first. A failure is recorded and the run carries on with everything that does not depend on it; the job
    then fails at the end, naming every failure."""
    manifests = registry.load_all()
    registry.publish(conn, manifests)
    reviews.sync(conn)          # the owner's corporate-action confirmations, as the repository has them now
    owners = output_owners()
    chosen = [n for n in registry.order(manifests)
              if (not names or n in names) and (not market or manifests[n].market == market)]
    results, failures, failed = [], [], set()
    for name in chosen:
        versions = sorted(manifests[name].active_versions, key=lambda v: v.status != "current")
        for v in versions:
            if version and v.method_version != version:
                continue
            blocked = [f"{d} {dv}" for d, dv in v.requires_models.items() if (d, dv) in failed]
            if blocked:
                failed.add((name, v.method_version))
                failures.append(f"{name} {v.method_version}: skipped, needs {', '.join(blocked)}")
                continue
            try:
                r = run_version(conn, manifests[name], v, code_version=code_version(), owners=owners)
            except Exception as exc:  # noqa: BLE001 - recorded on the run row; reported at the end
                failed.add((name, v.method_version))
                failures.append(f"{name} {v.method_version}: {type(exc).__name__}: {exc}"[:500])
                log.exception("%s %s failed", name, v.method_version)
                continue
            results.append(r)
            if r.message:
                failures.append(f"{name} {v.method_version}: {r.message}")
    if failures:
        raise ModelRunFailed(failures, results)
    return results


class ModelRunFailed(RuntimeError):
    def __init__(self, failures: list[str], results: list):
        super().__init__(f"{len(failures)} model run problem(s): " + " | ".join(failures))
        self.failures, self.results = failures, results


def compute_as_of(conn, as_of: dt.date, names: list[str] | None = None, market: str | None = None) -> dict:
    """What the current versions would have produced with data up to `as_of`. Computed in memory; never written."""
    from ..migration.parity import run_chain

    manifests = registry.load_all()
    chosen = [n for n in registry.order(manifests)
              if (not names or n in names) and (not market or manifests[n].market == market)]
    needed = set(chosen)
    for n in list(chosen):        # dependencies of the current versions must be computed too
        stack = [n]
        while stack:
            for dep in manifests[stack.pop()].current.requires_models:
                if dep not in needed:
                    needed.add(dep)
                    stack.append(dep)
    outputs = run_chain(conn, sorted(needed), as_of=as_of, pick=lambda m: m.current)
    conn.rollback()
    return {table: len(rows) for table, rows in outputs.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", action="append", help="run only this model (repeatable)")
    ap.add_argument("--market", choices=["lk_bonds", "cse", "lk_savings", "crypto"])
    ap.add_argument("--as-of", type=dt.date.fromisoformat,
                    help="compute the current versions with data up to this date, in memory, and print row counts "
                         "(never writes: writing would delete every later row)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings_mod.load()
    conn = db.connect(settings.database_url)
    if args.as_of:   # a look at the past: no pings, no writes
        for table, n in compute_as_of(conn, args.as_of, args.model, args.market).items():
            print(f"{table}: {n} rows as of {args.as_of} (not written)")
        return 0
    slug = f"models-{args.market or 'all'}".replace("_", "-")
    ping(settings, slug, "start")
    try:
        results = run(conn, args.model, args.market)
    except ModelRunFailed as exc:
        _report(exc.results)
        for f in exc.failures:
            print(f"FAILED {f}")
        ping(settings, slug, "fail")
        return 1
    except BaseException:
        ping(settings, slug, "fail")
        raise
    _report(results)
    ping(settings, slug)
    return 0


def _report(results) -> None:
    for r in results:
        c = r.counts
        print(f"{r.model} {r.method_version}: +{c.inserted} ~{c.updated} -{c.deleted} ={c.unchanged}")


if __name__ == "__main__":
    sys.exit(main())
