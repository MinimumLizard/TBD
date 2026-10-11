"""bond_execution_gap: where executed trades printed relative to the dealers' quoted mid (audit B9).

Version 1 is the old tool's signals/execution.py (MinimumLizard/Nelson-Siegel@1c33084), ported line for line and
evaluated for every day that has a curve: the median, over the trailing 20 calendar days, of (traded yield - quoted
mid yield) in basis points, for every bond-day that both quoted and traded. Reported only with at least 8 such
bond-days. Positive: trades printed at higher yields (lower prices) than the quote screen. See METHOD.md.
"""
from __future__ import annotations

from .._lib import bond_workspace as ws

WINDOW_DAYS = 20
MIN_OBSERVATIONS = 8


def _median(values) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _pairs(conn, obs_date: str, window: int) -> list:
    return conn.execute(
        """SELECT q.tau_years AS tau, (t.observed_yield - q.observed_yield) * 100.0 AS gap_bp
             FROM curve_residuals q
             JOIN curve_residuals t ON t.obs_date = q.obs_date AND t.isin = q.isin AND t.source = 'trade'
            WHERE q.source = 'quote' AND q.obs_date > date(?, ?) AND q.obs_date <= ?""",
        (obs_date, f"-{window} days", obs_date)).fetchall()


def gap(conn, obs_date: str) -> dict | None:
    rows = _pairs(conn, obs_date, WINDOW_DAYS)
    if len(rows) < MIN_OBSERVATIONS:
        return None
    values = [row["gap_bp"] for row in rows]
    return {"gap_bp": _median(values), "n": len(values), "window_days": WINDOW_DAYS}


def compute(inputs, as_of):
    day = ("obs_date <= %s", (as_of,)) if as_of else ("", ())
    fits = inputs.rows("models.bond_curve_fit", where=day[0], params=day[1], order_by="obs_date")
    points = inputs.rows("models.bond_curve_point", where=day[0], params=day[1])
    conn = ws.open_workspace()
    ws.load_curve(conn, fits, points)
    rows = []
    for fit in fits:
        measured = gap(conn, fit["obs_date"].isoformat())
        if measured:
            rows.append({"obs_date": fit["obs_date"], **measured})
    return {"models.bond_execution_gap": rows}
