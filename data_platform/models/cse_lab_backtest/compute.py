"""cse_lab_backtest: the portfolio lab's walk-forward test (decision 0024). INTERNAL RESEARCH: unpublished
(config/entitlements.yaml); no page or API route reads it; the owner reads it through the lab report job.

What the lab's own rules (cse_risk_estimates 1.1.0 and cse_portfolio_lab 1.1.0: the same universe filters, estimates,
caps, K-name selection with its buffer, floor and cap) would have built on each past date, with only what was known on
that date, and what holding it would have done (cse_lab_record 1.1.0's execution rules: whole shares, 1.12 % a side,
corporate actions, the drift band), under two rebalancing policies: quarterly (the lab's rule) and dynamic (a monthly
check, rebalancing when the holdings have moved away from the rules' new portfolio by more than a tracking-error
threshold). The arithmetic is data_platform/models/_lib/cse_backtest.py; this file reads the facts and writes rows.

The test starts on the first session with enough history for the estimates (preview_min_weeks weekly returns, the
lab's preview rule) and a published 12-month bill yield; until a full year of weekly returns exists, each date's
estimates use all the weeks available (they are marked as previews). Every decision on a date reads only facts up to
that date. Facts recorded only from October 2026 (the list of listed securities, sector labels, ownership groups) are
used as first recorded for earlier dates: a company delisted before then is missing (METHOD.md, limits).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .._lib import cse_backtest as bt
from .._lib import cse_estimates as est
from .._lib import cse_optimize as opt
from .._lib.cse_calendar import excluded_sessions
from .._lib.cse_sectors import classify, load_overrides
from ..cse_lab_record import compute as record
from ..cse_risk_estimates import compute as risk

OUTPUTS = ("models.cse_bt_summary", "models.cse_bt_nav", "models.cse_bt_event", "models.cse_bt_target",
           "models.cse_bt_trade")


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def compute(inputs, as_of):
    p = inputs.params
    out: dict[str, list[dict]] = {t: [] for t in OUTPUTS}
    skip = excluded_sessions(inputs)
    h = risk.history(inputs, as_of, skip)
    sessions, aspi, closes, actions = record.market_facts(inputs, as_of, skip)
    if not sessions or not h.sessions:
        return out
    stored = risk.latest_version(inputs, "cse.sector_overrides", "overrides", as_of)
    overrides = load_overrides({"overrides": stored["overrides"]} if stored else {})
    lists, labels, groups = risk.security_lists(inputs, as_of), risk.sector_labels(inputs), risk.ownership_groups(inputs, as_of)
    bills = risk.bill_yields(inputs)
    ecfg = {k: p[k] for k in ("min_history_weeks", "min_traded_share", "min_median_turnover_lkr", "equity_risk_premium")}
    ocfg = {k: p[k] for k in ("max_weight", "max_sector_weight", "max_group_weight", "participation", "days_to_build",
                              "notional_lkr")}
    rcfg = {k: p[k] for k in ("record_notional_lkr", "cost_per_side", "dividend_withholding", "rebalance_months",
                              "band_relative", "band_absolute", "min_trade_lkr", "te_threshold")}
    spec = p["fewer_names"]

    def rf_on(s: str) -> float | None:
        return risk.risk_free(p["risk_free"], bills, _d(s))[0]

    cache: dict[str, bt.DateModel | None] = {}

    def model_on(s: str) -> bt.DateModel | None:
        if s in cache:
            return cache[s]
        day = _d(s)
        rf = rf_on(s)
        securities = lists.at(day) or []
        lab = labels.at(day) or {}
        equities = [x.symbol for x in securities if x.symbol.endswith(est.EQUITY_SUFFIXES)]
        sectors = {x: classify(x, lab.get(x), overrides) for x in equities}
        gmap, glabels = risk.for_symbols(groups.at(day), equities)
        dm = None
        if rf is not None:
            o = est.run_date(h, securities, sectors, set(), {**ecfg, "risk_free_annual": rf}, s, p["preview_min_weeks"])
            e = o.estimates
            if e is not None:
                prob = opt.make_problem(e.symbols, e.sectors, e.cov, e.er, rf, e.median_turnover, ocfg, gmap)
                try:
                    opt.check_feasible(prob)
                    full = {"min_variance": opt.min_variance(prob), "max_sharpe": opt.max_sharpe(prob)}
                    dm = bt.DateModel(s, prob, full, len(e.weeks), o.status != "ok", rf, e.beta.to_dict(),
                                      e.vol.to_dict(), glabels, float(e.vol.median()))
                except opt.Infeasible:
                    dm = None
        cache[s] = dm
        return dm

    need = int(p["preview_min_weeks"]) + 1
    start = next((s for s in sessions if len(h.weeks_all(s)) >= need and rf_on(s) is not None and model_on(s)), None)
    if start is None:
        return out
    portfolios, policies = list(p["portfolios"]), list(p["policies"])
    res = bt.run(sessions, start, model_on, closes, actions, aspi, rf_on, rcfg, spec, ocfg["max_weight"], portfolios,
                 policies)

    # the rules' portfolio on the latest session, with each policy's names (for the buffer): shown, not applied
    last = sessions[-1]
    today = model_on(last)
    if today is not None:
        for policy in policies:
            for port in portfolios:
                kind, k = bt.kind_k(port)
                src = f"min_variance_{k}" if kind == "equal_weight" else port
                try:
                    tgt = bt.build_target(today, port, res.final_names.get((policy, src)), spec, ocfg["max_weight"])
                except opt.Infeasible:
                    continue
                res.targets += [{"as_of": last, "policy": policy, "portfolio": port, "applied": False, "today": True,
                                 **h_} for h_ in tgt.holdings]

    out["models.cse_bt_nav"] = [{**r, "session_date": _d(r["session_date"])} for r in res.nav]
    out["models.cse_bt_event"] = [{
        "session_date": _d(e["session_date"]), "policy": e["policy"], "portfolio": e["portfolio"], "kind": e["kind"],
        "tracking_error": e["tracking_error"], "left_universe": e["left_universe"],
        "names_in": ",".join(e["names_in"]), "names_out": ",".join(e["names_out"]),
        "drift_names": ",".join(e.get("drift_names", [])), "estimate_weeks": e["estimate_weeks"],
        "preview": e["preview"], "binding": e["binding"], "model_volatility": e["model_volatility"],
        "universe_volatility_median": e["universe_volatility_median"],
        "turnover": e["turnover"], "cost": e["cost"], "nav": e["nav"]} for e in res.events]
    out["models.cse_bt_target"] = [{
        "as_of": _d(t["as_of"]), "policy": t["policy"], "portfolio": t["portfolio"], "symbol": t["symbol"],
        "applied": t["applied"], "today": bool(t.get("today", False)), "weight": t["weight"],
        "risk_contribution": t["risk_contribution"], "volatility": t["volatility"], "beta": t["beta"],
        "avg_correlation": t["avg_correlation"], "sector": t["sector"], "group_key": t["group_key"],
        "group_name": t["group_name"], "at_cap": t["at_cap"], "at_floor": t["at_floor"], "rank": t["rank"],
        "in_previous": t["in_previous"]} for t in res.targets]
    out["models.cse_bt_trade"] = [{
        "session_date": _d(t["session_date"]), "policy": t["policy"], "portfolio": t["portfolio"], "seq": t["seq"],
        "symbol": t["symbol"], "action": t["action"], "shares": t["shares"], "price": t["price"], "value": t["value"],
        "cost": t["cost"], "reason": t["reason"]} for t in res.trades]
    out["models.cse_bt_summary"] = summaries(res, rcfg)
    return out


def summaries(res: bt.Result, rcfg: dict) -> list[dict]:
    navs: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    names_end: dict[tuple[str, str], int | None] = {}
    for r in sorted(res.nav, key=lambda r: r["session_date"]):
        key = (r["policy"], r["portfolio"])
        navs[key].append((r["session_date"], r["nav"]))
        names_end[key] = r["n_names"]
    rows = []
    for (policy, port), series in sorted(navs.items()):
        start, end = series[0][0], series[-1][0]
        years = max((_d(end) - _d(start)).days / 365.25, 1 / 365.25)
        stats = bt.statistics(series, (len(series) - 1) / years)
        evs = [e for e in res.events if e["policy"] == policy and e["portfolio"] == port]
        avg = sum(v for _, v in series) / len(series)
        traded = sum(e["turnover"] for e in evs if e["kind"] != "inception")
        rows.append({"policy": policy, "portfolio": port, "start_date": _d(start), "end_date": _d(end),
                     "end_value": series[-1][1], **stats,
                     "n_rebalances": sum(1 for e in evs if e["kind"] != "drift") if evs else None,
                     "n_drift": sum(1 for e in evs if e["kind"] == "drift") if evs else None,
                     "turnover": traded / avg if evs and avg else None,
                     "costs": sum(t["cost"] for t in res.trades if t["policy"] == policy and t["portfolio"] == port)
                     if evs else None,
                     "n_names_end": names_end[(policy, port)]})
    return rows
