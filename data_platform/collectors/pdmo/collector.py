"""PDMO collector: index pages → files → archive → facts.

    python -m data_platform.jobs.collect pdmo

Each run:
  1. reads the four index pages for every year from 2025 to the current year (derived from the date: the old
     pipeline's typed-in years would have stopped collection on 1 January 2027, audit F1);
  2. fetches every listed file not yet parsed by the current parser version, archives it, parses it and stores
     its rows as published;
  3. fails loudly when an index page that should list files lists none (the page changed shape, or a firewall
     answered in its place), or when a newly fetched file cannot be parsed.
"""
from __future__ import annotations

import datetime as dt
import logging

from ...core import db
from ...core.collector import Collector, Result
from . import index
from .errors import ParseError
from .facts import PARSER_VERSION, parse_file

log = logging.getLogger(__name__)

BASE = "https://www.treasury.gov.lk"
FIRST_YEAR = 2025          # the PDMO publishes nothing older in these sections (audit §3.2)
INDEX_PAGES = [
    ("daily", "/web/report-daily-report/section/{year}", index.parse_daily_index),
    ("trade-summary", "/web/reports-secondary-market-trade-summary/section/{year}", index.parse_trade_summary_index),
    ("bond-issuance", "/web/treasury-bonds-issuances/section/{year}", index.parse_issuance_index),
    ("bond-auction", "/web/result-treasury-bonds/section/{year}", index.parse_auction_index),
]
# Announcements and auction results first (they teach series labels), then volumes, trades, quotes; oldest first,
# so an amended report is stored after its original.
KIND_ORDER = {"bond_issuance": 0, "bond_auction": 1, "volumes": 2, "trade_summary": 3, "daily_summary": 4}


def index_years(today: dt.date) -> range:
    return range(FIRST_YEAR, today.year + 1)


def store_file(conn, *, entry: index.IndexEntry, index_year: int, fetch_id: int, sha256: str,
               fetched_at: dt.datetime, body: bytes) -> tuple[str, int]:
    """Parse one archived file and append its facts. Shared by the live collector and the migration.

    Returns (parse_status, rows added). A parse failure is recorded against the file, not raised.
    """
    try:
        parsed = parse_file(entry.kind, body, entry.label_date)
        status, note = "ok", parsed.note
    except ParseError as exc:
        parsed, status, note = None, "failed", str(exc)
    except Exception as exc:  # noqa: BLE001 - an unexpected parser crash is recorded the same way, with its type
        parsed, status, note = None, "failed", f"{type(exc).__name__}: {exc}"

    added = 0
    if parsed is not None:
        rows = [dict(r, raw_sha256=sha256, parser_version=PARSER_VERSION, fetched_at=fetched_at)
                for r in parsed.rows]
        added, _ = db.insert_facts(conn, parsed.table, rows, key=["raw_sha256", "parser_version", "row_no"],
                                   fetch_id=fetch_id)
    db.insert_facts(conn, "bonds.source_files", [{
        "url": entry.url, "raw_sha256": sha256, "fetch_id": fetch_id, "parser_version": PARSER_VERSION,
        "kind": entry.kind, "index_year": index_year, "posted_date": entry.posted_date,
        "label_date": entry.label_date, "amended": entry.amended,
        "report_date": parsed.report_date if parsed else None,
        "trading_date": parsed.trading_date if parsed else None,
        "parse_status": status, "parse_note": note[:1000], "rows_parsed": len(parsed.rows) if parsed else 0,
    }], key=["url", "raw_sha256", "parser_version"], fetch_id=fetch_id)
    return status, added


class PdmoCollector(Collector):
    source_id = "pdmo"

    def read_indexes(self) -> tuple[list[tuple[index.IndexEntry, int]], list[str]]:
        today = self.ctx.today_slt
        entries: list[tuple[index.IndexEntry, int]] = []
        seen: set[str] = set()
        problems, attempted, failed = [], 0, 0
        for label, path, parse in INDEX_PAGES:
            for year in index_years(today):
                attempted += 1
                url = BASE + path.format(year=year)
                try:
                    page = self.fetch("GET", url, note=f"{label} index {year}")
                    found = parse(page.body)
                except Exception as exc:  # noqa: BLE001 - one unreachable page must not stop the others
                    failed += 1
                    log.warning("%s index %s unreachable: %s", label, year, exc)
                    continue
                if not found:
                    # A brand-new year's page is empty until its first posting; anything else listing nothing has
                    # changed shape, or something answered in its place. Never treat that as "no news".
                    if year == today.year and today.timetuple().tm_yday <= 31:
                        log.info("%s index %s is empty (new year, expected)", label, year)
                    else:
                        failed += 1
                        problems.append(f"{label} index {year} listed ZERO files")
                    continue
                for entry in found:
                    if entry.url not in seen:
                        seen.add(entry.url)
                        entries.append((entry, year))
        if attempted and failed == attempted:
            raise RuntimeError(f"all {attempted} PDMO index pages were unreachable or empty")
        entries.sort(key=lambda e: (KIND_ORDER[e[0].kind], e[0].posted_date or e[0].label_date or dt.date.min))
        return entries, problems

    def collect(self) -> Result:
        conn = self.ctx.conn
        entries, problems = self.read_indexes()
        # Done = parsed successfully by the current parser. A file whose parse failed is fetched again on the next run
        # (the PDMO sometimes serves an error page or a truncated file, then the real one at the same address).
        known = {r["url"] for r in conn.execute(
            "select distinct url from bonds.source_files where parser_version = %s and parse_status = 'ok'",
            (PARSER_VERSION,))}
        todo = [(e, y) for e, y in entries if e.url not in known]
        added = parsed_ok = 0
        failures, unreachable = [], []
        for entry, year in todo:
            try:
                got = self.fetch("GET", entry.url, note=entry.kind)
            except Exception as exc:  # noqa: BLE001 - one dead link must not block every file listed after it
                conn.rollback()
                unreachable.append(f"{entry.url} ({type(exc).__name__}: {exc})"[:300])
                continue
            status, n = store_file(conn, entry=entry, index_year=year, fetch_id=got.fetch_id, sha256=got.sha256,
                                   fetched_at=got.response.fetched_at, body=got.body)
            conn.commit()
            added += n
            if status == "ok":
                parsed_ok += 1
            else:
                failures.append(entry.url)
        message = (f"{len(entries)} files listed, {len(todo)} new, {parsed_ok} parsed ok, {len(failures)} failed, "
                   f"{len(unreachable)} unreachable; {added} rows added")
        if problems or failures or unreachable:
            raise RuntimeError(message + ". Problems: " + "; ".join(
                problems + [f"parse failed: {u}" for u in failures] + [f"download failed: {u}" for u in unreachable]))
        return Result(rows_added=added, message=message, new_data=bool(todo))
