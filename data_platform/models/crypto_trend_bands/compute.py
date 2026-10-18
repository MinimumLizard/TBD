"""crypto_trend_bands: two long-run trend lines for bitcoin, each re-fitted every day on the closes up to that day,
with bands at one and two residual standard deviations, and where the close sits between the outer bands.

    log_regression   ln(close) = a + b ln(t), weighted least squares, weight 1/t (every stretch of log-time counts
                     the same, so the early years are not outweighed by the many recent days)
    power_law        log10(close) = A + B log10(t), ordinary least squares (every day counts the same)

t is the number of days since the genesis block (2009-01-03). The fits use running sums, so day D's fit is exactly the
fit of the closes from the first day to D, and a row never changes when later days arrive. See METHOD.md.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .._lib.crypto import GENESIS, closes

FITS = {
    # name: (log function, weight function of t)
    "log_regression": (np.log, lambda t: 1.0 / t),
    "power_law": (np.log10, lambda t: np.ones_like(t)),
}


def running_fit(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict[str, np.ndarray]:
    """Weighted least squares of y on x over the first i + 1 points, for every i, from running sums."""
    W = np.cumsum(w)
    Sx, Sy = np.cumsum(w * x), np.cumsum(w * y)
    Sxx, Sxy, Syy = np.cumsum(w * x * x), np.cumsum(w * x * y), np.cumsum(w * y * y)
    n = np.arange(1, len(x) + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cxx = Sxx - Sx * Sx / W          # centred sums
        cxy = Sxy - Sx * Sy / W
        cyy = Syy - Sy * Sy / W
        slope = cxy / cxx
        intercept = (Sy - slope * Sx) / W
        ssr = np.maximum(cyy - slope * cxy, 0.0)
        # weighted residual variance, scaled so equal weights give the usual ssr / (n - 2)
        sd = np.sqrt(ssr / W * n / (n - 2))
    return {"intercept": intercept, "slope": slope, "sd": sd, "n": n}


def fit_rows(pair: str, s: pd.Series, fit: str, min_obs: int, k_inner: float, k_outer: float) -> list[dict]:
    log, weight = FITS[fit]
    data = s.dropna()
    t = np.array([(d.date() - GENESIS).days for d in data.index], dtype=float)
    close = data.to_numpy()
    x, y = log(t), log(close)
    f = running_fit(x, y, weight(t))
    back = (lambda v: np.exp(v)) if fit == "log_regression" else (lambda v: 10.0 ** v)
    rows = []
    for i, day in enumerate(data.index):
        if f["n"][i] < min_obs:
            continue
        a, b, sd = float(f["intercept"][i]), float(f["slope"][i]), float(f["sd"][i])
        if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(sd)) or sd <= 0:
            continue
        mid = a + b * x[i]
        rows.append({
            "pair": pair, "day": day.date(), "fit": fit, "intercept": a, "slope": b, "n_obs": int(f["n"][i]),
            "resid_sd": sd, "close": float(close[i]), "fitted": float(back(mid)),
            "lower_1": float(back(mid - k_inner * sd)), "upper_1": float(back(mid + k_inner * sd)),
            "lower_2": float(back(mid - k_outer * sd)), "upper_2": float(back(mid + k_outer * sd)),
            "position": float((y[i] - (mid - k_outer * sd)) / (2 * k_outer * sd)),
        })
    return rows


def compute(inputs, as_of):
    p = inputs.params
    rows = []
    for pair, s in sorted(closes(inputs, as_of, p["pairs"]).items()):
        for fit in FITS:
            rows += fit_rows(pair, s, fit, int(p["min_observations"]), float(p["inner_band_sd"]),
                             float(p["outer_band_sd"]))
    return {"models.crypto_trend_band": rows}
