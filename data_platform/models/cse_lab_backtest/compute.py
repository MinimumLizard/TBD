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
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .._lib import cse_backtest as bt
from .._lib import cse_covariance as cv
from .._lib import cse_estimates as est
from .._lib import cse_optimize as opt
from .._lib.cse_calendar import excluded_sessions
from .._lib.cse_sectors import classify, load_overrides
from ..cse_lab_record import compute as record
from ..cse_risk_estimates import compute as risk

OUTPUTS = ("models.cse_bt_summary", "models.cse_bt_nav", "models.cse_bt_event", "models.cse_bt_target",
           "models.cse_bt_trade", "models.cse_bt_risk_test")
BASELINE = "identity"                      # the old tool's estimator: what every other is compared with
BLOCK, DRAWS, SEED = 5, 2000, 20261113     # the risk test's paired block bootstrap (fixed seed: the same rows each run)


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


@dataclass
class Setup:
    """The facts and the rules' inputs for a walk-forward run: built once, shared by compute() and the research
    script that compares estimators and policies (scripts/research/lab_tournament.py)."""
    params: dict
    h: est.History
    sessions: list[str]
    aspi: dict[str, float]
    closes: dict
    actions: list[dict]
    rf_on: Callable[[str], float | None]
    estimates_on: Callable[[str], tuple[est.Outcome, dict, dict] | None]
    ocfg: dict
    rcfg: dict
    spec: dict
    _cache: dict = field(default_factory=dict)

    @property
    def lags(self) -> int:
        return int(self.params.get("daily_lags", 2))

    def model_on(self, s: str, covariance: str | None = None) -> bt.DateModel | None:
        """The rules' inputs on session s, with the covariance by `covariance` (default: the version's own)."""
        method = covariance or self.params.get("covariance", "identity")
        if (s, method) in self._cache:
            return self._cache[(s, method)]
        dm = None
        got = self.estimates_on(s)
        if got is not None and got[0].estimates is not None:
            o, gmap, glabels = got
            e = o.estimates
            cov = e.cov if method == BASELINE else covariance_by(method, self.h, e, self.lags)[0]
            prob = opt.make_problem(e.symbols, e.sectors, cov, e.er, e.rf, e.median_turnover, self.ocfg, gmap)
            try:
                opt.check_feasible(prob)
                full = {"min_variance": opt.min_variance(prob), "max_sharpe": opt.max_sharpe(prob)}
                vol = dict(zip(e.symbols, np.sqrt(np.diag(cov)).tolist()))
                dm = bt.DateModel(s, prob, full, len(e.weeks), o.status != "ok", e.rf, e.beta.to_dict(), vol, glabels,
                                  float(np.median(list(vol.values()))))
            except opt.Infeasible:
                dm = None
        self._cache[(s, method)] = dm
        return dm

    def start(self) -> str | None:
        """The first session with enough history for the estimates and a published bill yield."""
        need = int(self.params["preview_min_weeks"]) + 1
        return next((s for s in self.sessions if len(self.h.weeks_all(s)) >= need and self.rf_on(s) is not None
                     and self.model_on(s)), None)


def daily_returns(h: est.History, e: est.Estimates) -> tuple[np.ndarray, float]:
    """The daily total returns of the estimate's shares over the span of its weekly returns
    (_lib/cse_covariance.daily_window)."""
    return cv.daily_window(h.tri, h.sessions, e.symbols, e.weeks[0], e.session)


def covariance_by(method: str, h: est.History, e: est.Estimates, lags: int = 2) -> tuple[np.ndarray, float]:
    if method == "daily":
        D, per_year = daily_returns(h, e)
        return cv.daily(D, per_year, lags)
    return cv.estimate(method, e.returns.to_numpy(), e.market.to_numpy())


# --- the risk test (version 1.1.0): which covariance estimator forecasts risk best -------------------------------

def weekly_dates(su: Setup, start: str) -> list[str]:
    """The last session on or before each Wednesday, from the walk-forward start."""
    out: list[str] = []
    for w in est.wednesdays(start, su.sessions[-1]):
        s = max((x for x in su.sessions if x <= w), default=None)
        if s and s >= start and (not out or s != out[-1]):
            out.append(s)
    return out


