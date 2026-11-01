"""The portfolio lab's walk-forward test (cse_lab_backtest): what the lab's own rules would have built and held on
each past date, using only what was known on that date, and how the holdings would have fared.

Shared pieces, unchanged: the universe and estimates (cse_estimates.run_date, with the preview on the longest history
of at least 26 weeks while a full year is missing), the problem and the solvers (cse_optimize: the caps, the K-name
selection with its buffer, the floor), and the record's execution rules (cse_record: whole shares, the cost per side,
dividends, splits, scrip and rights on their ex-date, the drift band).

New here: the walk forward itself, and the rebalancing policies.
  quarterly  the lab's rule: new model weights on the first session of January, April, July and October; between
             them only the drift band.
  dynamic    a check on the first session of every month: the rules' portfolio is built afresh, and the holdings are
             rebalanced to it when they have moved away from it by more than a threshold, measured as the estimated
             tracking error between the two (or when a holding has left the universe); on the quarterly dates
             always. Between checks, the drift band.

Every decision on a date reads only the facts up to that date (the estimates through run_date, which never looks
past its session; the prices through the record's Pricer). Pure: no database; the model's compute.py reads the facts
and writes the rows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import cse_optimize as opt
from . import cse_record as rec

QUARTERLY, DYNAMIC = "quarterly", "dynamic"
MARKET, BILLS = "market", "bills"


@dataclass
class DateModel:
    """The rules' inputs on one date: the problem (estimates, caps) and the full portfolios."""
    session: str
    problem: opt.Problem
    full: dict[str, np.ndarray]
    weeks: int
    preview: bool
    rf: float
    beta: dict[str, float]
    vol: dict[str, float]
    labels: dict[str, str]
    median_vol: float | None = None      # of every share in the date's universe (for "steadier than most")


@dataclass
class Target:
    """One portfolio's model weights on a date, with what explains each holding."""
    portfolio: str
    names: list[str]
    weights: dict[str, float]
    holdings: list[dict]
    binding: str
    volatility: float


@dataclass
class Book:
    state: rec.State
    names: list[str] = field(default_factory=list)


@dataclass
class Result:
    nav: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    targets: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    final_names: dict[tuple[str, str], list[str]] = field(default_factory=dict)   # (policy, portfolio) -> names held


def kind_k(portfolio: str) -> tuple[str, int]:
    kind, k = portfolio.rsplit("_", 1)
    return kind, int(k)


def check_dates(sessions: list[str], start: str) -> list[str]:
    """The start, then the first session of every month after it."""
    out, seen = [start], {start[:7]}
    for s in sessions:
        if s > start and s[:7] not in seen:
            seen.add(s[:7])
            out.append(s)
    return out


def build_target(dm: DateModel, portfolio: str, prev_names: list[str] | None, spec: dict, max_weight: float) -> Target:
    """The lab's K-name rule on this date (as cse_portfolio_lab's FewerNames): the K largest names of the full
    portfolio of the same kind, a name already held staying while it ranks in the top buffer x K, re-optimised with
    the cap max(max_weight, 1.5 / K) and the floor 0.5 / K. Equal weight uses minimum variance's names."""
    kind, k = kind_k(portfolio)
    source = "min_variance" if kind == "equal_weight" else kind
    p = dm.problem
    ranked = opt.ranking(dm.full[source], p.symbols)
    names = opt.retail_names(ranked, k, prev_names, spec["buffer"])
    if len(names) < k:
        raise opt.Infeasible(f"the full portfolio has only {len(names)} names")
    idx = {s: i for i, s in enumerate(p.symbols)}
    cap, floor = opt.retail_cap(k, max_weight), opt.retail_floor(k)
    sub = opt.subproblem(p, [idx[s] for s in names], cap)
    w = opt.solve_retail(kind, sub, floor)
    rc = opt.risk_contributions(w, sub.cov)
    sd = np.sqrt(np.diag(sub.cov))
    corr = sub.cov / np.outer(sd, sd)
    rank = {s: i + 1 for i, s in enumerate(ranked)}
    holdings = []
    for i, s in enumerate(names):
        others = [j for j in range(len(names)) if j != i]
        holdings.append({
            "symbol": s, "weight": float(w[i]), "risk_contribution": float(rc[i]), "volatility": float(sd[i]),
            "beta": dm.beta.get(s), "avg_correlation": float(np.mean(corr[i, others])) if others else None,
            "sector": sub.sectors[i], "group_key": sub.groups[i] if sub.groups else s,
            "group_name": dm.labels.get(sub.groups[i]) if sub.groups else None,
            "at_cap": bool(kind != "equal_weight" and w[i] >= sub.caps[i] - opt.AT_CAP),
            "at_floor": bool(kind != "equal_weight" and w[i] <= floor + opt.AT_CAP),
            "rank": rank.get(s), "in_previous": bool(prev_names and s in prev_names)})
    return Target(portfolio, names, {h["symbol"]: h["weight"] for h in holdings}, holdings,
                  "; ".join(opt.binding(w, sub, None if kind == "equal_weight" else floor)) if kind != "equal_weight" else "",
                  float(math.sqrt(w @ sub.cov @ w)))


