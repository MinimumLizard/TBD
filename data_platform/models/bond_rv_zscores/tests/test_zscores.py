"""bond_rv_zscores: the window never sees the day it scores; pair selection; reversion figures."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data_platform.models.bond_rv_zscores import compute as z


def test_the_window_excludes_the_day_scored():
    values = pd.Series([1.0, -1.0] * 20 + [50.0])
    stats = z._rolling_z(values)
    last = stats.iloc[-1]
    assert last.mean_bp == pytest.approx(0.0)                    # 50 is not in its own window
    assert last.zscore == pytest.approx(50.0 / values.iloc[:-1].std())
    assert stats.zscore.iloc[: z.MIN_OBSERVATIONS].isna().all()  # too little history: no score


def test_a_flat_history_gives_no_score():
    stats = z._rolling_z(pd.Series([3.0] * 40 + [4.0]))
    assert np.isnan(stats.zscore.iloc[-1])                       # sd 0 < 0.5 bp


def _residuals(taus: dict, days=40):
    rows = []
    for d in pd.bdate_range("2026-01-01", periods=days):
        for i, (isin, tau) in enumerate(taus.items()):
            rows.append({"obs_date": d, "isin": isin, "residual_bp": float(np.sin(d.day + i)), "tau_years": tau})
    return pd.DataFrame(rows)


def test_pairs_are_neighbours_or_both_auctioned():
    r = _residuals({"A": 2.0, "B": 3.5, "C": 9.0, "D": 10.5})
    assert z.candidate_pairs(r) == [("A", "B"), ("C", "D")]
    assert ("A", "D") in z.candidate_pairs(r, auctioned={"A", "D"})


def test_pair_scores_and_reversion_need_enough_history():
    r = _residuals({"A": 2.0, "B": 3.0}, days=40)
    pairs = z.pair_zscores(r)
    assert set(pairs.columns) >= {"spread_bp", "zscore", "n_window"} and len(pairs) == 40 - z.MIN_OBSERVATIONS
    assert z.measure_reversion(pairs) == []                      # under 30 extreme pair-days: nothing reported
