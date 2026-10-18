"""Bitstamp daily candles:  python -m data_platform.jobs.collect bitstamp

For each pair in parse.PAIRS: find the last stored day, ask Bitstamp for the days after it, one 1000-day window at a
time (1,000 days per request; the shared client keeps at least a second between requests), archive every
response before parsing it, and store only the UTC days that had ended when the response was fetched.

  * First run: a full backfill from 2011-09-14, the first day of Bitstamp's BTC/USD history. A pair listed later
    (ETH/USD on 2017-08-16, for example) returns empty windows until its listing; they are skipped.
  * Later runs: incremental from the day after the last stored one. A run after 00:10 UTC finds yesterday final.
  * Idempotent: a day already stored is never written again (crypto.ohlc_daily is append-only); a re-fetched day
    that disagrees is recorded in ops.value_conflicts, not written over the stored one.
  * Fails loudly: a pair that has history but returns nothing for days that should be complete fails the run (after
    the other pairs are stored), so a delisting or an outage is noticed rather than becoming a silent gap.

Bitstamp's terms need a signed Data License Agreement for commercial use (config/sources.yaml: permission_required).
"""
from __future__ import annotations

import datetime as dt

from ...core import db
from ...core.collector import Collector, Result
from . import parse

API = "https://www.bitstamp.net/api/v2/ohlc/{pair}/"
HISTORY_START = dt.date(2011, 9, 14)
WINDOW_DAYS = 1000


def store(conn, rows: list[dict], fetch_id: int, sha256: str, fetched_at: dt.datetime) -> tuple[int, int]:
    """Append candles. Returns (rows added, conflicts recorded)."""
    rows = [dict(r, raw_sha256=sha256, fetch_id=fetch_id, fetched_at=fetched_at) for r in rows]
    return db.insert_facts(conn, "crypto.ohlc_daily", rows, key=["pair", "day"], fetch_id=fetch_id,
                           compare_ignore=("fetch_id", "fetched_at", "ingested_at", "raw_sha256"))


class BitstampCollector(Collector):
    source_id = "bitstamp"
    job = "collect"
    pairs: tuple[str, ...] = tuple(parse.PAIRS)

    def collect(self) -> Result:
        until = parse.last_complete_day(self.ctx.now)
        added, notes, failed = 0, [], []
        for pair in self.pairs:
            try:
                n, note = self.collect_pair(pair, until)
                self.ctx.conn.commit()
                added += n
                if note:
                    notes.append(note)
            except Exception as exc:  # noqa: BLE001 - one pair failing never stops the others; raised at the end
                self.ctx.conn.rollback()
                failed.append(f"{pair} ({type(exc).__name__}: {exc})"[:300])
        message = f"{added} daily candles added up to {until} ({self.fetches} requests)"
        if notes:
            message += "; " + "; ".join(notes)
        if failed:
            raise RuntimeError(f"{message}; {len(failed)} pair(s) failed: " + "; ".join(failed))
        return Result(rows_added=added, new_data=bool(added), message=message)

    def collect_pair(self, pair: str, until: dt.date) -> tuple[int, str]:
        conn = self.ctx.conn
        last = conn.execute("select max(day) d from crypto.ohlc_daily where pair = %s", (pair,)).fetchone()["d"]
        start = last + dt.timedelta(days=1) if last else HISTORY_START
        has_history = last is not None
        added = conflicts = 0
        while start <= until:
            f = self.fetch("GET", API.format(pair=pair),
                           {"step": parse.DAY_SECONDS, "limit": WINDOW_DAYS, "start": parse.unix(start)}, note=pair)
            rows = parse.parse_ohlc(f.body, pair)
            window_end = start + dt.timedelta(days=WINDOW_DAYS)
            if any(r["day"] < start or r["day"] >= window_end for r in rows):
                raise parse.BitstampFormatError(f"{pair}: candles outside the window asked for ({start} to {window_end})")
            final = [r for r in parse.complete(rows, f.response.fetched_at) if r["day"] <= until]
            if not final and has_history:
                raise RuntimeError(f"no candles from {start}, although days up to {until} should be complete")
            if final:
                n, c = store(conn, final, f.fetch_id, f.sha256, f.response.fetched_at)
                added, conflicts = added + n, conflicts + c
                conn.commit()      # each window is whole days in order, so a later failure resumes from here
                has_history = True
            start = window_end
        span = conn.execute("""select min(day) first, max(day) last, count(*) n from crypto.ohlc_daily
                               where pair = %s""", (pair,)).fetchone()
        if span["last"] is None:
            raise RuntimeError(f"Bitstamp returned no candles at all from {HISTORY_START} to {until}")
        if span["last"] < until:
            raise RuntimeError(f"the latest candle is for {span['last']}, but days up to {until} should be complete")
        note = []
        missing = (span["last"] - span["first"]).days + 1 - span["n"]
        if missing:
            note.append(f"{pair}: {missing} day(s) without a candle between {span['first']} and {span['last']}")
        if conflicts:
            note.append(f"{pair}: {conflicts} re-fetched day(s) differ from the stored ones (ops.value_conflicts)")
        return added, "; ".join(note)