def tracking_error(current: dict[str, float], target: dict[str, float], dm: DateModel) -> float:
    """The estimated annual tracking error between the current weights and the target, on the date's covariance.
    Infinite when a holding has left the universe (it can no longer be measured, and the rules would not keep it)."""
    idx = {s: i for i, s in enumerate(dm.problem.symbols)}
    names = sorted(set(current) | set(target))
    if any(n not in idx for n in names if current.get(n, 0) > 1e-9):
        return math.inf
    ids = [idx[n] for n in names]
    d = np.array([current.get(n, 0.0) - target.get(n, 0.0) for n in names])
    return float(math.sqrt(max(d @ dm.problem.cov[np.ix_(ids, ids)] @ d, 0.0)))


def weights_of(st: rec.State, pricer: rec.Pricer) -> tuple[float, dict[str, float]]:
    vals = {s: n * (pricer.price(s) or 0.0) for s, n in st.shares.items()}
    nav = sum(vals.values()) + st.cash
    return nav, {s: v / nav for s, v in vals.items()} if nav else {}


def run(sessions: list[str], start: str, model_on: Callable[[str], DateModel | None], closes: dict, actions: list[dict],
        aspi: dict[str, float], rf_on: Callable[[str], float | None], cfg: dict, spec: dict, max_weight: float,
        portfolios: list[str], policies: list[str]) -> Result:
    """Walk forward from `start` to the last session. `model_on(session)` returns the rules' inputs on a check date
    (None when there are none: estimates waiting, constraints that cannot all be met)."""
    out = Result()
    checks = set(check_dates(sessions, start))
    books: dict[str, dict[str, Book]] = {p: {} for p in policies}
    seq: dict[tuple, int] = {}
    days = [s for s in sessions if s >= start]
    market_units = bills = None
    last = None
    for s in days:
        pricer = rec.Pricer(closes, actions, s)
        dm = model_on(s) if s in checks else None
        scheduled = rec.is_scheduled(s, sessions, cfg["rebalance_months"])
        for policy in policies:
            for port in portfolios:
                book = books[policy].get(port)
                trades = []
                event = None
                if book is not None:
                    trades += rec.apply_actions(book.state, actions, last, s, cfg, port, policy)
                if dm is not None:
                    act = book is None or (policy == QUARTERLY and scheduled) or policy == DYNAMIC
                    if act:
                        kind, k = kind_k(port)       # equal weight follows minimum variance's names (listed first)
                        src_port = f"min_variance_{k}" if kind == "equal_weight" else port
                        prev = books[policy][src_port].names if src_port in books[policy] else None
                        try:
                            tgt = build_target(dm, port, prev, spec, max_weight)
                        except opt.Infeasible as exc:
                            out.notes.append(f"{s} {policy} {port}: {exc}")
                            tgt = None
                        if tgt is not None:
                            te = None
                            if book is None:
                                why = "inception"
                            else:
                                _, current = weights_of(book.state, pricer)
                                te = tracking_error(current, tgt.weights, dm)
                                why = ("scheduled" if scheduled else
                                       "threshold" if policy == DYNAMIC and te > cfg["te_threshold"] else None)
                            out.targets += [{"as_of": s, "policy": policy, "portfolio": port, "applied": why is not None,
                                             **h} for h in tgt.holdings]
                            if why is not None:
                                if book is None:
                                    book = books[policy][port] = Book(rec.State({}, {}, set(), float(cfg["record_notional_lkr"])))
                                st = book.state
                                before = set(book.names)
                                st.targets = dict(tgt.weights)
                                names = sorted(set(st.targets) | set(st.shares))
                                trades += rec.execute(st, st.targets, names, pricer, cfg, port, s, policy, why,
                                                      0.0 if why == "inception" else cfg["min_trade_lkr"])
                                book.names = list(tgt.names)
                                event = {"session_date": s, "policy": policy, "portfolio": port, "kind": why,
                                         "tracking_error": None if te is None or math.isinf(te) else te,
                                         "left_universe": te is not None and math.isinf(te),
                                         "names_in": sorted(set(tgt.names) - before) if before else sorted(tgt.names),
                                         "names_out": sorted(before - set(tgt.names)), "estimate_weeks": dm.weeks,
                                         "preview": dm.preview, "binding": tgt.binding,
                                         "model_volatility": tgt.volatility,
                                         "universe_volatility_median": dm.median_vol}
                if book is None:
                    continue
                st = book.state
                if event is None and st.flags:
                    trades += rec.execute(st, st.targets, sorted(st.flags), pricer, cfg, port, s, policy,
                                          "drift band", cfg["min_trade_lkr"])
                    event = {"session_date": s, "policy": policy, "portfolio": port, "kind": "drift",
                             "tracking_error": None, "left_universe": False, "names_in": [], "names_out": [],
                             "estimate_weeks": None, "preview": None, "binding": None, "model_volatility": None,
                             "universe_volatility_median": None, "drift_names": sorted(st.flags)}
                nav, w = weights_of(st, pricer)
                st.flags = {n for n in set(w) | set(st.targets) if abs(w.get(n, 0.0) - st.targets.get(n, 0.0))
                            > rec.band(st.targets.get(n, 0.0), cfg)}
                for t in trades:
                    key = (policy, port)
                    seq[key] = seq.get(key, 0) + 1
                    out.trades.append({**t, "session_date": s, "policy": policy, "seq": seq[key]})
                if event:
                    event["turnover"] = sum(t["value"] for t in trades if t["action"] in (rec.INCREASE, rec.DECREASE))
                    event["cost"] = sum(t["cost"] for t in trades)
                    event["nav"] = nav
                    out.events.append(event)
                out.nav.append({"session_date": s, "policy": policy, "portfolio": port, "nav": nav, "cash": st.cash,
                                "n_names": sum(1 for v in st.shares.values() if v > 0)})
        if not any(books[p] for p in policies):
            continue                         # nothing formed yet: the benchmarks start with the portfolios
        N = float(cfg["record_notional_lkr"])
        if market_units is None:
            market_units, bills, bills_day = N / aspi[s], N, s
        else:
            rf = rf_on(s) or 0.0
            gap = (_date(s) - _date(bills_day)).days
            bills *= (1 + rf) ** (gap / 365)
            bills_day = s
        for policy in policies:
            out.nav.append({"session_date": s, "policy": policy, "portfolio": MARKET, "nav": market_units * aspi[s],
                            "cash": 0.0, "n_names": None})
            out.nav.append({"session_date": s, "policy": policy, "portfolio": BILLS, "nav": bills, "cash": bills,
                            "n_names": None})
        last = s
    out.final_names = {(p, port): list(b.names) for p in policies for port, b in books[p].items()}
    return out


