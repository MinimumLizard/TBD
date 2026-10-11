"""bond_rv_zscores: each bond's curve residual, and each nearby pair's residual spread, against its own history
(audit B6, B7, B11).

Version 1 is the old tool's signals/zscore.py and signals/run.py (MinimumLizard/Nelson-Siegel@1c33084), ported
line for line. The old tool labelled these outputs in trading language; the platform describes them neutrally (a
residual above or below the bond's own recent norm), because it gives information, not trade ideas.

    z = (today's residual - mean of the trailing window) / sd of that window

The window is the 60 observations BEFORE the day scored (at least 30), so no z-score has seen the value it scores.
Pairs: maturities within 2 years of each other, or both bonds ever auctioned. See METHOD.md.
"""
from __future__ import annotations

import datetime as dt
import itertools

import numpy as np
import pandas as pd

WINDOW_DAYS = 60
MIN_OBSERVATIONS = 30
MAX_TAU_GAP_YEARS = 2.0
MIN_SD_BP = 0.5               # a near-zero sd would manufacture enormous z-scores from noise
REVERSION_HORIZON_DAYS = 10
REVERSION_THRESHOLDS = (2.0, 3.0)
REVERSION_TOLERANCE_DAYS = 4
REVERSION_MIN_N = 30


def _rolling_z(values: pd.Series) -> pd.DataFrame:
    previous = values.shift(1)                       # excluding today: no look-ahead
    mean = previous.rolling(WINDOW_DAYS, min_periods=MIN_OBSERVATIONS).mean()
    sd = previous.rolling(WINDOW_DAYS, min_periods=MIN_OBSERVATIONS).std()
    count = previous.rolling(WINDOW_DAYS, min_periods=MIN_OBSERVATIONS).count()
    return pd.DataFrame({"mean_bp": mean, "sd_bp": sd, "zscore": (values - mean) / sd.where(sd > MIN_SD_BP),
                         "n_window": count})


