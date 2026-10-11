"""Daily gap check:  python -m data_platform.jobs.gapcheck

For every dataset in config/datasets.yaml, list the business days (by its market's calendar) that have no data,
once the dataset's grace period has passed. Each hole is classified:

    missing               a same-market dataset has that day, so it WAS a session and data is genuinely absent
                          (this is what 2026-10-05 would have looked like)
    unconfirmed_closure   nothing at all for that day: probably a holiday not yet listed in the calendar;
                          confirm it in config/calendars/ (or treat it as missing)
    acknowledged          a known, explained hole listed in config/datasets.yaml

It writes every finding to ops.gap_checks and exits non-zero if anything is missing or unconfirmed, so the
scheduled run fails and GitHub emails the owner. It also lists sources whose terms were last checked over six
months ago (decision 0009).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..core import db, settings as settings_mod, sources
from ..core.collector import SLT
from ..core.settings import REPO_ROOT

CONFIG = REPO_ROOT / "config"


@dataclass(frozen=True)
class Calendar:
    name: str
    starts: dt.date
    closures: dict[dt.date, dict]

    def business_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        days, d = [], max(start, self.starts)
        while d <= end:
            if d.weekday() < 5 and d not in self.closures:
                days.append(d)
            d += dt.timedelta(days=1)
        return days

    def back(self, end: dt.date, n: int) -> dt.date:
        """The business day n business days before `end`."""
        d = end
        while n > 0:
            d -= dt.timedelta(days=1)
            if d.weekday() < 5 and d not in self.closures:
                n -= 1
        return d


def load_calendar(name: str, directory: Path = CONFIG / "calendars") -> Calendar:
    raw = yaml.safe_load((directory / f"{name}.yaml").read_text())
    return Calendar(raw["name"], raw["starts"], {d: v for d, v in (raw.get("closures") or {}).items()})


def load_datasets(path: Path = CONFIG / "datasets.yaml") -> dict:
    return yaml.safe_load(path.read_text())


def days_present(conn, table: str, column: str, start: dt.date, end: dt.date) -> set[dt.date]:
    return {r["d"] for r in conn.execute(
        f"select distinct {column} as d from {table} where {column} between %s and %s", (start, end))}


def check(conn, today: dt.date, datasets: dict | None = None, calendars_dir: Path = CONFIG / "calendars") -> list[dict]:
    datasets = datasets or load_datasets()
    findings = []
    for key, cfg in datasets.items():
        cal = load_calendar(cfg["calendar"], calendars_dir)
        until = cal.back(today, cfg.get("grace_days", 1))
        expected = cal.business_days(cfg["starts"], until)
        if not expected:
            continue
        have = days_present(conn, cfg["table"], cfg["date_column"], expected[0], until)
        witnessed: set[dt.date] = set()
        for w in cfg.get("witnesses", []):
            wc = datasets[w]
            witnessed |= days_present(conn, wc["table"], wc["date_column"], expected[0], until)
        acknowledged = {d: why for d, why in (cfg.get("acknowledged") or {}).items()}
        for day in expected:
            if day in have:
                continue
            if day in acknowledged:
                status, detail = "acknowledged", acknowledged[day]
            elif day in witnessed:
                status, detail = "missing", "a same-market dataset has this day, so it was a session"
            else:
                status, detail = "unconfirmed_closure", f"no data anywhere; if it was a holiday, add it to config/calendars/{cfg['calendar']}.yaml"
            findings.append({"dataset": key, "day": day, "status": status, "detail": detail})
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--today", type=dt.date.fromisoformat, help="pretend today is this date (testing)")
    args = ap.parse_args(argv)
    today = args.today or dt.datetime.now(SLT).date()
    s = settings_mod.load()
    conn = db.connect(s.database_url)
    findings = check(conn, today)
    for f in findings:
        if f["status"] != "acknowledged":
            conn.execute("insert into ops.gap_checks (dataset, day, status, detail) values (%s, %s, %s, %s)",
                         (f["dataset"], f["day"], "missing" if f["status"] == "missing" else "late", f["detail"]))
    conn.commit()
    problems = [f for f in findings if f["status"] != "acknowledged"]
    for f in findings:
        print(f"{f['status']:20s} {f['dataset']:20s} {f['day']}  {f['detail']}")
    stale = sources.stale_rights_checks(today)
    for sid in stale:
        print(f"rights check overdue  {sid}: re-read its terms and update `checked` in config/sources.yaml")
    print(f"gap check {today}: {len(problems)} problem(s), {len(findings) - len(problems)} acknowledged, "
          f"{len(stale)} overdue rights check(s)")
    return 1 if problems or stale else 0


if __name__ == "__main__":
    sys.exit(main())
