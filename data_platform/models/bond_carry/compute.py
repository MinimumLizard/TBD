"""bond_carry: what each quoted bond earns per year from its yield over a funding rate, plus rolldown, per unit of
duration (audit B10).

Version 1 is the old tool's signals/carry.py (MinimumLizard/Nelson-Siegel@1c33084), ported line for line and
evaluated for every day that has a curve, with the entry yield shifted by that day's execution gap, as the old
dashboard did:

    carry     = entry yield - funding rate
    rolldown  = duration x (curve yield now - curve yield a quarter shorter) / 0.25, curve unchanged
    funding   = volume-weighted 12-month bill yield (240-380 days left) over the 5 days to the latest print in the
                last 30 days, plus 5 bp

Flat-yield pricing with semi-annual coupons dated back from maturity; no day count; tax ignored. See METHOD.md.
"""
from __future__ import annotations

import datetime as dt
import math

from .._lib import bond_workspace as ws, nelson_siegel as ns
from ...collectors.pdmo import isin as isin_module, series

FUNDING_SPREAD_BP = 5.0
BILL_MIN_DAYS = 240
BILL_MAX_DAYS = 380
BILL_WINDOW_DAYS = 5
BILL_LOOKBACK_DAYS = 30
HORIZON_YEARS = 0.25
COUPON_FREQUENCY = 2


