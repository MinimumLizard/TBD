"""bond_execution_gap: a median over the window, reported only with enough bond-days."""
from __future__ import annotations

import pytest

from data_platform.models._lib import bond_workspace as ws
from data_platform.models.bond_execution_gap import compute as eg


def _point(conn, day, isin, source, observed):
    conn.execute("""INSERT INTO curve_residuals (obs_date, isin, source, tau_years, observed_yield, fitted_yield,
                    residual_bp, weight) VALUES (?, ?, ?, 3.0, ?, 10.0, 0, NULL)""", (day, isin, source, observed))


def test_median_over_the_window():
    conn = ws.open_workspace()
    for k in range(9):
        day = f"2026-09-{10 + k:02d}"
        _point(conn, day, "A", "quote", 10.0)
        _point(conn, day, "A", "trade", 10.0 + (k + 1) / 100)      # gaps 1..9 bp
    assert eg.gap(conn, "2026-09-18") == {"gap_bp": pytest.approx(5.0), "n": 9, "window_days": 20}
    assert eg.gap(conn, "2026-09-17") == {"gap_bp": pytest.approx(4.5), "n": 8, "window_days": 20}
    assert eg.gap(conn, "2026-09-16") is None                        # 7 bond-days: too few
    assert eg.gap(conn, "2026-10-08") is None                        # all outside the 20 days
