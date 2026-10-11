"""Run the model plug-ins:  python -m data_platform.jobs.models [--market lk_bonds|cse] [--model NAME ...]

Each model is recomputed in full from the facts and its pinned dependencies (they are small, and a full recompute
can never leave half the history under old rules). The writer only touches rows whose value changed, and keeps
the old value in models.revisions. Models run in dependency order; every active version runs (the current one
the site shows, and any reference version kept beside it).

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

log = logging.getLogger(__name__)


def run(conn, names: list[str] | None = None, market: str | None = None, as_of: dt.date | None = None,
        version: str | None = None) -> list:
    manifests = registry.load_all()
    registry.publish(conn, manifests)
    owners = output_owners()
    chosen = [n for n in registry.order(manifests)
              if (not names or n in names) and (not market or manifests[n].market == market)]
    results = []
    for name in chosen:
        for v in manifests[name].active_versions:
            if version and v.method_version != version:
                continue
            results.append(run_version(conn, manifests[name], v, code_version=code_version(), as_of=as_of,
                                       owners=owners))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", action="append", help="run only this model (repeatable)")
    ap.add_argument("--market", choices=["lk_bonds", "cse"])
    ap.add_argument("--as-of", type=dt.date.fromisoformat, help="use only data up to this date")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings_mod.load()
    slug = f"models-{args.market or 'all'}".replace("_", "-")
    ping(settings, slug, "start")
    try:
        conn = db.connect(settings.database_url)
        for r in run(conn, args.model, args.market, args.as_of):
            c = r.counts
            print(f"{r.model} {r.method_version}: +{c.inserted} ~{c.updated} -{c.deleted} ={c.unchanged}")
    except BaseException:
        ping(settings, slug, "fail")
        raise
    ping(settings, slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
