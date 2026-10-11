"""CSE collectors.

    python -m data_platform.jobs.collect cse_api                 # end of day: the session's prices, indices, market
    python -m data_platform.jobs.collect cse_api:announcements   # disclosures (every couple of hours)
    python -m data_platform.jobs.collect cse_api:history         # weekly: one-year chart history, fills any missed day

Rules carried over from the old terminal (audit §2.1), all enforced here:
  * the session date comes from the API (dailyMarketSummery), never from the clock;
  * a session already stored is "no new data"; an API session OLDER than the stored one is an error;
  * an open market is never snapshotted; tradeSummary must be for the same session.
What is new:
  * every response is archived before parsing (the old job kept raw files in git, which grows forever);
  * per-company snapshots for every ordinary share, not only a personal watchlist;
  * the weekly history job repairs missed sessions automatically (prices only: the chart has no turnover),
    because a missed daily run was otherwise a permanent gap (audit F4: 2026-10-05).
"""
from __future__ import annotations

import datetime as dt

from ...core import db
from ...core.collector import Collector, Fetched, Result
from . import parse

API = "https://www.cse.lk/api/"
GET_ENDPOINTS = frozenset({"allSecurityCode", "cntSecurity", "lastUpdateTime", "previousUpdateTime",
                           "corporateAnnouncementCategory", "returnAspiSnp"})


# --- storing (shared with the migration) ------------------------------------------------------------------------

def _with_fetch(rows: list[dict], fetch_id: int, fetched_at: dt.datetime) -> list[dict]:
    return [dict(r, fetch_id=fetch_id, fetched_at=fetched_at) for r in rows]


def store_prices(conn, rows: list[dict], fetch_id: int, fetched_at: dt.datetime) -> int:
    """Append price rows. A 'backfill' row is written only for a session with no stored row for that stock: backfill
    exists to fill gaps, and a daily row carries real turnover (old cse/backfill.py, same rule). Re-reading the
    rolling one-year chart therefore adds only sessions that are genuinely missing."""
    if rows and rows[0]["source"] == "backfill":
        have = {(r["session_date"], r["symbol"]) for r in conn.execute(
            "select session_date, symbol from cse.prices_daily where symbol = any(%s)",
            (list({r["symbol"] for r in rows}),))}
        rows = [r for r in rows if (r["session_date"], r["symbol"]) not in have]
    added, _ = db.insert_facts(conn, "cse.prices_daily", _with_fetch(rows, fetch_id, fetched_at),
                               key=["session_date", "symbol", "source"], fetch_id=fetch_id)
    return added


def store_indices(conn, rows: list[dict], fetch_id: int, fetched_at: dt.datetime) -> int:
    if rows and rows[0]["source"] == "backfill":
        have = {(r["session_date"], r["index_code"]) for r in conn.execute(
            "select session_date, index_code from cse.indices_daily")}
        rows = [r for r in rows if (r["session_date"], r["index_code"]) not in have]
    added, _ = db.insert_facts(conn, "cse.indices_daily", _with_fetch(rows, fetch_id, fetched_at),
                               key=["session_date", "index_code", "source"], fetch_id=fetch_id)
    return added


def store(conn, table: str, rows: list[dict], key: list[str], fetch_id: int, fetched_at: dt.datetime) -> int:
    added, _ = db.insert_facts(conn, table, _with_fetch(rows, fetch_id, fetched_at), key=key, fetch_id=fetch_id)
    return added


# --- collectors --------------------------------------------------------------------------------------------------

class CseCollector(Collector):
    source_id = "cse_api"
    # Per-company calls go to every ordinary share. Set this to a set of symbols to limit them (tests, or an incident
    # where the API is struggling). None in production.
    only_symbols: set[str] | None = None

    def companies(self, securities: list[dict]) -> list[dict]:
        return [s for s in securities if s["symbol"].endswith(parse.EQUITY_SUFFIXES)
                and (self.only_symbols is None or s["symbol"] in self.only_symbols)]

    def api(self, endpoint: str, **params) -> Fetched:
        method = "GET" if endpoint in GET_ENDPOINTS else "POST"
        return self.fetch(method, API + endpoint, params or None, note=endpoint)


