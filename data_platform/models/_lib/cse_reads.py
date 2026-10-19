"""The facts the ownership and fundamentals models both read, in the shapes the ported old code expects."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from . import cse_ownership as own

SLT = dt.timezone(dt.timedelta(hours=5, minutes=30))


def market_data(inputs, as_of) -> own.MarketData:
    """Security lists, company summaries and the trade summary's rows, by session (up to as_of)."""
    where, params = ("session_date <= %s", (as_of,)) if as_of else ("", ())
    lists: dict[dt.date, list[dict]] = defaultdict(list)
    for r in inputs.rows("cse.security_list", "session_date, symbol, name", where=where, params=params,
                         order_by="session_date, symbol"):
        lists[r["session_date"]].append({"symbol": r["symbol"], "name": r["name"]})
    info: dict[dt.date, list[tuple]] = defaultdict(list)
    for r in inputs.rows("cse.company_info_daily", "session_date, symbol, quantity_issued, market_cap", where=where,
                         params=params, order_by="session_date, symbol"):
        info[r["session_date"]].append((r["symbol"], r["quantity_issued"], r["market_cap"]))
    trades: dict[dt.date, list[tuple]] = defaultdict(list)
    for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, market_cap, close",
                         where=" and ".join(filter(None, ["source = 'daily'", where])), params=params,
                         order_by="session_date, symbol"):
        trades[r["session_date"]].append((r["symbol"], r["market_cap"], r["close"]))
    return own.MarketData(dict(lists), dict(info), dict(trades))


def _utc_text(t: dt.datetime | None) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""


def reports(inputs) -> tuple[list[own.Report], dict[str, dt.date | None]]:
    """The report index (one row per report) as the old reports.csv held it, and the day each became known: its
    upload date in Sri Lanka (None: no upload date, known from the start)."""
    out, known_from = [], {}
    for r in inputs.rows("cse.financial_reports_current",
                         "report_id, code, symbol, kind, title, period_date, uploaded_at, url, status, text_sha256",
                         order_by="report_id"):
        rid = str(r["report_id"])
        out.append(own.Report(rid, r["code"], r["symbol"], r["kind"], r["title"],
                              r["period_date"].isoformat() if r["period_date"] else "", _utc_text(r["uploaded_at"]),
                              r["url"], r["status"], r["text_sha256"]))
        known_from[rid] = r["uploaded_at"].astimezone(SLT).date() if r["uploaded_at"] else None
    return out, known_from


def known_on(reps: list[own.Report], known_from: dict, day: dt.date) -> list[own.Report]:
    """The reports uploaded on or before `day`."""
    return [r for r in reps if known_from[r.id] is None or known_from[r.id] <= day]


def texts(inputs, reps: list[own.Report]):
    """A function: text_sha256 -> text, for the reports with a text."""
    shas = sorted({r.text_sha256 for r in reps if r.status == "ok" and r.text_sha256})
    body = {r["sha256"]: r["body"] for r in inputs.rows("cse.report_texts", "sha256, body", where="sha256 = any(%s)",
                                                         params=(shas,), order_by="sha256")}
    return body.__getitem__
