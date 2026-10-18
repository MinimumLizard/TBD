"""Run one collector:  python -m data_platform.jobs.collect <source_id>

The scheduler (GitHub Actions) calls this several times a day per source. A run that finds nothing new is a
quiet success; a run that fails exits non-zero, so GitHub emails, and Healthchecks.io notices if no run reports in.
"""
from __future__ import annotations

import argparse
import logging
import sys

from ..core import settings as settings_mod
from ..core.collector import run_collector


def registry():
    from ..collectors.cse.collector import (CseAnnouncementsCollector, CseCorporateActionsCollector,
                                            CseEndOfDayCollector, CseHistoryCollector)
    from ..collectors.pdmo.collector import PdmoCollector

    return {c.source_id + ("" if c.job == "collect" else f":{c.job}"): c
            for c in (PdmoCollector, CseEndOfDayCollector, CseAnnouncementsCollector, CseHistoryCollector,
                      CseCorporateActionsCollector)}


def main(argv: list[str] | None = None) -> int:
    collectors = registry()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("collector", choices=sorted(collectors))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_collector(collectors[args.collector], settings_mod.load())
    print(result.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