def _date(s: str):
    import datetime as dt
    return dt.date.fromisoformat(s)


def statistics(navs: list[tuple[str, float]], sessions_per_year: float) -> dict:
    """Total return, annualised volatility of daily returns, the largest fall from a peak, and the best and worst
    calendar months, from a NAV series [(date, value)] in date order."""
    if len(navs) < 2:
        return {"total_return": None, "volatility": None, "max_drawdown": None, "best_month": None, "worst_month": None}
    v = np.array([x for _, x in navs], dtype=float)
    r = v[1:] / v[:-1] - 1
    peak = v.copy()                         # the running highest value so far
    for i in range(1, len(v)):
        peak[i] = max(peak[i - 1], v[i])
    months: dict[str, list[float]] = {}
    for d, x in navs:
        months.setdefault(d[:7], []).append(x)
    keys = sorted(months)
    mret = [months[keys[i]][-1] / months[keys[i - 1]][-1] - 1 for i in range(1, len(keys))]
    return {"total_return": float(v[-1] / v[0] - 1),
            "volatility": float(np.std(r, ddof=1) * math.sqrt(sessions_per_year)) if len(r) > 1 else None,
            "max_drawdown": float(np.min(v / peak - 1)),
            "best_month": float(max(mret)) if mret else None, "worst_month": float(min(mret)) if mret else None}
