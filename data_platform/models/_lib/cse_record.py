"""The forward-only record of the lab's model portfolios (audit C11), shared by cse_lab_record and the lab report.

A port of MinimumLizard/CSE@e05c6f3 cse/record.py: the same rules in the same order, so the record agrees with the old
tool's record/*.csv on the same inputs. What differs is plumbing and wording:

  * the old files (record/nav.csv, holdings.csv, trades.csv) are three model output tables; the state carried from
    one session to the next is read from the rows already recorded, as the old code read its files;
  * the old files kept numbers rounded to 8 decimals (its CSV writer), and the next session read them back rounded;
    `digits` reproduces that for the port (version 1.0.0); None keeps full precision;
  * the old file's two words for a trade's direction are recorded as "increase" / "decrease" (of the shares held);
  * the old personal comparison portfolio ("my book") and the personal trade list are not ported.

Rules (METHOD.md has them in full):
  inception        each traded portfolio starts with `notional` and takes whole shares at that session's close:
                   shares = floor(w x N / (P x (1 + cost))); the cost of each trade is paid; the rest is cash.
  each session     value = shares x the last traded close (corrected for share-count events that went ex since)
                   + cash; corporate actions on holdings on their ex-date (dividends credited, splits and scrip
                   issues applied with fractions dropped, rights taken up as far as the cash allows).
  rebalance date   the first session of a month listed in rebalance_months: every name back to its new model
                   weight at that close, decreases first, then increases limited by cash; changes under min_trade
                   are skipped.
  drift band       a name is flagged when |weight - model weight| > max(band_relative x model weight, band_absolute);
                   flagged names go back to the model weight at the next session's close.
  market           the ASPI, held as index units (a benchmark, not investable).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

TRADED = ("min_variance", "risk_parity", "max_sharpe", "equal_weight")
MARKET = "market"
INDEX_UNIT = "ASI"
INCREASE, DECREASE = "increase", "decrease"


@dataclass
class State:
    shares: dict[str, float]
    targets: dict[str, float]
    flags: set[str]
    cash: float


@dataclass
class Update:
    session: str
    nav: list[dict] = field(default_factory=list)
    holdings: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    status: str = ""


def band(target: float, cfg: dict) -> float:
    return max(cfg["band_relative"] * target, cfg["band_absolute"])


def is_scheduled(session: str, sessions: list[str], months: list[int]) -> bool:
    """The first trading session of a month listed in `rebalance_months`."""
    month = session[:7]
    first = next((s for s in sessions if s[:7] == month), None)
    return first == session and int(session[5:7]) in months


def last_state(nav_rows: list[dict], holding_rows: list[dict]) -> tuple[str | None, dict[str, State]]:
    """The state at the last recorded session of one series (old last_state, from rows instead of files)."""
    if not nav_rows:
        return None, {}
    last = max(r["date"] for r in nav_rows)
    states = {}
    for r in nav_rows:
        if r["date"] == last:
            states[r["portfolio"]] = State({}, {}, set(), float(r["cash"] or 0))
    for h in holding_rows:
        if h["date"] != last:
            continue
        st = states[h["portfolio"]]
        if float(h["shares"]):
            st.shares[h["symbol"]] = float(h["shares"])
        if h["target_weight"] not in ("", None):
            st.targets[h["symbol"]] = float(h["target_weight"])
        if h["flag"] in ("1", True):
            st.flags.add(h["symbol"])
    return last, states


class Pricer:
    """The last traded close on or before the session, corrected for share-count events that went ex after that
    close (so a split that has not traded yet does not inflate the value)."""

    def __init__(self, closes: dict[str, dict[str, float]], actions: list[dict], session: str):
        self.closes, self.session = closes, session
        self.actions: dict[str, list[dict]] = {}
        for a in actions:
            self.actions.setdefault(a["symbol"], []).append(a)

    def last(self, sym: str) -> tuple[str, float] | None:
        series = self.closes.get(sym) or {}
        dates = [d for d in series if d <= self.session]
        if not dates:
            return None
        d = max(dates)
        return d, series[d]

    def price(self, sym: str) -> float | None:
        got = self.last(sym)
        if not got:
            return None
        d, p = got
        for a in self.actions.get(sym, []):
            if d < a["ex_date"] <= self.session:
                if a["type"] in ("subdivision", "scrip") and a.get("factor"):
                    p = p / a["factor"]
                elif a["type"] == "rights":
                    n, m, s = a["ratio_held"], a["ratio_new"], a["subscription_price"]
                    p = (n * p + m * s) / (n + m)
                elif a["type"] == "cash_dividend":
                    p = p - a["amount_per_share"]
        return p


def _affordable_shares(value: float, price: float, cost: float) -> int:
    return max(0, math.floor(value / (price * (1 + cost))))


def execute(st: State, targets: dict[str, float], names: list[str], pricer: Pricer, cfg: dict,
            portfolio: str, session: str, series: str, reason: str, min_trade: float) -> list[dict]:
    """Bring `names` to their model weights at today's price: decreases first, then increases limited by cash."""
    c = cfg["cost_per_side"]
    total = st.cash + sum(sh * (pricer.price(s) or 0) for s, sh in st.shares.items())
    decreases, increases = [], []
    for s in names:
        p = pricer.price(s)
        if not p:
            continue
        diff = targets.get(s, 0.0) * total - st.shares.get(s, 0) * p
        if abs(diff) < min_trade:
            continue
        (increases if diff > 0 else decreases).append((s, p, diff))
    trades = []
    for s, p, diff in decreases:
        n = min(st.shares.get(s, 0), round(-diff / p)) if targets.get(s, 0) > 0 else st.shares.get(s, 0)
        if n <= 0:
            continue
        value = n * p
        st.shares[s] = st.shares.get(s, 0) - n
        st.cash += value - value * c
        trades.append({"date": session, "series": series, "portfolio": portfolio, "symbol": s, "action": DECREASE,
                       "shares": n, "price": p, "value": value, "cost": value * c, "reason": reason})
    for s, p, diff in increases:
        n = _affordable_shares(min(diff, st.cash), p, c)
        if n <= 0:
            continue
        value = n * p
        st.shares[s] = st.shares.get(s, 0) + n
        st.cash -= value + value * c
        trades.append({"date": session, "series": series, "portfolio": portfolio, "symbol": s, "action": INCREASE,
                       "shares": n, "price": p, "value": value, "cost": value * c, "reason": reason})
    st.shares = {s: n for s, n in st.shares.items() if n > 0}
    return trades


