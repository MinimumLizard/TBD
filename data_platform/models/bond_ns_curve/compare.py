"""Measure how two versions of the curve differ, for METHOD.md (numbers in docs come from a command):

    python -m data_platform.models.bond_ns_curve.compare 1.0.0 2.0.0

Prints, over the days both versions fitted: bonds per day; the weighted fit error on each version's own quotes;
the error of the NEW curve on the OLD version's quotes, with the old weights (the like-for-like comparison); how far
the curve moved at those bonds; and the out-of-sample check against executed trades.
"""
from __future__ import annotations

import statistics
import sys

from ...core import db, settings as settings_mod


def compare(conn, old: str, new: str) -> dict:
    fits = {(r["method_version"], r["obs_date"]): r for r in conn.execute(
        "select * from models.bond_curve_fit where method_version in (%s, %s)", (old, new))}
    days = sorted({d for v, d in fits if v == old} & {d for v, d in fits if v == new})
    points = {}
    for r in conn.execute("""select method_version, obs_date, isin, observed_yield, fitted_yield, weight
                             from models.bond_curve_point where source = 'quote' and method_version in (%s, %s)""",
                          (old, new)):
        points[(r["method_version"], r["obs_date"], r["isin"])] = r
    like_for_like, moved = [], []
    for d in days:
        sq = wsum = 0.0
        for (v, day, isin), p in points.items():
            if v != old or day != d:
                continue
            q = points.get((new, d, isin))
            if q is None:
                continue
            sq += p["weight"] * ((p["observed_yield"] - q["fitted_yield"]) * 100) ** 2
            wsum += p["weight"]
            moved.append(abs(q["fitted_yield"] - p["fitted_yield"]) * 100)
        if wsum:
            like_for_like.append((sq / wsum) ** 0.5)

    def med(version, column):
        values = [fits[(version, d)][column] for d in days if fits[(version, d)][column] is not None]
        return statistics.median(values) if values else None

    return {"days": len(days),
            "bonds_per_day": {old: statistics.mean(fits[(old, d)]["n_quotes"] for d in days),
                              new: statistics.mean(fits[(new, d)]["n_quotes"] for d in days)},
            "median_rmse_bp_own_quotes": {old: med(old, "rmse_bp"), new: med(new, "rmse_bp")},
            f"median_rmse_bp_of_{new}_on_{old}_quotes": statistics.median(like_for_like) if like_for_like else None,
            "curve_move_bp_at_those_bonds": {"median": statistics.median(moved) if moved else None,
                                             "p95": sorted(moved)[int(0.95 * (len(moved) - 1))] if moved else None},
            "median_trade_rmse_bp": {old: med(old, "trade_rmse_bp"), new: med(new, "trade_rmse_bp")},
            "median_trade_bias_bp": {old: med(old, "trade_bias_bp"), new: med(new, "trade_bias_bp")}}


def main(argv: list[str] | None = None) -> int:
    old, new = (argv or sys.argv[1:])[:2]
    result = compare(db.connect(settings_mod.load().database_url), old, new)
    for key, value in result.items():
        if isinstance(value, dict):
            value = ", ".join(f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, float):
            value = f"{value:.2f}"
        print(f"{key:45} {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
