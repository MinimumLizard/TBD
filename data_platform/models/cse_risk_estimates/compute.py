"""cse_risk_estimates: the portfolio lab's universe and risk estimates per estimate date (audit C8, C9; the sector
classification C4). INTERNAL RESEARCH: unpublished (config/entitlements.yaml), read by cse_portfolio_lab and the
owner's lab report only.

Version 1.0.0 ports MinimumLizard/CSE@e05c6f3 cse/estimates.py, cse/returns.py and cse/sectors.py (the arithmetic in
data_platform/models/_lib/cse_estimates.py and cse_sectors.py) and runs them as at every session from the old lab's
first one, each time with only the facts up to that session, as the old daily job did: the universe filter with a
reason for every security left out, the weekly total returns, the Ledoit-Wolf covariance, Dimson beta, CAPM expected
return, volatility and Amihud illiquidity. The owner's conflict-of-interest list comes from the private settings
(LAB_PRIVATE_FILE, stored in cse.lab_private_settings); without them version 1.0.0 computes nothing. The risk-free
rate is the old tool's typed 9.9 %.
Version 1.1.0: no personal exclusions; the risk-free rate is the CBSL's 12-month treasury bill yield as published
by the estimate date; no preview; estimate dates from the first session with a full year of weekly returns.

The covariance is stored in factor form (METHOD.md): the weekly returns (models.cse_weekly_return), the universe and
the shrinkage intensity determine it exactly; data_platform/models/_lib/cse_estimates.py ledoit_wolf() rebuilds it.
"""
from __future__ import annotations

import bisect
import datetime as dt
from collections import defaultdict

import numpy as np

from .._lib import cse_estimates as est
from .._lib.cse_calendar import ASPI, excluded_sessions, session_filter
from .._lib.cse_sectors import classify, load_overrides

SLT = dt.timezone(dt.timedelta(hours=5, minutes=30))
MARKET_PROXY = "ASPI (price index)"


# --- the facts --------------------------------------------------------------------------------------------------

def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def latest_version(inputs, table: str, columns: str, as_of):
    """The latest stored version of an owner's input (on or before as_of), or None."""
    sub = f"(select max(version_id) from {table}" + (" where loaded_at < (%s::date + 1))" if as_of else ")")
    rows = inputs.rows(table, columns, where=f"version_id = {sub}", params=(as_of,) if as_of else ())
    return rows[0] if rows else None


class ByDate:
    """Rows grouped by a date: for a day, the group of the latest date on or before it (before the first: the
    first, as for the security lists elsewhere)."""

    def __init__(self, groups: dict):
        self.dates = sorted(groups)
        self._g = groups

    def at(self, day: dt.date):
        if not self.dates:
            return None
        i = bisect.bisect_right(self.dates, day) - 1
        return self._g[self.dates[max(i, 0)]]


def history(inputs, as_of, skip: set[dt.date]) -> est.History:
    where, params = session_filter(as_of)
    aspi = {r["session_date"].isoformat(): r["value"] for r in inputs.rows(
        "cse.indices_daily_current", "session_date, value",
        where=" and ".join(filter(None, ["index_code = %s", where])), params=(ASPI, *params))
        if r["session_date"] not in skip}
    prices = [{"date": r["session_date"].isoformat(), "symbol": r["symbol"], "close": r["close"],
               "turnover": r["turnover"], "turnover_est": r["turnover_est"]}
              for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, close, turnover, turnover_est",
                                   where=" and ".join(filter(None, ["right(symbol, 6) in ('.N0000', '.X0000')",
                                                                    where])), params=params,
                                   order_by="symbol, session_date")
              if r["session_date"] not in skip]
    tri: dict[str, dict] = defaultdict(dict)
    for r in inputs.rows("models.cse_total_return", "symbol, session_date, tri", where=where, params=params):
        if r["session_date"] not in skip:
            tri[r["symbol"]][r["session_date"].isoformat()] = r["tri"]
    return est.History(sorted(aspi), aspi, prices, tri)


def security_lists(inputs, as_of) -> ByDate:
    where, params = session_filter(as_of)
    by: dict[dt.date, list[est.Security]] = defaultdict(list)
    for r in inputs.rows("cse.security_list", "session_date, symbol, name", where=where, params=params,
                         order_by="session_date, symbol"):
        by[r["session_date"]].append(est.Security(r["symbol"], r["name"]))
    if not by:          # before the first stored list: the first list
        for r in inputs.rows("cse.security_list", "session_date, symbol, name",
                             where="session_date = (select min(session_date) from cse.security_list)",
                             order_by="symbol"):
            by[r["session_date"]].append(est.Security(r["symbol"], r["name"]))
    return ByDate(dict(by))