def left_alone(su: Setup, symbols: list[str], w: np.ndarray, s0: str, s1: str) -> tuple[list[float], np.ndarray]:
    """Daily returns of weights w set at s0's close and left alone until s1's close (total returns, no costs), and
    the weights at s1."""
    days = [s for s in su.sessions if s0 <= s <= s1]
    lv = np.column_stack([est.sample_on_or_before(su.h.tri[s], days).to_numpy() for s in symbols])
    rel = lv / lv[0]
    rel = np.where(np.isfinite(rel), rel, 1.0)
    value = rel @ w
    end = rel[-1] * w
    return list(value[1:] / value[:-1] - 1), end / end.sum()


def variance_ratio(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Variance of a over variance of b, with a 90 % interval from a paired moving-block bootstrap (blocks of BLOCK
    days, so runs of calm and of turbulent days stay together; the same days are drawn for both series)."""
    rng = np.random.default_rng(SEED)
    n = len(a)
    starts = np.arange(n - BLOCK + 1)
    ratios = []
    for _ in range(DRAWS):
        idx = np.concatenate([np.arange(s, s + BLOCK) for s in rng.choice(starts, size=math.ceil(n / BLOCK))])[:n]
        ratios.append(np.var(a[idx], ddof=1) / np.var(b[idx], ddof=1))
    return float(np.var(a, ddof=1) / np.var(b, ddof=1)), float(np.quantile(ratios, 0.05)), float(np.quantile(ratios, 0.95))


def risk_test(su: Setup, start: str, k: int | None, methods: tuple[str, ...] = cv.METHODS) -> list[dict]:
    """Every week from `start`, the minimum-variance portfolio is built with each estimator (the lab's caps; k None:
    the full portfolio, else the K-name version with its buffer) and held for a week without costs. Per estimator:
    the realised volatility (what a minimum-variance portfolio exists to keep low), the volatility it forecast, how
    much its weights changed from week to week, and its realised variance against the baseline estimator's with a
    90 % interval. Two reference rows: equal weight across the universe, and the ASPI.

    Each week's portfolio reads only facts up to its date; the returns that judge it come after. Nothing here looks
    at which estimator earned more: with months of data a difference in return is noise, a difference in risk is not."""
    if not methods:
        return []
    dates = weekly_dates(su, start)
    spec = {**su.spec, "tolerance": 0}          # the test compares estimators, not trading rules
    series = {m: [] for m in methods}
    forecast = {m: [] for m in methods}
    turnover = {m: [] for m in methods}
    names = {m: [] for m in methods}
    prev: dict = {m: None for m in methods}
    prev_names: dict = {m: None for m in methods}
    equal: list[float] = []
    used: list[str] = []
    for s0, s1 in zip(dates, dates[1:]):
        models = {m: su.model_on(s0, m) for m in methods}
        if any(v is None for v in models.values()):
            continue
        used.append(s0)
        for m, dm in models.items():
            p = dm.problem
            symbols, w = p.symbols, dm.full["min_variance"]
            if k is not None:
                try:
                    tgt = bt.build_target(dm, f"min_variance_{k}", prev_names[m], spec, su.ocfg["max_weight"])
                    prev_names[m] = tgt.names
                    symbols, w = tgt.names, np.array([tgt.weights[x] for x in tgt.names])
                except opt.Infeasible:      # as the lab does: keep what it had (the first time: the full portfolio)
                    if prev[m] is not None and all(x in p.symbols for x in prev[m][0]):
                        symbols, w = prev[m]
            ids = [p.symbols.index(x) for x in symbols]
            r, end = left_alone(su, symbols, w, s0, s1)
            series[m] += r
            forecast[m].append(float(math.sqrt(w @ p.cov[np.ix_(ids, ids)] @ w)))
            names[m].append(float(1 / (w ** 2).sum()))
            if prev[m] is not None:
                old, new = dict(zip(*prev[m])), dict(zip(symbols, w))
                turnover[m].append(sum(abs(new.get(x, 0) - old.get(x, 0)) for x in set(old) | set(new)) / 2)
            prev[m] = (symbols, end)
        p = models[methods[0]].problem
        equal += left_alone(su, p.symbols, np.full(len(p.symbols), 1 / len(p.symbols)), s0, s1)[0]
    if len(used) < 4:
        return []
    days = [s for s in su.sessions if used[0] <= s <= dates[-1]]
    per_year = (len(days) - 1) / max((_d(days[-1]) - _d(days[0])).days / 365.25, 1 / 365.25)
    ann = lambda r: float(np.std(r, ddof=1) * math.sqrt(per_year))
    aspi = np.array([su.aspi[s] for s in days])
    scope = "full" if k is None else f"k{k}"
    common = {"scope": scope, "start_date": _d(used[0]), "end_date": _d(dates[-1]), "n_weeks": len(used),
              "n_days": len(days) - 1}
    rows = [{**common, "estimator": "ref_equal_weight", "realised_volatility": ann(equal)},
            {**common, "estimator": "ref_market", "realised_volatility": ann(aspi[1:] / aspi[:-1] - 1)}]
    base = np.array(series[BASELINE]) if BASELINE in series else None
    for m in methods:
        a = np.array(series[m])
        ratio = variance_ratio(a, base) if base is not None and m != BASELINE else (1.0, 1.0, 1.0) if m == BASELINE else (None,) * 3
        rows.append({**common, "estimator": m, "realised_volatility": ann(a),
                     "forecast_volatility": float(np.mean(forecast[m])),
                     "weekly_turnover": float(np.mean(turnover[m])) if turnover[m] else None,
                     "effective_names": float(np.mean(names[m])),
                     "variance_ratio": ratio[0], "ratio_low": ratio[1], "ratio_high": ratio[2]})
    return rows


def setup(inputs, as_of) -> Setup | None:
    p = inputs.params
    skip = excluded_sessions(inputs)
    h = risk.history(inputs, as_of, skip)
    sessions, aspi, closes, actions = record.market_facts(inputs, as_of, skip)
    if not sessions or not h.sessions:
        return None
    stored = risk.latest_version(inputs, "cse.sector_overrides", "overrides", as_of)
    overrides = load_overrides({"overrides": stored["overrides"]} if stored else {})
    lists, labels, groups = risk.security_lists(inputs, as_of), risk.sector_labels(inputs), risk.ownership_groups(inputs, as_of)
    bills = risk.bill_yields(inputs)
    ecfg = {k: p[k] for k in ("min_history_weeks", "min_traded_share", "min_median_turnover_lkr", "equity_risk_premium")}
    ocfg = {k: p[k] for k in ("max_weight", "max_sector_weight", "max_group_weight", "participation", "days_to_build",
                              "notional_lkr")}
    rcfg = {k: p[k] for k in ("record_notional_lkr", "cost_per_side", "dividend_withholding", "rebalance_months",
                              "band_relative", "band_absolute", "min_trade_lkr", "te_threshold")}

    def rf_on(s: str) -> float | None:
        return risk.risk_free(p["risk_free"], bills, _d(s))[0]

    seen: dict[str, tuple | None] = {}

    def estimates_on(s: str):
        if s not in seen:
            day, rf = _d(s), rf_on(s)
            if rf is None:
                seen[s] = None
            else:
                securities = lists.at(day) or []
                lab = labels.at(day) or {}
                equities = [x.symbol for x in securities if x.symbol.endswith(est.EQUITY_SUFFIXES)]
                sectors = {x: classify(x, lab.get(x), overrides) for x in equities}
                gmap, glabels = risk.for_symbols(groups.at(day), equities)
                o = est.run_date(h, securities, sectors, set(), {**ecfg, "risk_free_annual": rf}, s, p["preview_min_weeks"])
                seen[s] = (o, gmap, glabels)
        return seen[s]

    return Setup(p, h, sessions, aspi, closes, actions, rf_on, estimates_on, ocfg, rcfg, p["fewer_names"])


def compute(inputs, as_of):
    out: dict[str, list[dict]] = {t: [] for t in OUTPUTS}
    su = setup(inputs, as_of)
    if su is None:
        return out
    p, sessions, model_on, rcfg, spec, ocfg = su.params, su.sessions, su.model_on, su.rcfg, su.spec, su.ocfg
    closes, actions, aspi, rf_on = su.closes, su.actions, su.aspi, su.rf_on

    start = su.start()
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
    methods = tuple(p.get("risk_test_estimators", []))
    for k in p.get("risk_test_sizes", []):
        out["models.cse_bt_risk_test"] += risk_test(su, start, k or None, methods)
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