def apply_actions(st: State, actions: list[dict], since: str, session: str, cfg: dict, portfolio: str,
                  series: str) -> list[dict]:
    """Corporate actions going ex in (since, session] on shares held at `since`."""
    rows = []
    for a in sorted(actions, key=lambda a: a["ex_date"]):
        s = a["symbol"]
        held = st.shares.get(s, 0)
        if not held or not (since < a["ex_date"] <= session):
            continue
        base = {"date": session, "series": series, "portfolio": portfolio, "symbol": s, "price": None, "cost": 0.0}
        if a["type"] == "cash_dividend":
            cash = held * a["amount_per_share"] * (1 - cfg["dividend_withholding"])
            st.cash += cash
            rows.append({**base, "action": "dividend", "shares": held, "value": cash,
                         "reason": f"ex {a['ex_date']} Rs {a['amount_per_share']:g}/sh net of "
                                   f"{cfg['dividend_withholding']:.0%} WHT"})
        elif a["type"] in ("subdivision", "scrip"):
            new = math.floor(held * a["factor"])
            st.shares[s] = new
            rows.append({**base, "action": a["type"], "shares": new - held, "value": 0.0,
                         "reason": f"ex {a['ex_date']} factor {a['factor']:.6g}; fractions dropped"})
        elif a["type"] == "rights":
            entitled = math.floor(held * a["ratio_new"] / a["ratio_held"])
            take = min(entitled, math.floor(max(st.cash, 0) / a["subscription_price"]))
            st.shares[s] = held + take
            st.cash -= take * a["subscription_price"]
            rows.append({**base, "action": "rights", "shares": take, "price": a["subscription_price"],
                         "value": take * a["subscription_price"],
                         "reason": f"ex {a['ex_date']} {a['ratio_new']:g} for {a['ratio_held']:g} @ "
                                   f"{a['subscription_price']:g}"
                                   + ("" if take == entitled else f"; {entitled - take} not taken up (cash)")})
    return rows


def _value(st: State, pricer: Pricer) -> tuple[float, dict[str, tuple[float, float]]]:
    vals = {}
    for s, n in st.shares.items():
        p = pricer.price(s) or 0.0
        vals[s] = (p, n * p)
    return sum(v for _, v in vals.values()), vals


