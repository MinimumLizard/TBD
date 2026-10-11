"""Apply database migrations:  python -m data_platform.jobs.migrate

Every scheduled job runs this first. It is idempotent, waits for any concurrent run, and refuses to continue if an
already-applied migration file was edited (add a new numbered file instead).
"""
from __future__ import annotations

import sys

from ..core import db, settings as settings_mod


def main() -> int:
    conn = db.connect(settings_mod.load().database_url)
    applied = db.migrate(conn)
    print(f"migrations applied: {applied or 'none (up to date)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
