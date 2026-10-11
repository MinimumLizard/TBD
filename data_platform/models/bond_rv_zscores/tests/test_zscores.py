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


def test_point_in_time_pairs_never_change_when_a_later_day_arrives():
    days = 45
    r = _residuals({"A": 2.0, "B": 3.0, "C": 3.9}, days=days)
    # maturities shorten every day, as real ones do: the whole-history median would move with each new day
    r["tau_years"] = r["tau_years"] - (r["obs_date"] - r["obs_date"].min()).dt.days / 365.25
    first_auction = {}
    upto = r[r.obs_date < r.obs_date.max()]
    before = z.pair_zscores_point_in_time(upto, first_auction).set_index(["obs_date", "isin_a", "isin_b"])
    after = z.pair_zscores_point_in_time(r, first_auction).set_index(["obs_date", "isin_a", "isin_b"])
    shared = before.index.intersection(after.index)
    assert len(shared) == len(before) > 0
    pd.testing.assert_frame_equal(before.loc[shared].sort_index(), after.loc[shared].sort_index())
    one = after.reset_index().iloc[-1]
    assert one.tau_a != r[r["isin"] == one.isin_a].tau_years.median()       # the day's own maturity, not a median


def test_point_in_time_pairs_use_auctions_known_on_the_day():
    import datetime as dt

    r = _residuals({"A": 1.0, "D": 9.0}, days=45)         # 8 years apart: a pair only once both are auctioned
    switch_on = r.obs_date.sort_values().unique()[40]
    first_auction = {"A": dt.date(2025, 1, 1), "D": pd.Timestamp(switch_on).date()}
    pairs = z.pair_zscores_point_in_time(r, first_auction)
    assert pairs.obs_date.min() == switch_on