def bond_zscores(residuals: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, group in residuals.groupby("isin"):
        group = group.sort_values("obs_date").reset_index(drop=True)
        stats = _rolling_z(group["residual_bp"])
        out.append(pd.concat([group[["obs_date", "isin", "residual_bp"]], stats], axis=1))
    if not out:
        return pd.DataFrame()
    return pd.concat(out).dropna(subset=["zscore"]).reset_index(drop=True)


def candidate_pairs(residuals: pd.DataFrame, auctioned=None) -> list[tuple[str, str]]:
    """Near neighbours (median maturities within 2 years), plus any two bonds that have ever been auctioned."""
    auctioned = set(auctioned or ())
    tau = residuals.groupby("isin")["tau_years"].median()
    return [(a, b) for a, b in itertools.combinations(sorted(tau.index), 2)
            if abs(tau[a] - tau[b]) <= MAX_TAU_GAP_YEARS or (a in auctioned and b in auctioned)]


def pair_zscores(residuals: pd.DataFrame, auctioned=None) -> pd.DataFrame:
    """z-score of the residual spread (a minus b) within each pair, against the pair's own window."""
    wide = residuals.pivot_table(index="obs_date", columns="isin", values="residual_bp")
    tau = residuals.groupby("isin")["tau_years"].median()
    out = []
    for first, second in candidate_pairs(residuals, auctioned):
        spread = (wide[first] - wide[second]).dropna()
        if len(spread) < MIN_OBSERVATIONS + 1:
            continue
        stats = _rolling_z(spread)
        frame = pd.DataFrame({"obs_date": spread.index, "isin_a": first, "isin_b": second,
                              "spread_bp": spread.values, "tau_a": tau[first], "tau_b": tau[second]}
                             ).join(stats.reset_index(drop=True))
        out.append(frame)
    if not out:
        return pd.DataFrame()
    return pd.concat(out).dropna(subset=["zscore"]).reset_index(drop=True)


def _forward_change(group) -> list:
    """Change in the pair spread 10 business days later (by date, searching up to 4 days on for a missing day)."""
    by_date = dict(zip(group.obs_date, group.spread_bp))
    offset = pd.tseries.offsets.BDay(REVERSION_HORIZON_DAYS)
    out = []
    for when, spread in zip(group.obs_date, group.spread_bp):
        target = when + offset
        found = None
        for slip in range(REVERSION_TOLERANCE_DAYS + 1):
            candidate = target + dt.timedelta(days=slip)
            if candidate in by_date:
                found = by_date[candidate]
                break
        out.append(float("nan") if found is None else found - spread)
    return out


def measure_reversion(pairs: pd.DataFrame) -> list[dict]:
    """Average movement of the pair spread back toward its norm, 10 business days after |z| >= 2 and >= 3.
    In-sample, one regime: it measures that the mechanism reverts, not what anything would earn."""
    if pairs.empty:
        return []
    frame = pairs.copy()
    frame["pair"] = frame.isin_a + "/" + frame.isin_b
    forward = []
    for _, group in frame.groupby("pair"):
        group = group.sort_values("obs_date").copy()
        group["forward"] = _forward_change(group)
        forward.append(group)
    measured = pd.concat(forward).dropna(subset=["forward"])
    if measured.empty:
        return []
    reversion = -np.sign(measured.zscore) * measured.forward
    stats = []
    for threshold in REVERSION_THRESHOLDS:
        extreme = abs(measured.zscore) >= threshold
        if extreme.sum() < REVERSION_MIN_N:
            continue
        stats.append({"stat_key": f"pair_reversion_{REVERSION_HORIZON_DAYS}d_z{threshold:g}",
                      "value": float(reversion[extreme].mean()), "n": int(extreme.sum())})
    return stats


def compute(inputs, as_of):
    day_filter = ("obs_date <= %s", (as_of,)) if as_of else ("", ())
    points = inputs.rows("models.bond_curve_point", "obs_date, isin, residual_bp, tau_years",
                         where=" and ".join(filter(None, ["source = 'quote'", day_filter[0]])),
                         params=day_filter[1], order_by="isin, obs_date")
    auction_filter = ("auction_date <= %s", (as_of,)) if as_of else ("", ())
    auctioned = ({r["isin"] for r in inputs.rows("bonds.auction_results_current", "distinct isin",
                                                  where=auction_filter[0], params=auction_filter[1])}
                 | {r["isin"] for r in inputs.rows("bonds.auction_announcements_current", "distinct isin",
                                                    where=auction_filter[0], params=auction_filter[1])})
    residuals = pd.DataFrame(points, columns=["obs_date", "isin", "residual_bp", "tau_years"])
    if residuals.empty:
        return {"models.bond_residual_zscore": [], "models.bond_pair_zscore": [], "models.model_stats": []}
    residuals["obs_date"] = pd.to_datetime(residuals["obs_date"])

    bonds = bond_zscores(residuals)
    bonds["deviation_bp"] = bonds["residual_bp"] - bonds["mean_bp"]
    pairs = pair_zscores(residuals, auctioned)
    if not pairs.empty:
        pairs["deviation_bp"] = pairs["spread_bp"] - pairs["mean_bp"]

    bond_rows = [{"obs_date": r.obs_date.date(), "isin": r.isin, "residual_bp": r.residual_bp,
                  "mean_bp": r.mean_bp, "sd_bp": r.sd_bp, "deviation_bp": r.deviation_bp, "zscore": r.zscore,
                  "n_window": int(r.n_window)} for r in bonds.itertuples()]
    pair_rows = [{"obs_date": r.obs_date.date(), "isin_a": r.isin_a, "isin_b": r.isin_b, "tau_a": r.tau_a,
                  "tau_b": r.tau_b, "spread_bp": r.spread_bp, "mean_bp": r.mean_bp, "sd_bp": r.sd_bp,
                  "deviation_bp": r.deviation_bp, "zscore": r.zscore, "n_window": int(r.n_window)}
                 for r in pairs.itertuples()] if not pairs.empty else []
    return {"models.bond_residual_zscore": bond_rows, "models.bond_pair_zscore": pair_rows,
            "models.model_stats": measure_reversion(pairs)}
