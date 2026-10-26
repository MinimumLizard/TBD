"""cse_lab_record: the forward-only record of the lab's model portfolios (audit C11). INTERNAL RESEARCH: unpublished
(config/entitlements.yaml); no page or API route reads it; the owner reads it through the lab report job.

Version 1.0.0 ports MinimumLizard/CSE@e05c6f3 cse/record.py (data_platform/models/_lib/cse_record.py) and continues
the old tool's series v1-52w-grp20 from its inception on 2026-10-07: whole shares, 1.12 % per side, the quarterly
rebalance dates, the drift band, dividends, splits, scrip issues and rights taken up, numbers kept to 8 decimals as
the old files kept them. Its rows for 2026-10-07 to 2026-10-15 equal the old record/*.csv.
Version 1.1.0 records the 1.1.0 portfolios (the full ones and the versions with 10 and 15 names) from a neutral
Rs 1 mn each, starting at the first run that finds valid model weights: never backfilled.

Append-only, as the old files: the rows already recorded are read back and returned unchanged, and only the sessions
after the last one recorded are added, one at a time, in order. A session already recorded is never rewritten, even
when the inputs of a past date change later. A look at the past (as_of) returns the rows recorded up to it.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .._lib import cse_record as rec
from .._lib.cse_calendar import ASPI, excluded_sessions, session_filter

NAV = "models.cse_lab_nav"
HOLDING = "models.cse_lab_holding"
TRADE = "models.cse_lab_trade"
OUTPUTS = (NAV, HOLDING, TRADE)


# --- reading -----------------------------------------------------------------------------------------------------

def recorded(inputs, series: str) -> dict[str, list[dict]]:
    """This version's rows already recorded for the series, as stored."""
    v = inputs.version.method_version
    out = {}
    for t in OUTPUTS:
        rows = inputs.rows(t, "*", where="method_version = %s and series = %s", params=(v, series))
        for r in rows:
            r.pop("run_id", None)
            r.pop("method_version", None)
        out[t] = rows
    return out


