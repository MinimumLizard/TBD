"""cse_security_metrics: per-share metrics for every session (audit C2, the old terminal's Panel B).

Version 1 ports the old CSE terminal's definitions (MinimumLizard/CSE@f263830 cse/metrics.py and cse/build.py),
which it computed for its own watchlist on its latest session; here they are computed for every share and every
session, from the stored facts:

- close, change and change / previous close; turnover; market capitalisation (the trade summary's, else the
  company summary's);
- position in the 52-week range the CSE publishes: (close - low) / (high - low);
- range_flag: a one-session move of more than 40% within roughly the last year (240 sessions), the sign of a
  corporate action the CSE's unadjusted prices and 52-week range do not reflect;
- volume against the mean of the previous 20 sessions (sessions without a trade count as 0);
- price return minus ASPI return over 5, 21 and 63 sessions, from the last traded price on or before each end of
  the window, flagged when the window contains a move of more than 40%.

Prices are unadjusted (no splits, bonuses or rights), as the old terminal's were. See METHOD.md.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict

import numpy as np

from .._lib.cse_calendar import ASPI, excluded_sessions, session_filter

WINDOWS = {"1w": 5, "1m": 21, "3m": 63}
AVG_SESSIONS = 20
JUMP = 0.40
YEAR_SESSIONS = 240
NO_TRADE_FLAG = "no trade before window"
JUMP_FLAG = "unadjusted corporate action in window"


class History:
    """One share's traded closes, with O(log n) look-ups: last close on or before a date, jumps in a range."""

    def __init__(self, dates: list, closes: list[float]):
        self.dates = dates
        self.closes = closes
        jumps = [False] + [abs(closes[j] / closes[j - 1] - 1) > JUMP if closes[j - 1] else False
                           for j in range(1, len(closes))]
        self.jump_count = np.cumsum(jumps)

    def last_on_or_before(self, day):
        j = bisect_right(self.dates, day) - 1
        return self.closes[j] if j >= 0 else None

    def has_jump(self, since, until) -> bool:
        """A move over 40% between two consecutive traded closes, both dated from `since` to `until`."""
        lo, hi = bisect_left(self.dates, since), bisect_right(self.dates, until) - 1
        return hi > lo and bool(self.jump_count[hi] - self.jump_count[lo])


def range_position(price, lo, hi):
    if price is None or lo is None or hi is None or hi <= lo:
        return None
    return (price - lo) / (hi - lo)


def compute(inputs, as_of):
    skip = excluded_sessions(inputs)
    where, params = session_filter(as_of)
    aspi = {r["session_date"]: r["value"] for r in inputs.rows(
        "cse.indices_daily_current", "session_date, value",
        where=" and ".join(filter(None, ["index_code = %s", where])), params=(ASPI, *params))
        if r["session_date"] not in skip}
    calendar = sorted(aspi)
    position = {d: i for i, d in enumerate(calendar)}
    aspi_history = History(calendar, [aspi[d] for d in calendar])

    prices = defaultdict(dict)
    for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, source, close, previous_close, "
                         "volume_regular, volume_total, turnover, market_cap", where=where, params=params):
        if r["session_date"] not in skip:
            prices[r["symbol"]][r["session_date"]] = r
    infos = defaultdict(dict)
    for r in inputs.rows("cse.company_info_daily", "session_date, symbol, last_traded_price, high_52w, low_52w, "
                         "market_cap, beta_triasi", where=where, params=params):
        if r["session_date"] not in skip:
            infos[r["symbol"]][r["session_date"]] = r

    rows = []
    for symbol in sorted(set(prices) | set(infos)):
        bars = prices[symbol]
        dates = sorted(bars)
        history = History(dates, [bars[d]["close"] for d in dates])
        # The volume series as the old terminal stored it: regular-market volume on daily rows, the chart's total
        # (including negotiated crossings) on backfill rows.
        volume = np.zeros(len(calendar))
        for d, bar in bars.items():
            if d in position:
                v = bar["volume_regular"] if bar["source"] == "daily" else bar["volume_total"]
                volume[position[d]] = v or 0.0
        cumulative = np.concatenate([[0.0], np.cumsum(volume)])

        for i, session in enumerate(calendar):
            bar, info = bars.get(session), infos[symbol].get(session)
            if bar is None and info is None:
                continue
            traded = bar is not None
            price = bar["close"] if traded else info["last_traded_price"]
            change = bar["close"] - bar["previous_close"] if traded and bar["previous_close"] is not None else None
            pct = change / bar["previous_close"] if change is not None and bar["previous_close"] else None
            lo, hi = (info["low_52w"], info["high_52w"]) if info else (None, None)
            year_ago = calendar[i + 1 - min(i + 1, YEAR_SESSIONS)]
            row = {"session_date": session, "symbol": symbol, "traded": traded, "close": price, "change": change,
                   "pct": pct, "turnover": bar["turnover"] if traded else None,
                   "volume": (bar["volume_regular"] if bar["source"] == "daily" else bar["volume_total"])
                   if traded else None,
                   "market_cap": (bar["market_cap"] if traded and bar["market_cap"] else
                                  (info["market_cap"] if info else None)),
                   "low_52w": lo, "high_52w": hi, "range_pos": range_position(price, lo, hi),
                   "range_flag": history.has_jump(year_ago, session),
                   "beta": info["beta_triasi"] if info else None}

            if i + 1 >= AVG_SESSIONS + 1:
                avg = (cumulative[i] - cumulative[i - AVG_SESSIONS]) / AVG_SESSIONS
                today = volume[i] if traded else 0.0
                row["vol_avg20"] = float(avg)
                row["vol_ratio"] = float(today / avg) if avg else None

            for label, k in WINDOWS.items():
                if i + 1 < k + 1:
                    continue
                start = calendar[i - k]
                p0, p1 = history.last_on_or_before(start), history.last_on_or_before(session)
                a0, a1 = aspi_history.last_on_or_before(start), aspi_history.last_on_or_before(session)
                if p0 is None or p1 is None or a0 is None or a1 is None:
                    row[f"flag_{label}"] = NO_TRADE_FLAG
                    continue
                row[f"ret_{label}"] = p1 / p0 - 1
                row[f"rel_{label}"] = (p1 / p0 - 1) - (a1 / a0 - 1)
                row[f"flag_{label}"] = JUMP_FLAG if history.has_jump(start, session) else None
            rows.append(row)
    return {"models.cse_security_session": rows, "models.cse_security_reference": reference(inputs, where, params, as_of)}


def reference(inputs, where: str, params: tuple, as_of=None) -> list[dict]:
    """Each share's latest name in the CSE's security list, and its sector label from its company profile (both
    as of the run's date). Display facts only; nothing is computed from them."""
    latest: dict[str, dict] = {}
    for r in inputs.rows("cse.security_list", "session_date, symbol, name", where=where, params=params,
                         order_by="session_date"):
        latest[r["symbol"]] = r
    sectors: dict[str, str] = {}
    for r in inputs.rows("cse.company_profiles", "symbol, sector_label", order_by="fetched_at",
                         where="fetched_at < (%s::date + 1)" if as_of else "", params=(as_of,) if as_of else ()):
        if r["sector_label"]:
            sectors[r["symbol"]] = r["sector_label"]
    return [{"symbol": s, "name": r["name"], "sector_label": sectors.get(s), "last_session": r["session_date"]}
            for s, r in sorted(latest.items())]
