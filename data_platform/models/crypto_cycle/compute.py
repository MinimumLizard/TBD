"""crypto_cycle: long moving averages, the Pi cycle lines and their crossings, halvings, cycle peaks and lows, and
monthly returns, for the pairs in the manifest (BTC and ETH in US dollars). Every value for day D uses closes up to
D only; a cycle peak or low that can still move (its epoch has not ended) is marked provisional. See METHOD.md."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .._lib.crypto import HALVINGS, closes, ema, epoch_of, sma, weekly_sma_and_ema


def _f(v) -> float | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def daily_lines(s: pd.Series, p: dict) -> pd.DataFrame:
    filled = s.ffill()
    out = pd.DataFrame({"close": s})
    out["sma_50"] = sma(s, 50)
    out["sma_200"] = sma(s, 200)
    out["mayer"] = s / out["sma_200"]
    weekly = weekly_sma_and_ema(s, sma_weeks=[200, 20], ema_weeks=[21])
    out["sma_200w"] = weekly["sma_200w"]
    out["sma_200w_chg_4w"] = out["sma_200w"] / out["sma_200w"].shift(28) - 1
    out["sma_20w"] = weekly["sma_20w"]
    out["ema_21w"] = weekly["ema_21w"]
    out["dist_20w"] = s / out["sma_20w"] - 1
    out["pi_sma_111"] = sma(s, p["pi_top_short"])
    out["pi_sma_350x2"] = sma(s, p["pi_top_long"]) * p["pi_top_multiple"]
    out["pi_ema_150"] = pd.Series(ema(filled.to_numpy(), p["pi_bottom_ema"]), index=s.index).where(s.notna())
    out["pi_sma_471x0745"] = sma(s, p["pi_bottom_long"]) * p["pi_bottom_multiple"]
    # month to date: against the previous month's last close
    month_start = s.index.to_period("M").to_timestamp()
    prev_month_end = month_start - pd.Timedelta(days=1)
    out["ret_mtd"] = s / filled.reindex(prev_month_end).to_numpy() - 1
    return out


def crossings(lines: pd.DataFrame) -> list[tuple[pd.Timestamp, str]]:
    """Days a line crossed another: on day D the relation is true and on D - 1 it was not (both days defined)."""
    events = []
    top = lines["pi_sma_111"] > lines["pi_sma_350x2"]
    top_ok = lines["pi_sma_111"].notna() & lines["pi_sma_350x2"].notna()
    bottom = lines["pi_ema_150"] < lines["pi_sma_471x0745"]
    bottom_ok = lines["pi_ema_150"].notna() & lines["pi_sma_471x0745"].notna()
    for kind, rel, ok in (("pi_top_cross", top, top_ok), ("pi_bottom_cross", bottom, bottom_ok)):
        hit = rel & ~rel.shift(1, fill_value=False) & ok & ok.shift(1, fill_value=False)
        events += [(d, kind) for d in lines.index[hit.to_numpy()]]
    return sorted(events)


def anchors(pair: str, s: pd.Series) -> list[dict]:
    """Halvings, cycle peaks and cycle lows as known on each day, with the change since each.

    Epoch k runs from halving k up to the day before halving k + 1 (epoch 0: from the first close to the day before
    the first halving). An epoch's cycle peak and cycle low are the two ends of its largest fall so far: the pair of
    days (peak before low) with the lowest ratio low close / peak close. (The highest close of an epoch is not used:
    in the epoch of 2020-2024 it fell in March 2024, a month before the next halving, not at the 2021 top.) Before
    any fall, the peak is the highest close so far and there is no low. Epoch 0 has no peak (Bitstamp's history
    starts after the 2011 top), so its low is its lowest close so far. In cycle order the anchors run low 0,
    halving 1, peak 1, low 1, halving 2, ...; each carries its change from the one before it."""
    data = s.dropna()
    days = [d.date() for d in data.index]
    values = data.to_numpy()
    halving_close = {k: float(data.loc[pd.Timestamp(h)]) for k, h in HALVINGS.items() if pd.Timestamp(h) in data.index}

    # per epoch, day by day: the highest close so far, and the largest fall so far (its peak and its low)
    state: dict[int, dict] = {}
    rows = []
    for day, close in zip(days, values):
        e = epoch_of(day)
        st = state.setdefault(e, {"high": None, "peak": None, "low": None})
        if e == 0:
            if st["low"] is None or close < st["low"][1]:
                st["low"] = (day, close)
        else:
            if st["high"] is None or close > st["high"][1]:
                st["high"] = (day, close)
            fall = close / st["high"][1]
            if fall < 1 and (st["low"] is None or fall < st["low"][1] / st["peak"][1]):
                st["peak"], st["low"] = st["high"], (day, close)
            elif st["low"] is None:
                st["peak"] = st["high"]          # no fall yet: the highest close so far

        sequence = []        # (kind, epoch, anchor_day, anchor_close, provisional), in cycle order
        for k in sorted(state):
            if k >= 1 and k in halving_close:
                sequence.append(("halving", k, HALVINGS[k], halving_close[k], False))
            open_epoch = k == e
            if state[k]["peak"] is not None:
                sequence.append(("cycle_peak", k, *state[k]["peak"], open_epoch))
            if state[k]["low"] is not None:
                sequence.append(("cycle_low", k, *state[k]["low"], open_epoch))
        prior = None
        for kind, k, a_day, a_close, provisional in sequence:
            rows.append({"pair": pair, "day": day, "kind": kind, "epoch": k, "anchor_day": a_day,
                         "anchor_close": float(a_close), "roi": float(close / a_close - 1),
                         "days_since": (day - a_day).days,
                         "change_from_prior": float(a_close / prior[1] - 1) if prior else None,
                         "days_from_prior": (a_day - prior[0]).days if prior else None,
                         "provisional": provisional})
            prior = (a_day, a_close)
    return rows


def monthly(pair: str, s: pd.Series) -> list[dict]:
    """Completed calendar months only (the data reaches the month's last day), so a row never changes later."""
    data = s.dropna()
    if data.empty:
        return []
    last_day = data.index[-1]
    rows, prev = [], None
    for period, group in data.groupby(data.index.to_period("M")):
        month_end = period.to_timestamp(how="end").normalize()
        if month_end > last_day:
            break
        close = float(group.iloc[-1])
        rows.append({"pair": pair, "month": period.to_timestamp().date(), "day": month_end.date(), "close": close,
                     "ret_month": close / prev - 1 if prev else None})
        prev = close
    return rows


def compute(inputs, as_of):
    p = inputs.params
    daily, events, anchor_rows, months = [], [], [], []
    for pair, s in sorted(closes(inputs, as_of, p["pairs"]).items()):
        lines = daily_lines(s, p)
        for day, r in lines.iterrows():
            if np.isnan(r["close"]):
                continue
            d = day.date()
            row = {"pair": pair, "day": d, **{c: _f(r[c]) for c in lines.columns}}
            past = [(k, h) for k, h in HALVINGS.items() if h <= d]
            if past:
                k, h = past[-1]
                row["last_halving"] = h
                row["days_since_halving"] = (d - h).days
                base = s.get(pd.Timestamp(h))
                row["roi_since_halving"] = _f(r["close"] / base - 1) if base is not None and not np.isnan(base) else None
            daily.append(row)
        for day, kind in crossings(lines):
            events.append({"pair": pair, "day": day.date(), "kind": kind, "close": float(s.loc[day])})
        anchor_rows += anchors(pair, s)
        months += monthly(pair, s)
    return {"models.crypto_cycle_daily": daily, "models.crypto_cycle_event": events,
            "models.crypto_cycle_anchor": anchor_rows, "models.crypto_cycle_monthly": months}