def funding_rate(conn, obs_date: str, spread_bp: float = FUNDING_SPREAD_BP) -> dict | None:
    today = dt.date.fromisoformat(obs_date)
    earliest = (today - dt.timedelta(days=BILL_LOOKBACK_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT obs_date, isin, wavg_yield, volume_lkr FROM trade_summary
            WHERE security_type = 'Tbill' AND obs_date <= ? AND obs_date > ?
              AND wavg_yield IS NOT NULL AND volume_lkr > 0
            ORDER BY obs_date DESC""", (obs_date, earliest)).fetchall()
    by_day: dict[str, list] = {}
    for row in rows:
        decoded = isin_module.decode_bill(row["isin"])
        if not decoded:
            continue
        remaining = (decoded[1] - dt.date.fromisoformat(row["obs_date"])).days
        if BILL_MIN_DAYS <= remaining <= BILL_MAX_DAYS:
            by_day.setdefault(row["obs_date"], []).append(row)
    if not by_day:
        return None
    latest = max(by_day)
    cutoff = (dt.date.fromisoformat(latest) - dt.timedelta(days=BILL_WINDOW_DAYS)).isoformat()
    sample = [row for day, rows in by_day.items() if day > cutoff for row in rows]
    weight = sum(row["volume_lkr"] for row in sample)
    bill = sum(row["wavg_yield"] * row["volume_lkr"] for row in sample) / weight
    return {"bill_pct": bill, "rate_pct": bill + spread_bp / 100.0, "spread_bp": spread_bp, "as_of": latest,
            "stale_days": (today - dt.date.fromisoformat(latest)).days, "n_bills": len(sample),
            "window_days": BILL_WINDOW_DAYS}


def price_and_duration(yield_pct: float, coupon_pct: float, tau_years: float) -> tuple[float, float]:
    """(price per 100, modified duration) at a flat yield; cash flows dated backwards from maturity."""
    periods = max(int(math.ceil(tau_years * COUPON_FREQUENCY - 1e-9)), 1)
    times = [t for t in (tau_years - k / COUPON_FREQUENCY for k in range(periods - 1, -1, -1)) if t > 1e-9]
    rate = yield_pct / 100.0 / COUPON_FREQUENCY
    price = weighted = 0.0
    for index, time_years in enumerate(times):
        flow = coupon_pct / COUPON_FREQUENCY + (100.0 if index == len(times) - 1 else 0.0)
        present = flow / (1.0 + rate) ** (time_years * COUPON_FREQUENCY)
        price += present
        weighted += present * time_years
    return price, weighted / price / (1.0 + rate)


def profile(conn, obs_date: str, entry_gap_bp: float = 0.0, spread_bp: float = FUNDING_SPREAD_BP) -> dict:
    fit = conn.execute("SELECT * FROM curve_fits WHERE obs_date = ?", (obs_date,)).fetchone()
    funding = funding_rate(conn, obs_date, spread_bp)
    if not fit or not funding:
        return {}
    betas = (fit["beta0"], fit["beta1"], fit["beta2"])
    lam = fit["lambda_years"]
    out = {}
    for row in conn.execute(
            """SELECT r.isin, r.tau_years, r.observed_yield, b.coupon_pct, b.series_label
                 FROM curve_residuals r JOIN bonds b USING(isin)
                WHERE r.obs_date = ? AND r.source = 'quote' AND b.coupon_pct IS NOT NULL""", (obs_date,)):
        if len(series.coupon_steps(row["series_label"])) > 1:
            continue     # a level-coupon formula cannot price a step-coupon bond (none reach the version 1 curve)
        tau = row["tau_years"]
        entry = row["observed_yield"] + entry_gap_bp / 100.0
        price, duration = price_and_duration(entry, row["coupon_pct"], tau)
        aged = max(tau - HORIZON_YEARS, 0.02)
        drop = float(ns.predict([tau], betas, lam)[0]) - float(ns.predict([aged], betas, lam)[0])
        roll_bp = duration * drop * 100.0 / HORIZON_YEARS
        carry_bp = (entry - funding["rate_pct"]) * 100.0
        total = carry_bp + roll_bp
        out[row["isin"]] = {"entry_yield": entry, "price": price, "duration": duration, "carry_bp": carry_bp,
                            "roll_bp": roll_bp, "total_bp": total,
                            "per_duration_bp": total / duration if duration > 0 else 0.0, "funding": funding}
    return out


def compute(inputs, as_of):
    day = ("obs_date <= %s", (as_of,)) if as_of else ("", ())
    spread_bp = float(inputs.params.get("funding_spread_bp", FUNDING_SPREAD_BP))
    fits = inputs.rows("models.bond_curve_fit", where=day[0], params=day[1], order_by="obs_date")
    conn = ws.open_workspace()
    ws.load_reference(conn, inputs.rows("models.bond_reference"))
    ws.load_curve(conn, fits, inputs.rows("models.bond_curve_point", where=day[0], params=day[1]))
    ws.load_trades(conn, inputs.rows("bonds.trades_current", where=day[0], params=day[1]))
    gaps = {r["obs_date"].isoformat(): r["gap_bp"]
            for r in inputs.rows("models.bond_execution_gap", where=day[0], params=day[1])}
    # Version 1.1.0: a quote wider than this is administered rather than dealt (the old tool's own threshold for
    # admitting a quote), so its yield cannot be read as what the bond earns. Version 1 never saw such quotes.
    max_spread = inputs.params.get("max_quote_spread_bp")
    too_wide = set()
    if max_spread is not None:
        for q in inputs.rows("models.bond_quotes", "obs_date, isin, bid_yield, offer_yield", where=day[0], params=day[1]):
            if q["bid_yield"] is None or q["offer_yield"] is None or (q["bid_yield"] - q["offer_yield"]) * 100 > max_spread:
                too_wide.add((q["obs_date"].isoformat(), q["isin"]))
    funding_rows, carry_rows = [], []
    for fit in fits:
        obs_date = fit["obs_date"].isoformat()
        funding = funding_rate(conn, obs_date, spread_bp)
        if funding:
            funding_rows.append({"obs_date": obs_date, "bill_pct": funding["bill_pct"],
                                 "rate_pct": funding["rate_pct"], "spread_bp": funding["spread_bp"],
                                 "bill_as_of": funding["as_of"], "stale_days": funding["stale_days"],
                                 "n_bills": funding["n_bills"], "window_days": funding["window_days"]})
        entry_gap = gaps.get(obs_date, 0.0)
        for isin, facts in sorted(profile(conn, obs_date, entry_gap, spread_bp).items()):
            if (obs_date, isin) in too_wide:
                continue
            carry_rows.append({"obs_date": obs_date, "isin": isin, "entry_gap_bp": entry_gap,
                               **{k: v for k, v in facts.items() if k != "funding"}})
    return {"models.bond_funding": funding_rows, "models.bond_carry": carry_rows}
