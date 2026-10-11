"""bond_ns_curve: one Nelson-Siegel yield curve per day, and every bond's distance from it (audit B3-B5).

Version 1 is the old tool's curves/fit.py (MinimumLizard/Nelson-Siegel@1c33084), ported line for line and run
against the same tables: dealer quote mids are fitted by weighted least squares at a fixed lambda, each quote
weighted by 1/spread^2; executed trades are held out of the fit and compared with it afterwards. See METHOD.md.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from .._lib import bond_workspace as ws, nelson_siegel as ns
from ...collectors.pdmo import series

MIN_TAU_YEARS = 0.08     # under a month: price is noise, not curve
MIN_BONDS = 6            # fewer than this and the shape is not identified
MIN_SPREAD_BP = 1.0      # floor, so a zero spread cannot dominate the fit
MAX_SPREAD_BP = 300.0    # beyond this the quote carries no information


def _years(obs_date: dt.date, maturity: dt.date) -> float:
    return (maturity - obs_date).days / 365.25


def load_day(conn, obs_date: str):
    """Quotes to fit (step-coupon bonds and the last month of a bond's life left out), and the day's trades."""
    quotes = []
    day = dt.date.fromisoformat(obs_date)
    for row in conn.execute(
            """SELECT o.isin, o.mid_yield, o.bid_yield, o.offer_yield, b.maturity_date, b.series_label
                 FROM observations o JOIN bonds b USING(isin)
                WHERE o.obs_date = ? AND o.source = 'pdmo_daily'
                  AND o.mid_yield IS NOT NULL AND b.maturity_date IS NOT NULL""", (obs_date,)):
        if len(series.coupon_steps(row["series_label"])) > 1:
            continue
        tau = _years(day, dt.date.fromisoformat(row["maturity_date"]))
        if tau < MIN_TAU_YEARS:
            continue
        spread = None
        if row["bid_yield"] is not None and row["offer_yield"] is not None:
            spread = abs(row["bid_yield"] - row["offer_yield"]) * 100.0
        quotes.append({"isin": row["isin"], "tau": tau, "yield": row["mid_yield"], "spread_bp": spread})
    return quotes, load_trades(conn, obs_date)


def load_trades(conn, obs_date: str) -> list:
    day = dt.date.fromisoformat(obs_date)
    trades = []
    for row in conn.execute(
            """SELECT t.isin, t.wavg_yield, b.maturity_date, b.series_label
                 FROM trade_summary t JOIN bonds b USING(isin)
                WHERE t.obs_date = ? AND t.security_type = 'TBond'
                  AND t.wavg_yield IS NOT NULL AND b.maturity_date IS NOT NULL""", (obs_date,)):
        if len(series.coupon_steps(row["series_label"])) > 1:
            continue
        tau = _years(day, dt.date.fromisoformat(row["maturity_date"]))
        if tau < MIN_TAU_YEARS:
            continue
        trades.append({"isin": row["isin"], "tau": tau, "yield": row["wavg_yield"]})
    return trades


def weights_from_spreads(quotes, max_spread_bp: float = MAX_SPREAD_BP) -> np.ndarray:
    """1/spread^2 (spread floored at 1 bp and capped), the median spread standing in for a missing one;
    normalised to average 1, so a stored weight reads as "counted N times as much as an average quote"."""
    known = [q["spread_bp"] for q in quotes if q["spread_bp"] is not None]
    fallback = float(np.median(known)) if known else 20.0
    spreads = np.array([min(max(q["spread_bp"] if q["spread_bp"] is not None else fallback, MIN_SPREAD_BP),
                            max_spread_bp) for q in quotes])
    weights = 1.0 / spreads**2
    return weights / weights.mean()


def fit_day(conn, obs_date: str, lam: float, max_spread_bp: float = MAX_SPREAD_BP):
    """(summary, points) for one day, or None when fewer than MIN_BONDS quotes are usable."""
    quotes, trades = load_day(conn, obs_date)
    if len(quotes) < MIN_BONDS:
        return None
    tau = np.array([q["tau"] for q in quotes])
    observed = np.array([q["yield"] for q in quotes])
    weights = weights_from_spreads(quotes, max_spread_bp)
    betas, fitted, _ = ns.fit_fixed(tau, observed, lam, weights)
    summary = {
        "obs_date": obs_date, "beta0": float(betas[0]), "beta1": float(betas[1]), "beta2": float(betas[2]),
        "lambda_years": lam, "n_quotes": len(quotes), "rmse_bp": ns.weighted_rmse_bp(observed, fitted, weights),
        "n_trades": 0, "trade_rmse_bp": None, "trade_bias_bp": None,
    }
    points = [_point(obs_date, q, "quote", o, f, w) for q, o, f, w in zip(quotes, observed, fitted, weights)]
    if trades:
        trade_tau = np.array([t["tau"] for t in trades])
        trade_obs = np.array([t["yield"] for t in trades])
        trade_fit = ns.predict(trade_tau, betas, lam)
        errors_bp = (trade_obs - trade_fit) * 100.0
        summary["n_trades"] = len(trades)
        summary["trade_rmse_bp"] = float(np.sqrt(np.mean(errors_bp**2)))
        # A median, not a mean: a day holds 7 to 14 trades, and one booking at an agreed rather than a market
        # level moves a mean of that many a long way (old fit.py, the 2026-09-24 example).
        summary["trade_bias_bp"] = float(np.median(errors_bp))
        points += [_point(obs_date, t, "trade", o, f, None) for t, o, f in zip(trades, trade_obs, trade_fit)]
    return summary, points


def _point(obs_date, point, source, observed, fitted, weight) -> dict:
    return {"obs_date": obs_date, "isin": point["isin"], "source": source, "tau_years": point["tau"],
            "observed_yield": float(observed), "fitted_yield": float(fitted),
            "residual_bp": float((observed - fitted) * 100.0), "weight": None if weight is None else float(weight)}


def build_workspace(inputs, as_of):
    conn = ws.open_workspace()
    ws.load_reference(conn, inputs.rows("models.bond_reference"))
    day_filter = ("obs_date <= %s", (as_of,)) if as_of else ("", ())
    ws.load_quotes(conn, inputs.rows("models.bond_quotes", where=day_filter[0], params=day_filter[1]))
    ws.load_trades(conn, inputs.rows("bonds.trades_current", where=day_filter[0], params=day_filter[1]))
    return conn


def compute(inputs, as_of):
    conn = build_workspace(inputs, as_of)
    lam = float(inputs.params["lambda_years"])
    max_spread = float(inputs.params.get("max_spread_bp", MAX_SPREAD_BP))
    fits, points = [], []
    for (obs_date,) in conn.execute("""SELECT DISTINCT obs_date FROM observations
                                       WHERE source='pdmo_daily' AND mid_yield IS NOT NULL ORDER BY obs_date"""):
        result = fit_day(conn, obs_date, lam, max_spread)
        if result:
            fits.append(result[0])
            points += result[1]
    return {"models.bond_curve_fit": fits, "models.bond_curve_point": points}