def sector_labels(inputs) -> ByDate:
    """Each share's CSE profile label as known by a date: the latest profile fetched by then (Sri Lanka time), or
    before any, the earliest (the old terminal fetched every profile once and read the latest file)."""
    by: dict[dt.date, dict[str, str | None]] = {}
    current: dict[str, str | None] = {}
    rows = sorted(inputs.rows("cse.company_profiles", "symbol, sector_label, fetched_at"),
                  key=lambda r: (r["fetched_at"], r["symbol"]))
    for r in rows:
        current[r["symbol"]] = r["sector_label"]
        by[r["fetched_at"].astimezone(SLT).date()] = dict(current)
    return ByDate(by)


def ownership_groups(inputs, as_of) -> ByDate:
    """cse_ownership's groups by session: company code -> (group key, group name)."""
    where, params = session_filter(as_of)
    by: dict[dt.date, dict[str, tuple[str, str | None]]] = defaultdict(dict)
    for r in inputs.rows("models.cse_ownership_detail", "session_date, code, group_key, group_name", where=where,
                         params=params, order_by="session_date, code"):
        by[r["session_date"]][r["code"]] = (r["group_key"], r["group_name"])
    return ByDate(dict(by))


def for_symbols(groups: dict[str, tuple[str, str | None]] | None, symbols: list[str]) -> tuple[dict, dict]:
    """Old ownership groups.for_symbols: share -> group key (both classes of a company share its group; a company
    with no row is its own group), and group key -> name. Without ownership data both are empty (no group cap)."""
    if not groups:
        return {}, {}
    out = {s: groups.get(s.split(".")[0], ("LISTED:" + s.split(".")[0], None))[0] for s in symbols}
    labels = {key: name for key, name in groups.values() if name is not None}
    return out, labels


def add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def bill_yields(inputs) -> list[tuple[dt.date, float]]:
    return sorted((r["month"], r["value"]) for r in inputs.rows(
        "rates.cbsl_monthly_current", "month, value", where="series = 'TB_12M'"))


def risk_free(spec: dict, bills: list[tuple[dt.date, float]], day: dt.date) -> tuple[float | None, str, dt.date | None]:
    """(annual rate, source, month). fixed: the stated rate. cbsl_tb_12m: the CBSL's 12-month treasury bill yield
    (end of month, table 4.04) of the latest month whose figure had surely been published by the day: a month counts
    once `publication_delay_months` full months have passed after it."""
    if spec["source"] == "fixed":
        return float(spec["annual"]), f"fixed at {spec['annual']:.2%} (the old tool's typed value)", None
    delay = int(spec.get("publication_delay_months", 1))
    usable = [(m, v) for m, v in bills if add_months(m, 1 + delay) <= day]
    if not usable:
        return None, "no 12-month bill yield published by this date", None
    m, v = usable[-1]
    return v / 100, f"CBSL 12-month treasury bill yield, {m:%B %Y} (table 4.04)", m


# --- the model --------------------------------------------------------------------------------------------------

def estimate_dates(h: est.History, params: dict, as_of) -> list[str]:
    sessions = [s for s in h.sessions if not as_of or s <= as_of.isoformat()]
    first = params.get("first_estimate_date")
    if first:
        return [s for s in sessions if s >= str(first)]
    # the first session with a full window of weekly returns possible
    need = int(params["min_history_weeks"]) + 1
    return [s for s in sessions if len(h.weeks_all(s)) >= need]


def weekly_rows(h: est.History, last: str) -> list[dict]:
    weeks = h.weeks_all(last)
    out = []
    for series, level in sorted(h.tri.items()) + [(ASPI, h.aspi)]:
        r = est.weekly_returns(level, weeks)
        s = est.sample_on_or_before(level, weeks)
        idx = np.searchsorted(np.array(level.sort_index().index, dtype=object), np.array(weeks, dtype=object),
                              side="right") - 1
        when = {w: level.sort_index().index[i] for w, i in zip(weeks, idx) if i >= 0}
        for w, v in r.items():
            if np.isfinite(v):
                out.append({"series": series, "week_end": w, "level": s[w], "level_date": when[w], "weekly_return": v})
    return out


