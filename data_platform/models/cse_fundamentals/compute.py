"""cse_fundamentals: each company's EPS and net assets per share, read from its interim reports and checked inside
each report, and the ratios built on them at each session's prices (audit C21, C22; the old terminal's
data/fundamentals/{reports,latest}.csv).

Version 1 runs the old code (ported line for line into data_platform/models/_lib/cse_figures.py, with the
shareholder-table step from _lib/cse_ownership.py) as at every session the old daily job could have run, each time
with only the facts known by then: prices, share counts and security lists up to that session, the reports uploaded
by then, the financial year ends fetched by then, and the cash dividends announced by then. So a session's row never
changes when later sessions arrive.

Outputs (see METHOD.md):
  models.cse_report_figures   per report: the EPS and NAV per share that reconciled, as at the latest session
                              (the old reports.csv)
  models.cse_fundamentals     per company and session: TTM EPS, NAV per share, P/E, P/B, ROE, trailing dividends
                              and dividend yield (the old latest.csv), with the company's latest report
"""
from __future__ import annotations

import datetime as dt

from .._lib import cse_figures as fig
from .._lib import cse_ownership as own
from .._lib.cse_calendar import excluded_sessions
from .._lib import cse_reads as reads


def fiscal_years(inputs, as_of) -> list[tuple[dt.date, str, str]]:
    """(session, symbol, finYearEnd) for every profile with a year end, in the order the old fyes() read its files
    (session folder, then symbol): a later profile overwrites an earlier one."""
    where, params = ("session_date <= %s", (as_of,)) if as_of else ("", ())
    rows = inputs.rows("cse.company_fiscal_years", "session_date, symbol, fin_year_end",
                       where=" and ".join(filter(None, ["fin_year_end is not null", "fin_year_end <> ''",
                                                        "session_date is not null", where])),
                       params=params, order_by="session_date, symbol, fetched_at")
    return [(r["session_date"], r["symbol"], r["fin_year_end"]) for r in rows]


def fye_at(profiles: list[tuple[dt.date, str, str]], session: dt.date) -> dict[str, str]:
    out = {}
    for d, symbol, fye in profiles:
        if d <= session:
            out[symbol.split(".")[0]] = fye
    return out


def closes(inputs, as_of) -> list[tuple[dt.date, str, float]]:
    """Every close (daily rows preferred, as the old prices.csv reader did), oldest first."""
    skip = excluded_sessions(inputs)
    where, params = ("session_date <= %s", (as_of,)) if as_of else ("", ())
    return [(r["session_date"], r["symbol"], r["close"]) for r in inputs.rows(
        "cse.prices_daily_current", "session_date, symbol, close", where=where, params=params,
        order_by="session_date, symbol") if r["session_date"] not in skip]


def actions(inputs) -> list[dict]:
    """The cash dividends in use (cse_corporate_actions' used actions), in the old CSV's terms."""
    return [{"symbol": r["symbol"], "type": r["action_type"], "ex_date": r["ex_date"].isoformat(),
             "amount_per_share": r["amount_per_share"], "announced_date": r["announced_date"]}
            for r in inputs.rows("models.cse_corporate_action_used",
                                 "action_id, symbol, action_type, ex_date, amount_per_share, announced_date",
                                 where="action_type = 'cash_dividend'", order_by="action_id")]


def run(inputs, as_of, sessions_wanted=None) -> dict:
    """{session: (report rows, latest rows)} for every session (or those wanted). Shared with the parity check."""
    data = reads.market_data(inputs, as_of)
    reps, known_from = reads.reports(inputs)
    text_of = reads.texts(inputs, reps)
    cache, extractor = own.TableCache(text_of), fig.Extractor(text_of)
    profiles = fiscal_years(inputs, as_of)
    divs_all = actions(inputs)
    prices = closes(inputs, as_of)
    counts = fig.ShareCounts(data)
    sessions = [d for d in data.sessions if not as_of or d <= as_of]
    last_close: dict[str, tuple[float, str]] = {}
    i = 0
    out = {}
    for d in sessions:
        while i < len(prices) and prices[i][0] <= d:
            day, symbol, close = prices[i]
            last_close[symbol] = (float(close), day.isoformat())
            i += 1
        if sessions_wanted is not None and d not in sessions_wanted:
            continue
        market = data.market(d)
        known = reads.known_on(reps, known_from, d)
        fye = fye_at(profiles, d)
        rows = fig.report_rows(market, known, fig.report_shares(market, known, cache), counts.at(d), fye, extractor)
        asof = max(v[1] for v in last_close.values())
        known_actions = [a for a in divs_all if a["announced_date"] is None or a["announced_date"] <= d]
        latest = fig.latest_rows(rows, market, last_close, fye, fig.dividends_ttm(known_actions, asof))
        out[d] = (rows, latest)
    return out


def _date(v):
    return dt.date.fromisoformat(v) if v else None


def compute(inputs, as_of):
    results = run(inputs, as_of)
    figures, daily = [], []
    for d, (rows, latest) in results.items():
        newest: dict[str, dict] = {}
        for r in sorted(rows, key=lambda r: r["period_date"]):     # stable: the old page's "latest report" link
            newest[r["code"]] = r
        for x in latest:
            rep = newest.get(x["code"])
            daily.append({"session_date": d, "code": x["code"], "price": x["price"], "price_date": _date(x["price_date"]),
                          "shares": x["shares"], "fye": x["fye"], "nav": x["nav"], "nav_period": _date(x["nav_period"]),
                          "pb": x["pb"], "ttm_profit": x["ttm_profit"], "ttm_eps": x["ttm_eps"],
                          "ttm_to": _date(x["ttm_to"]), "ttm_note": x["ttm_note"],
                          "earnings_yield": x["earnings_yield"], "pe": x["pe"], "roe": x["roe"],
                          "div_ttm": x["div_ttm"], "dy": x["dy"],
                          "report_id": int(rep["report_id"]) if rep else None,
                          "report_period": _date(rep["period_date"]) if rep else None,
                          "report_url": rep["url"] if rep else None})
    if results:
        last = max(results)
        for r in results[last][0]:
            figures.append({"report_id": int(r["report_id"]), "code": r["code"], "period_date": _date(r["period_date"]),
                            "fye": r["fye"], "shares": r["shares"], "eps": r["eps"],
                            "eps_class": r["eps_class"], "eps_status": r["eps_status"], "profit": r["profit"],
                            "unit": r["unit"], "eps_line": r["eps_line"], "nav": r["nav"],
                            "nav_status": r["nav_status"], "equity": r["equity"], "nav_line": r["nav_line"],
                            "source_url": r["url"], "as_of": last})
    return {"models.cse_report_figures": figures, "models.cse_fundamentals": daily}