def targets_by_date(inputs, as_of, portfolios: tuple[str, ...]) -> dict[str, dict[str, dict[str, float]] | None]:
    """The lab's model weights per date: {date: {portfolio: {symbol: weight}}}, or None for a date without valid
    weights (estimates waiting, a preview, constraints that cannot all hold, a portfolio not formed)."""
    where, params = session_filter(as_of, "as_of")
    ok = {r["as_of"] for r in inputs.rows("models.cse_lab_summary", "as_of, status, preview", where=where,
                                          params=params) if r["status"] == "ok" and not r["preview"]}
    formed = defaultdict(set)
    for r in inputs.rows("models.cse_lab_portfolio", "as_of, portfolio, status", where=where, params=params):
        if r["status"] == "ok":
            formed[r["as_of"]].add(r["portfolio"])
    weights: dict[dt.date, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for r in inputs.rows("models.cse_lab_weight", "as_of, portfolio, symbol, weight", where=where, params=params,
                         order_by="as_of, portfolio, symbol"):
        if r["portfolio"] in portfolios and r["weight"] > 1e-6:
            weights[r["as_of"]][r["portfolio"]][r["symbol"]] = r["weight"]
    out = {}
    for d in ok:
        if all(p in formed[d] and weights[d].get(p) for p in portfolios):
            out[d.isoformat()] = {p: dict(weights[d][p]) for p in portfolios}
    return out


def market_facts(inputs, as_of, skip) -> tuple[list[str], dict[str, float], dict[str, dict[str, float]], list[dict]]:
    """The ASPI calendar and values, every share's closes, and the corporate actions in use (old effective())."""
    where, params = session_filter(as_of)
    aspi = {r["session_date"].isoformat(): r["value"] for r in inputs.rows(
        "cse.indices_daily_current", "session_date, value",
        where=" and ".join(filter(None, ["index_code = %s", where])), params=(ASPI, *params))
        if r["session_date"] not in skip}
    closes: dict[str, dict[str, float]] = defaultdict(dict)
    for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, close", where=where, params=params):
        if r["session_date"] not in skip:
            closes[r["symbol"]][r["session_date"].isoformat()] = r["close"]
    actions = [{"symbol": a["symbol"], "type": a["action_type"], "ex_date": a["ex_date"].isoformat(),
                "amount_per_share": a["amount_per_share"], "ratio_new": a["ratio_new"], "ratio_held": a["ratio_held"],
                "factor": a["factor"], "subscription_price": a["subscription_price"]}
               for a in inputs.rows("models.cse_corporate_action_used",
                                    "action_id, symbol, action_type, ex_date, amount_per_share, ratio_new, ratio_held, "
                                    "factor, subscription_price", order_by="ex_date, action_id")
               if a["ex_date"] is not None]
    return sorted(aspi), aspi, dict(closes), actions


# --- the record --------------------------------------------------------------------------------------------------

def _row_date(r: dict) -> str:
    d = r["session_date"]
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def state_of(rows: dict[str, list[dict]]) -> tuple[str | None, dict[str, rec.State]]:
    """The last recorded session and the state there, as the old code read it from its files."""
    nav = [{"date": _row_date(r), "portfolio": r["portfolio"], "cash": r["cash"]} for r in rows[NAV]]
    hold = [{"date": _row_date(r), "portfolio": r["portfolio"], "symbol": r["symbol"], "shares": r["shares"],
             "target_weight": r["target_weight"], "flag": r["outside_band"]} for r in rows[HOLDING]]
    return rec.last_state(nav, hold)


def to_rows(up: rec.Update, digits: int | None, next_seq: dict) -> dict[str, list[dict]]:
    """An update's rows as the tables keep them (numbers rounded as the old files when `digits` is set)."""
    k = lambda v: rec.stored(v, digits)  # noqa: E731
    day = dt.date.fromisoformat(up.session)
    nav = [{"series": r["series"], "session_date": day, "portfolio": r["portfolio"], "nav": k(r["nav"]),
            "cash": k(r["cash"]), "holdings_value": k(r["holdings_value"]), "note": r["note"]} for r in up.nav]
    hold = [{"series": r["series"], "session_date": day, "portfolio": r["portfolio"], "symbol": r["symbol"],
             "shares": k(r["shares"]), "price": k(r["price"]), "value": k(r["value"]), "weight": k(r["weight"]),
             "target_weight": k(r["target_weight"]), "outside_band": r["flag"] == "1"} for r in up.holdings]
    trades = []
    for r in up.trades:
        key = (r["portfolio"],)
        next_seq[key] = next_seq.get(key, 0) + 1
        trades.append({"series": r["series"], "session_date": day, "portfolio": r["portfolio"], "seq": next_seq[key],
                       "symbol": r["symbol"], "action": r["action"], "shares": k(r["shares"]), "price": k(r["price"]),
                       "value": k(r["value"]), "cost": k(r["cost"]), "reason": r["reason"]})
    return {NAV: nav, HOLDING: hold, TRADE: trades}


def advance(rows: dict[str, list[dict]], todo: list[str], sessions: list[str], targets: dict, aspi: dict,
            closes: dict, actions: list[dict], cfg: dict, series: str, portfolios: tuple[str, ...],
            digits: int | None, wait_for_targets: bool) -> tuple[dict[str, list[dict]], list[str]]:
    """Record the sessions in `todo`, in order, after what `rows` holds; return all rows and each session's status.
    Without a record yet, the first session with valid model weights is the inception; a session before it adds
    nothing (wait_for_targets: try the next one; otherwise stop)."""
    rows = {t: list(v) for t, v in rows.items()}
    statuses = []
    last, states = state_of(rows)
    for session in todo:
        if last is not None and session <= last:
            continue
        pricer = rec.Pricer(closes, actions, session)
        up = rec.update(last, states, series, session, sessions, targets.get(session), pricer, actions, aspi, cfg,
                        portfolios)
        statuses.append(f"{session}: {up.status}")
        if not up.nav:
            if last is None and not wait_for_targets:
                break
            continue
        new = to_rows(up, digits, {})
        for t in OUTPUTS:
            rows[t] += new[t]
        last, states = state_of(new)          # read back as stored, as the old code read its files
    return rows, statuses


def compute(inputs, as_of):
    p = inputs.params
    series, portfolios = p["series"], tuple(p["portfolios"])
    have = recorded(inputs, series)
    if as_of:                        # a look at the past: what had been recorded by then
        return {t: [r for r in have[t] if r["session_date"] <= as_of] for t in OUTPUTS}
    sessions, aspi, closes, actions = market_facts(inputs, None, excluded_sessions(inputs))
    targets = targets_by_date(inputs, None, portfolios)
    last = max((_row_date(r) for r in have[NAV]), default=None)
    if last is not None:
        todo = [s for s in sessions if s > last]
    elif p.get("inception"):
        todo = [s for s in sessions if s >= str(p["inception"])]
    else:                            # the first run: the record starts at the latest session (never backfilled)
        todo = sessions[-1:]
    cfg = {k: p[k] for k in ("record_notional_lkr", "cost_per_side", "dividend_withholding", "rebalance_months",
                             "band_relative", "band_absolute", "min_trade_lkr")}
    out, _ = advance(have, todo, sessions, targets, aspi, closes, actions, cfg, series, portfolios,
                     p.get("digits"), wait_for_targets=bool(p.get("inception")))
    return out