def compute(inputs, as_of):
    p = inputs.params
    skip = excluded_sessions(inputs)
    h = history(inputs, as_of, skip)
    out = {"models.cse_weekly_return": [], "models.cse_risk_summary": [], "models.cse_risk_universe": [],
           "models.cse_risk_estimate": []}
    if not h.sessions:
        return out
    excluded: set[str] = set()
    if p.get("exclusions") == "private":
        private = latest_version(inputs, "cse.lab_private_settings", "settings", as_of)
        if private is None:         # version 1.0.0 needs the owner's own list: without it, nothing
            return out
        excluded = set(private["settings"].get("excluded") or [])
    stored = latest_version(inputs, "cse.sector_overrides", "overrides", as_of)
    overrides = load_overrides({"overrides": stored["overrides"]} if stored else {})
    lists, labels, groups = security_lists(inputs, as_of), sector_labels(inputs), ownership_groups(inputs, as_of)
    bills = bill_yields(inputs) if p["risk_free"]["source"] != "fixed" else []
    cfg = {k: p[k] for k in ("min_history_weeks", "min_traded_share", "min_median_turnover_lkr",
                             "equity_risk_premium")}
    dates = estimate_dates(h, p, as_of)
    out["models.cse_weekly_return"] = weekly_rows(h, h.sessions_to(as_of.isoformat())[-1] if as_of else h.sessions[-1])
    for session in dates:
        day = dt.date.fromisoformat(session)
        securities = lists.at(day) or []
        lab = labels.at(day) or {}
        equities = [s.symbol for s in securities if s.symbol.endswith(est.EQUITY_SUFFIXES)]
        sectors = {s: classify(s, lab.get(s), overrides) for s in equities}
        gmap, glabels = for_symbols(groups.at(day), equities)
        rf, rf_source, rf_month = risk_free(p["risk_free"], bills, day)
        if rf is None:
            universe = est.select_universe(securities, h, sectors, excluded, {**cfg, "risk_free_annual": 0.0},
                                           session, h.weeks_all(session))
            outcome = est.Outcome(session, "waiting", rf_source, universe)
        else:
            outcome = est.run_date(h, securities, sectors, excluded, {**cfg, "risk_free_annual": rf}, session,
                                   p.get("preview_min_weeks"))
        rows = date_rows(day, outcome, securities, gmap, glabels, rf, rf_source, rf_month, p)
        for table, r in rows.items():
            out[table] += r
    return out


def date_rows(day: dt.date, o: est.Outcome, securities: list[est.Security], gmap: dict, glabels: dict,
              rf, rf_source: str, rf_month, p: dict) -> dict[str, list[dict]]:
    u, e = o.universe, o.estimates
    names = {s.symbol: s.name for s in securities}
    dropped = {d["symbol"]: d["reason"] for d in u.dropped}
    universe = []
    for s in sorted(names):
        st = u.stats.loc[s] if not u.stats.empty and s in u.stats.index else None
        universe.append({"as_of": day, "symbol": s, "name": names[s], "included": s not in dropped,
                         "reason": dropped.get(s),
                         "weeks": None if st is None else int(st["weeks"]),
                         "traded_share": None if st is None else float(st["traded_share"]),
                         "median_turnover": None if st is None else float(st["median_turnover"]),
                         "real_turnover_share": None if st is None else float(st["real_turnover_share"]),
                         "sector": None if st is None else st["sector"]})
    estimates = []
    if e is not None:
        for s in e.symbols:
            g = gmap.get(s, s)
            estimates.append({"as_of": day, "symbol": s, "sector": e.sectors[s], "group_key": g,
                              "group_name": glabels.get(g, g), "beta": e.beta[s],
                              "beta_current": e.beta_parts.loc[s, "b0"], "beta_lag": e.beta_parts.loc[s, "b1"],
                              "expected_return": e.er[s], "volatility": e.vol[s], "amihud": e.amihud[s],
                              "median_turnover": e.median_turnover[s], "turnover_source": e.turnover_source[s]})
    summary = {"as_of": day, "status": o.status, "message": o.message, "preview": o.preview_weeks is not None
               and e is not None, "n_securities": len(securities), "n_universe": len(u.symbols),
               "history_weeks": (o.preview_weeks if o.status == "waiting" else p["min_history_weeks"])
               if e is not None else None,
               "max_weeks_available": est.max_weeks(u),
               "first_week": e.weeks[0] if e is not None else None, "last_week": e.weeks[-1] if e is not None else None,
               "shrinkage": e.shrinkage if e is not None else None, "risk_free": rf, "risk_free_source": rf_source,
               "risk_free_month": rf_month, "equity_risk_premium": p["equity_risk_premium"],
               "market_proxy": MARKET_PROXY}
    return {"models.cse_risk_summary": [summary], "models.cse_risk_universe": universe,
            "models.cse_risk_estimate": estimates}
