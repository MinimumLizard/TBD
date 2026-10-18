"""crypto_market: per pair per day, the close, its returns, its distance from the highest close to date, and its
realised volatility. Every value for day D uses closes up to D only. See METHOD.md."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .._lib.crypto import closes

RETURN_DAYS = {"1d": 1, "7d": 7, "30d": 30, "1y": 365}
VOL_DAYS = {"30d": 30, "90d": 90}


def pair_rows(pair: str, s: pd.Series, year_days: int) -> list[dict]:
    filled = s.ffill()              # "the last close on or before" a day; only matters if a day is ever missing
    log_ret = np.log(s / s.shift(1))
    vols = {k: log_ret.rolling(n, min_periods=n).std(ddof=1) * np.sqrt(year_days) for k, n in VOL_DAYS.items()}
    rets = {k: s / filled.shift(n) - 1 for k, n in RETURN_DAYS.items()}
    rows = []
    ath, ath_day = -np.inf, None
    for i, (day, close) in enumerate(s.items()):
        if np.isnan(close):
            continue
        if close > ath:
            ath, ath_day = close, day
        row = {"pair": pair, "day": day.date(), "close": float(close), "ath_close": float(ath),
               "ath_day": ath_day.date(), "drawdown": float(close / ath - 1),
               "days_since_ath": int((day - ath_day).days)}
        for k in RETURN_DAYS:
            v = rets[k].iloc[i]
            row[f"ret_{k}"] = None if np.isnan(v) else float(v)
        for k in VOL_DAYS:
            v = vols[k].iloc[i]
            row[f"vol_{k}"] = None if np.isnan(v) else float(v)
        rows.append(row)
    return rows


def compute(inputs, as_of):
    year_days = int(inputs.params.get("annualisation_days", 365))
    rows = []
    for pair, s in sorted(closes(inputs, as_of).items()):
        rows += pair_rows(pair, s, year_days)
    return {"models.crypto_market_daily": rows}