class CseEndOfDayCollector(CseCollector):
    job = "collect"

    def collect(self) -> Result:
        conn = self.ctx.conn
        status = parse.market_status(self.api("marketStatus").body)
        secs_f = self.api("allSecurityCode")
        dms_f = self.api("dailyMarketSummery")
        session, market, tri = parse.session_and_market(dms_f.body)

        last = conn.execute("select max(session_date) d from cse.prices_daily where source = 'daily'").fetchone()["d"]
        if last == session:
            # The session's market data is stored. Finish any company summaries an earlier run could not get.
            stored = conn.execute("select symbol from cse.security_list where session_date = %s", (session,)).fetchall()
            securities = [s for s in parse.security_list(secs_f.body, session) if s["symbol"] in {r["symbol"] for r in stored}]
            missing = self.missing_companies(securities, session)
            if not missing:
                return Result(new_data=False, message=f"no new session (latest stored daily session {last})")
            added, failed = self.store_companies(missing, session)
            return self.finish(f"session {session}: {len(missing)} company summaries completed", added, failed)
        if last and session < last:
            raise RuntimeError(f"API session {session} is older than the last stored session {last}")
        if parse.is_open(status):
            raise RuntimeError(f"market status is {status!r}; refusing to snapshot an open session")

        trade_f = self.api("tradeSummary")
        prices = parse.trade_summary(trade_f.body, session)
        sectors_f = self.api("allSectors")
        indices = parse.sectors(sectors_f.body, session)
        for endpoint in ("aspiData", "snpData", "marketSummery"):
            self.api(endpoint)                   # archived for the record; their figures duplicate the above
        securities = parse.security_list(secs_f.body, session)

        added = 0
        added += store(conn, "cse.security_list", securities, ["session_date", "symbol"], secs_f.fetch_id,
                       secs_f.response.fetched_at)
        added += store_prices(conn, prices, trade_f.fetch_id, trade_f.response.fetched_at)
        added += store_indices(conn, indices, sectors_f.fetch_id, sectors_f.response.fetched_at)
        added += store_indices(conn, tri, dms_f.fetch_id, dms_f.response.fetched_at)
        added += store(conn, "cse.market_daily", market, ["session_date", "source"], dms_f.fetch_id,
                       dms_f.response.fetched_at)
        conn.commit()

        more, failed = self.store_companies(self.missing_companies(securities, session), session)
        return self.finish(f"session {session}: {len(prices)} prices", added + more, failed)

    def missing_companies(self, securities: list[dict], session) -> list[dict]:
        have = {r["symbol"] for r in self.ctx.conn.execute(
            "select symbol from cse.company_info_daily where session_date = %s", (session,))}
        return [s for s in self.companies(securities) if s["symbol"] not in have]

    def store_companies(self, equities: list[dict], session) -> tuple[int, list[str]]:
        """Company summary (and, once per listing, profile) for each share. One share failing never stops the rest:
        each success is committed at once, and the failures are retried by the next run of the day."""
        conn = self.ctx.conn
        added, failed = 0, []
        have_profile = {r["symbol"] for r in conn.execute("select distinct symbol from cse.company_profiles")}
        for sec in equities:
            try:
                f = self.api("companyInfoSummery", symbol=sec["symbol"])
                added += store(conn, "cse.company_info_daily", [parse.company_info(f.body, sec["symbol"], session)],
                               ["session_date", "symbol"], f.fetch_id, f.response.fetched_at)
                if sec["symbol"] not in have_profile:   # sector labels: once per listing, refreshed by hand if needed
                    f = self.api("companyProfile", symbol=sec["symbol"])
                    added += store(conn, "cse.company_profiles",
                                   [dict(parse.company_profile(f.body, sec["symbol"]), raw_sha256=f.sha256)],
                                   ["symbol", "raw_sha256"], f.fetch_id, f.response.fetched_at)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - recorded and raised at the end of the run
                conn.rollback()
                failed.append(f"{sec['symbol']} ({type(exc).__name__}: {exc})"[:200])
        return added, failed

    def finish(self, what: str, added: int, failed: list[str]) -> Result:
        message = f"{what}, {added} rows added ({self.fetches} API calls)"
        if failed:   # everything else is already committed; this makes the run fail loudly and the next one retry
            raise RuntimeError(f"{message}; {len(failed)} company summaries failed: " + "; ".join(failed[:20]))
        return Result(rows_added=added, message=message)


class CseAnnouncementsCollector(CseCollector):
    job = "announcements"

    def collect(self) -> Result:
        conn = self.ctx.conn
        secs = conn.execute("""select symbol, name from cse.security_list
                               where session_date = (select max(session_date) from cse.security_list)""").fetchall()
        if not secs:
            f = self.api("allSecurityCode")
            secs = parse.security_list(f.body, self.ctx.today_slt)
        by_name = parse.company_codes(secs)
        known = {r["announcement_id"] for r in conn.execute("select announcement_id from cse.announcements")}

        list_f = self.api("approvedAnnouncement")
        rows = []
        for a in parse.approved_announcements(list_f.body):
            aid = str(a.announcementId)
            if aid in known:
                continue
            detail, detail_f, endpoint = None, None, None
            for ep in ("getAnnouncementById", "getGeneralAnnouncementById"):
                f = self.api(ep, announcementId=a.announcementId)
                detail = parse.announcement_detail(f.body, ep, aid)
                if detail:
                    detail_f, endpoint = f, ep
                    break
            row = parse.announcement_row(a, detail, by_name)
            rows.append(dict(row, detail_endpoint=endpoint, list_fetch_id=list_f.fetch_id,
                             detail_fetch_id=detail_f.fetch_id if detail_f else None,
                             fetched_at=list_f.response.fetched_at))
            known.add(aid)
        fin_f = self.api("getFinancialAnnouncement")
        for row in parse.financial_announcements(fin_f.body, by_name):
            if row["announcement_id"] not in known:
                rows.append(dict(row, detail_endpoint=None, list_fetch_id=fin_f.fetch_id, detail_fetch_id=None,
                                 fetched_at=fin_f.response.fetched_at))
        added, _ = db.insert_facts(conn, "cse.announcements", rows, key=["announcement_id"])
        return Result(rows_added=added, new_data=bool(added), message=f"{added} new announcements")


class CseHistoryCollector(CseCollector):
    job = "history"

    def collect(self) -> Result:
        conn = self.ctx.conn
        secs_f = self.api("allSecurityCode")
        securities = parse.security_list(secs_f.body, self.ctx.today_slt)
        added = 0
        for sec in self.companies(securities):
            f = self.api("companyChartDataByStock", stockId=sec["stock_id"], period=5)
            added += store_prices(conn, parse.stock_chart(f.body, sec["symbol"]), f.fetch_id, f.response.fetched_at)
        sectors_f = self.api("allSectors")
        for sector_id, code in parse.sector_ids(sectors_f.body):
            f = self.api("chartData", chartId=sector_id, period=5)
            added += store_indices(conn, parse.index_chart(f.body, code), f.fetch_id, f.response.fetched_at)
        return Result(rows_added=added, new_data=bool(added),
                      message=f"{added} backfill rows for sessions the daily job did not store")
