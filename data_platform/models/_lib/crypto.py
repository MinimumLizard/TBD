"""Shared by the crypto models: reading Bitstamp's daily closes, and the moving averages every crypto method uses.

Everything here is trailing: a value for day D uses closes up to and including D, never after, so a model built on
these functions gives a row for D that does not change when later days arrive (each model's tests check this).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

GENESIS = dt.date(2009, 1, 3)          # the Bitcoin genesis block's date (block 0)
# The four halvings so far: the UTC dates of blocks 210,000, 420,000, 630,000 and 840,000.
HALVINGS: dict[int, dt.date] = {
    1: dt.date(2012, 11, 28),
    2: dt.date(2016, 7, 9),
    3: dt.date(2020, 5, 11),
    4: dt.date(2024, 4, 20),
}


def day_filter(as_of: dt.date | None) -> tuple[str, tuple]:
    return ("day <= %s", (as_of,)) if as_of else ("", ())


def closes(inputs, as_of: dt.date | None, pairs: list[str] | None = None) -> dict[str, pd.Series]:
    """{pair: daily closes}, indexed by every calendar day from the pair's first candle to its last. A day Bitstamp
    has no candle for (none so far) is NaN, never filled in."""
    where, params = day_filter(as_of)
    if pairs:
        where = " and ".join(filter(None, [where, "pair = any(%s)"]))
        params = (*params, list(pairs))
    out: dict[str, list] = {}
    for r in inputs.rows("crypto.ohlc_daily", "pair, day, close", where=where, params=params, order_by="pair, day"):
        out.setdefault(r["pair"], []).append((r["day"], r["close"]))
    series = {}
    for pair, rows in out.items():
        s = pd.Series([c for _, c in rows], index=pd.DatetimeIndex([d for d, _ in rows]), dtype=float)
        series[pair] = s.asfreq("D")
    return series


def sma(s: pd.Series, n: int) -> pd.Series:
    """Simple moving average of the last n days, only where all n days have a close."""
    return s.rolling(n, min_periods=n).mean()


def ema(values: np.ndarray, n: int) -> np.ndarray:
    """Exponential moving average with alpha = 2 / (n + 1), started from the simple average of the first n values
    (the common convention, e.g. TradingView's). NaN before that. Values must have no gaps."""
    out = np.full(len(values), np.nan)
    if len(values) < n:
        return out
    alpha = 2.0 / (n + 1)
    e = float(np.mean(values[:n]))
    out[n - 1] = e
    for i in range(n, len(values)):
        e = alpha * values[i] + (1 - alpha) * e
        out[i] = e
    return out


def weekly_sma_and_ema(s: pd.Series, sma_weeks: list[int], ema_weeks: list[int]) -> dict[str, pd.Series]:
    """Weekly averages as a weekly chart shows them on each day.

    Weeks run Monday to Sunday (UTC), so a week's close is its Sunday close. On day D the latest week is the one D is
    in, with D's close as its close so far (on a Sunday that is the final close). So for an n-week simple average:

        sma_nw(D) = (close(D) + the n - 1 previous Sunday closes) / n

    and for an n-week exponential average, the weekly EMA up to the previous Sunday moved one step with close(D).
    A missing Sunday close (none so far) is taken as the last close before it.
    """
    filled = s.ffill()
    days = s.index
    sundays = filled[days.dayofweek == 6]
    sun_dates = sundays.index.values
    sun_vals = sundays.to_numpy()
    cum = np.concatenate([[0.0], np.cumsum(sun_vals)])
    # number of Sundays strictly before each day
    before = np.searchsorted(sun_dates, days.values, side="left")
    out: dict[str, pd.Series] = {}
    close = s.to_numpy()
    for n in sma_weeks:
        k = n - 1
        total = cum[before] - cum[np.maximum(before - k, 0)]
        vals = np.where(before >= k, (total + close) / n, np.nan)
        out[f"sma_{n}w"] = pd.Series(vals, index=days)
    for n in ema_weeks:
        weekly_ema = ema(sun_vals, n)          # the EMA at each completed week
        alpha = 2.0 / (n + 1)
        vals = np.full(len(days), np.nan)
        for i, b in enumerate(before):
            if b >= n:                          # an EMA exists at the previous Sunday: one more step with today
                vals[i] = alpha * close[i] + (1 - alpha) * weekly_ema[b - 1]
            elif b == n - 1:                    # today completes the n-th week: the seed, a simple average
                vals[i] = (sun_vals[:b].sum() + close[i]) / n
        out[f"ema_{n}w"] = pd.Series(vals, index=days)
    return out


def last_on_or_before(s: pd.Series, day: pd.Timestamp) -> float | None:
    """The last close on or before `day`, or None if the series starts after it."""
    sub = s.loc[:day].dropna()
    return float(sub.iloc[-1]) if len(sub) else None


def epoch_of(day: dt.date) -> int:
    """0 before the first halving; k from halving k (inclusive) to halving k + 1."""
    return sum(1 for h in HALVINGS.values() if h <= day)