def _snapshot(up: Update, st: State, pricer: Pricer, portfolio: str, series: str, cfg: dict, note: str) -> None:
    hv, vals = _value(st, pricer)
    nav = hv + st.cash
    up.nav.append({"date": up.session, "series": series, "portfolio": portfolio, "nav": nav, "cash": st.cash,
                   "holdings_value": hv, "note": note})
    for s in sorted(set(st.shares) | set(st.targets)):
        p, v = vals.get(s, (pricer.price(s), 0.0))
        w = v / nav if nav else 0.0
        t = st.targets.get(s, 0.0)
        flag = abs(w - t) > band(t, cfg)
        up.holdings.append({"date": up.session, "series": series, "portfolio": portfolio, "symbol": s,
                            "shares": st.shares.get(s, 0), "price": p, "value": v, "weight": w,
                            "target_weight": t, "flag": "1" if flag else "0"})


def update(last: str | None, states: dict[str, State], series: str, session: str, sessions: list[str],
           targets: dict[str, dict[str, float]] | None, pricer: Pricer, actions: list[dict], aspi: dict[str, float],
           cfg: dict, portfolios: tuple[str, ...] = TRADED) -> Update:
    """One session of one series (old update(), with the last state passed in). `targets`: the model weights of each
    portfolio computed for this session, or None when there are none today (the estimates are waiting or the
    constraints cannot all be met)."""
    up = Update(session)
    if last == session:
        up.status = f"record already has {session} for {series}; nothing written"
        return up
    if last and last > session:
        raise RuntimeError(f"record for {series} is at {last}, after session {session}")
    N = cfg["record_notional_lkr"]

    if last is None:  # inception
        if targets is None:
            up.status = "no record yet and no valid targets; nothing written"
            return up
        for p in portfolios:
            st = State({}, dict(targets[p]), set(), float(N))
            up.trades += execute(st, st.targets, list(st.targets), pricer, cfg, p, session, series, "inception", 0.0)
            _snapshot(up, st, pricer, p, series, cfg, "inception")
        units = N / aspi[session]
        up.nav.append({"date": session, "series": series, "portfolio": MARKET, "nav": N, "cash": 0.0,
                       "holdings_value": N, "note": f"inception; {units:.6f} ASPI units"})
        up.holdings.append({"date": session, "series": series, "portfolio": MARKET, "symbol": INDEX_UNIT,
                            "shares": units, "price": aspi[session], "value": N, "weight": 1.0,
                            "target_weight": 1.0, "flag": "0"})
        up.status = f"inception {session}"
    else:
        scheduled = is_scheduled(session, sessions, cfg["rebalance_months"])
        skipped = scheduled and targets is None   # e.g. constraints infeasible today
        scheduled = scheduled and targets is not None
        for p in portfolios:
            st = states[p]
            up.trades += apply_actions(st, actions, last, session, cfg, p, series)
            if scheduled:
                st.targets = dict(targets[p])
                names = sorted(set(st.targets) | set(st.shares))
                up.trades += execute(st, st.targets, names, pricer, cfg, p, session, series,
                                     "scheduled rebalance", cfg["min_trade_lkr"])
                note = "scheduled rebalance"
            elif st.flags:
                up.trades += execute(st, st.targets, sorted(st.flags), pricer, cfg, p, session, series,
                                     "drift band", cfg["min_trade_lkr"])
                note = f"drift trades: {', '.join(sorted(st.flags))}"
            else:
                note = "scheduled rebalance skipped: no valid targets today" if skipped else ""
            _snapshot(up, st, pricer, p, series, cfg, note)
        mk = states[MARKET]
        units = mk.shares[INDEX_UNIT]
        nav = units * aspi[session]
        up.nav.append({"date": session, "series": series, "portfolio": MARKET, "nav": nav, "cash": 0.0,
                       "holdings_value": nav, "note": ""})
        up.holdings.append({"date": session, "series": series, "portfolio": MARKET, "symbol": INDEX_UNIT,
                            "shares": units, "price": aspi[session], "value": nav, "weight": 1.0,
                            "target_weight": 1.0, "flag": "0"})
        up.status = (f"updated {last} → {session}" + (" (scheduled rebalance)" if scheduled else "")
                     + (" (scheduled rebalance skipped: no valid targets)" if skipped else ""))
    return up


def stored(v, digits: int | None):
    """A number as the record keeps it: rounded to `digits` decimals as the old CSV writer did (version 1.0.0), or
    as computed (None)."""
    if digits is None or v is None or isinstance(v, (bool, str)):
        return v
    return round(float(v), digits)
