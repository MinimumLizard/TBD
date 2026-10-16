"""Pure parsers for CSE API responses: bytes in, validated rows out. No network, no database.

The row shapes match the cse.* tables (db/migrations/0003_cse.sql) minus the provenance columns (fetch_id,
fetched_at), which the collector adds. The rules reproduce the old terminal's cse/fetch.py and cse/backfill.py
exactly where the old CSV files had a column, so the migration can prove parity (docs/architecture.md §14).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import quote

from .models import (AnnouncementDetail, ApprovedAnnouncements, CompanyInfo, CompanyProfile, DailyMarketSummary,
                     FinancialAnnouncements, IndexChart, MarketStatus, SectorList, SecurityList, StockChart,
                     TradeSummary, ms_to_date, validate)

CDN = "https://cdn.cse.lk/"
EQUITY_SUFFIXES = (".N0000", ".X0000")          # voting, non-voting (audit §2: API_NOTES §3)
TRI_INDICES = {"triasi": "ASTRI", "spt": "S&P SL20 TRI"}


def _json(body: bytes):
    return json.loads(body)


def market_status(body: bytes) -> str:
    return validate(MarketStatus, _json(body), "marketStatus").status


def is_closed(status: str) -> bool:
    """True only when the status says the market is closed ("Market Closed"). Anything else, including an unknown
    status, counts as open: while trading, the API says "Regular Trading" (seen 2026-10-16), which the old tool's
    test (contains OPEN and not CLOSE) let through, so a run during the session could have stored intraday prices
    as the close. An auction ("Close Auction") is still part of the session."""
    s = status.upper()
    return "CLOSE" in s and not any(word in s for word in ("TRADING", "AUCTION", "OPEN"))


def session_and_market(body: bytes) -> tuple[dt.date, list[dict], list[dict]]:
    """dailyMarketSummery → (latest session date, market rows for both sessions it carries, TRI index rows).

    The session date always comes from here, never from the clock (the API serves Friday's session all weekend).
    """
    dms = validate(DailyMarketSummary, _json(body), "dailyMarketSummery")
    market, tri = [], []
    rows = dms.rows
    for i, row in enumerate(rows):
        prev = rows[i + 1] if i + 1 < len(rows) else None
        for attr, name in TRI_INDICES.items():
            v = getattr(row, attr)
            if v is None:
                continue
            pv = getattr(prev, attr) if prev else None
            tri.append({"session_date": row.session, "index_code": name, "source": "daily", "value": v,
                        "change": (v - pv) if pv is not None else None})
        market.append({
            "session_date": row.session, "source": "daily", "turnover": row.marketTurnover,
            "volume": row.volumeOfTurnOverNumber, "trades": row.tradesNo, "foreign_buy": row.equityForeignPurchase,
            "foreign_sell": row.equityForeignSales, "listed": row.listedCompanyNumber,
            "traded": row.tradeCompanyNumber, "market_cap": row.marketCap, "aspi": row.asi, "spsl20": row.spp,
            "astri": row.triasi, "spsl20_tri": row.spt, "per": row.per, "pbv": row.pbv, "dy": row.dy,
        })
    return dms.latest.session, market, tri


def security_list(body: bytes, session: dt.date) -> list[dict]:
    secs = validate(SecurityList, _json(body), "allSecurityCode").root
    return [{"session_date": session, "symbol": s.symbol, "stock_id": s.id, "name": s.name, "active": s.active}
            for s in secs]


def trade_summary(body: bytes, session: dt.date) -> list[dict]:
    """tradeSummary → one 'daily' price row per security that traded. Fails if it is not this session's data."""
    trade = validate(TradeSummary, _json(body), "tradeSummary")
    newest = max(ms_to_date(r.lastTradedTime) for r in trade.reqTradeSummery)
    if newest != session:
        raise ValueError(f"tradeSummary is for {newest} but dailyMarketSummery says {session}")
    return [{
        "session_date": session, "symbol": r.symbol, "source": "daily", "close": r.closingPrice,
        "previous_close": r.previousClose or None, "open": r.open, "high": r.high, "low": r.low,
        "volume_regular": r.sharevolume, "volume_total": r.crossingVolume, "trades_regular": r.tradevolume,
        "trades_total": r.crossingTradeVol, "turnover": r.turnover, "turnover_est": None, "market_cap": r.marketCap,
        "last_traded_at": dt.datetime.fromtimestamp(r.lastTradedTime / 1000, dt.timezone.utc),
    } for r in trade.reqTradeSummery]


def sectors(body: bytes, session: dt.date) -> list[dict]:
    return [{"session_date": session, "index_code": s.symbol, "source": "daily", "value": s.indexValue,
             "change": s.change} for s in validate(SectorList, _json(body), "allSectors").root]


def sector_ids(body: bytes) -> list[tuple[int, str]]:
    return [(s.sectorId, s.symbol) for s in validate(SectorList, _json(body), "allSectors").root]


def company_info(body: bytes, symbol: str, session: dt.date) -> dict:
    info = validate(CompanyInfo, _json(body), f"companyInfoSummery {symbol}")
    if info.reqSymbolInfo.symbol != symbol:
        raise ValueError(f"companyInfoSummery for {symbol} returned {info.reqSymbolInfo.symbol}")
    s, b = info.reqSymbolInfo, info.reqSymbolBetaInfo
    raw = _json(body)["reqSymbolInfo"]
    return {"session_date": session, "symbol": symbol, "last_traded_price": s.lastTradedPrice,
            "previous_close": s.previousClose, "high_52w": s.p12HiPrice, "low_52w": s.p12LowPrice,
            "market_cap": s.marketCap, "quantity_issued": s.quantityIssued, "isin": raw.get("isin"),
            "beta_triasi": b.triASIBetaValue if b else None, "beta_spsl": b.betaValueSPSL if b else None,
            "beta_period": b.triASIBetaPeriod if b else None, "beta_quarter": b.quarter if b else None}


def company_profile(body: bytes, symbol: str) -> dict:
    prof = validate(CompanyProfile, _json(body), f"companyProfile {symbol}")
    first = prof.reqComSumInfo[0] if prof.reqComSumInfo else None
    return {"symbol": symbol, "sector_label": first.sector if first else None,
            "board_type": first.boardType if first else None}


def stock_chart(body: bytes, symbol: str) -> list[dict]:
    """companyChartDataByStock (period 5, about 240 sessions) → 'backfill' price rows.

    As served: unadjusted. The chart's volume `q` includes negotiated crossings, so it is volume_total. There is
    no turnover; turnover_est = close × volume_total (decision D2). previous_close is the previous bar's close.
    """
    chart = validate(StockChart, _json(body), f"companyChartDataByStock {symbol}")
    rows, prev = [], None
    for bar in sorted(chart.chartData, key=lambda b: b.t):
        rows.append({"session_date": ms_to_date(bar.t), "symbol": symbol, "source": "backfill", "close": bar.p,
                     "previous_close": prev, "open": None, "high": bar.h, "low": bar.l, "volume_regular": None,
                     "volume_total": bar.q, "trades_regular": None, "trades_total": None, "turnover": None,
                     "turnover_est": bar.p * bar.q, "market_cap": None, "last_traded_at": None})
        prev = bar.p
    return rows


def index_chart(body: bytes, index_code: str) -> list[dict]:
    rows, prev = [], None
    for pt in sorted(validate(IndexChart, _json(body), f"chartData {index_code}").root, key=lambda p: p.d):
        rows.append({"session_date": ms_to_date(pt.d), "index_code": index_code, "source": "backfill",
                     "value": pt.v, "change": (pt.v - prev) if prev is not None else None})
        prev = pt.v
    return rows


# --- announcements ---------------------------------------------------------------------------------------------

def norm_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def company_codes(securities: list[dict]) -> dict[str, str]:
    """Normalised company name → bare company code, voting class preferred (old cse/fetch.py)."""
    by_name: dict[str, str] = {}
    for s in sorted(securities, key=lambda s: (not s["symbol"].endswith(".N0000"), s["symbol"])):
        by_name.setdefault(norm_name(s["name"]), s["symbol"].split(".")[0])
    return by_name


def approved_announcements(body: bytes):
    return validate(ApprovedAnnouncements, _json(body), "approvedAnnouncement").approvedAnnouncements


def announcement_detail(body: bytes, endpoint: str, aid) -> AnnouncementDetail | None:
    if not body:
        return None                     # 204: no detail here
    data = _json(body)
    if not data:
        return None                     # {}: the other endpoint serves this id
    return validate(AnnouncementDetail, data, f"{endpoint} {aid}")


def doc_url(detail: AnnouncementDetail | None) -> str:
    if not detail or not detail.reqAnnouncementDocs:
        return ""
    d = detail.reqAnnouncementDocs[0]
    base = d.baseUrl if (d.baseUrl or "").startswith("https://") else CDN    # never emit a non-https link
    return base.rstrip("/") + "/" + quote(d.fileUrl.lstrip("/"), safe="/")


def announcement_row(a, detail: AnnouncementDetail | None, by_name: dict[str, str]) -> dict:
    symbol = (detail.reqBaseAnnouncement.symbol if detail else None) or by_name.get(norm_name(a.company), "")
    return {"announcement_id": str(a.announcementId), "announced_date": a.date, "symbol": symbol or None,
            "company": a.company.strip(), "title": (a.remarks or "").strip() or a.announcementCategory.strip(),
            "category": a.announcementCategory.strip(), "document_url": doc_url(detail) or None}


def financial_announcements(body: bytes, by_name: dict[str, str]) -> list[dict]:
    fin = validate(FinancialAnnouncements, _json(body), "getFinancialAnnouncement")
    return [{"announcement_id": f"F{f.id}", "announced_date": f.date,
             "symbol": f.symbol or by_name.get(norm_name(f.name)) or None, "company": f.name.strip(),
             "title": f.fileText.strip(), "category": "FINANCIAL REPORT",
             "document_url": CDN + quote(f.path.lstrip("/"), safe="/")} for f in fin.reqFinancialAnnouncemnets]
