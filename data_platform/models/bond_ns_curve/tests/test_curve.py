"""bond_ns_curve: the maths on exact synthetic data, and the fit on a real day."""
from __future__ import annotations

import numpy as np
import pytest

from data_platform.models._lib import nelson_siegel as ns
from data_platform.models.bond_ns_curve import compute as curve


def test_fit_recovers_a_known_curve_exactly():
    tau = np.array([0.5, 1, 2, 3, 5, 7, 10, 15])
    truth = np.array([12.0, -3.0, 1.5])
    y = ns.predict(tau, truth, 2.82)
    betas, fitted, rss = ns.fit_fixed(tau, y, 2.82, np.linspace(1, 3, len(tau)))
    assert betas == pytest.approx(truth, abs=1e-10)
    assert rss == pytest.approx(0, abs=1e-18)


def test_fewer_than_four_points_cannot_be_fitted():
    with pytest.raises(ValueError, match="at least 4"):
        ns.fit_fixed([1, 2, 3], [9, 10, 11], 2.82)


def test_short_end_limit_is_beta0_plus_beta1():
    assert ns.predict([0.0], [12.0, -3.0, 1.5], 2.82)[0] == pytest.approx(9.0)


def test_weights_are_inverse_squared_spreads_floored_capped_and_average_one():
    quotes = [{"spread_bp": s} for s in (0.2, 10.0, 20.0, None, 1000.0)]
    w = curve.weights_from_spreads(quotes)
    assert w.mean() == pytest.approx(1.0)
    raw = 1 / np.array([1.0, 10.0, 20.0, 15.0, 300.0]) ** 2     # floor 1 bp, median 15 bp for the gap, cap 300 bp
    assert w == pytest.approx(raw / raw.mean())


@pytest.mark.db
def test_a_real_day_fits_and_residuals_are_observed_minus_fitted(bond_models):
    conn = bond_models
    fit = conn.execute("select * from models.bond_curve_fit where method_version = '1.0.0'").fetchone()
    assert str(fit["obs_date"]) == "2026-08-31" and fit["n_quotes"] == 53
    assert fit["lambda_years"] == pytest.approx(2.821790673757931)
    assert 0 < fit["rmse_bp"] < 20
    points = conn.execute("select * from models.bond_curve_point where method_version = '1.0.0'").fetchall()
    assert len(points) == 53
    for p in points:
        assert p["residual_bp"] == pytest.approx((p["observed_yield"] - p["fitted_yield"]) * 100)
        assert p["tau_years"] >= curve.MIN_TAU_YEARS
    assert np.mean([p["weight"] for p in points]) == pytest.approx(1.0)


@pytest.mark.db
def test_version_2_fits_every_two_way_quote(bond_models):
    conn = bond_models
    two_way = conn.execute("""select count(*) n from models.bond_quotes q join models.bond_reference r
                              using (method_version, isin)
                              where q.method_version = '2.0.0' and q.mid_yield is not null
                                and (r.maturity_date - q.obs_date) / 365.25 >= 0.08""").fetchone()["n"]
    fit = conn.execute("select * from models.bond_curve_fit where method_version = '2.0.0'").fetchone()
    assert fit["n_quotes"] == two_way > 53
