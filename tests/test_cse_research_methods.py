"""The research methods of the lab review (§7): each against its definition, on made-up numbers."""
from __future__ import annotations

import numpy as np
import pytest

from data_platform.models._lib import cse_covariance as cv
from data_platform.models._lib import cse_stats as st
from data_platform.models._lib import cse_weighting as wt


def cov_of(sd, corr):
    sd = np.asarray(sd, float)
    return np.outer(sd, sd) * corr


def test_nonlinear_shrinkage_keeps_eigenvectors_pulls_eigenvalues_together_and_learns_the_truth():
    rng = np.random.default_rng(1)
    p, n = 40, 400
    true = np.diag(np.linspace(1, 4, p))
    X = rng.multivariate_normal(np.zeros(p), true, size=n)
    S = X.T @ X / n
    C = cv.nonlinear(S, n)
    ls, lc = np.linalg.eigvalsh(S), np.linalg.eigvalsh(C)
    assert np.allclose(C, C.T) and lc.min() > 0
    assert lc.max() - lc.min() < ls.max() - ls.min()                      # the spread of eigenvalues shrinks
    err = lambda M: np.linalg.norm(M - true)  # noqa: E731
    assert err(C) < err(S)                                                 # and it is closer to the truth
    # fewer observations than shares: still symmetric and positive definite, closer to the truth than the sample
    Xs = X[:30]
    Ss = Xs.T @ Xs / 30
    Cs = cv.nonlinear(Ss, 30)
    assert np.allclose(Cs, Cs.T) and np.linalg.eigvalsh(Cs).min() > 0 and err(Cs) < err(Ss)


def test_ewma_weights_recent_days_more():
    rng = np.random.default_rng(2)
    calm, wild = rng.normal(0, 0.005, (200, 3)), rng.normal(0, 0.03, (40, 3))
    D = np.vstack([calm, wild])
    recent, _ = cv.ewma(D, 240, decay=0.97, lags=0)
    flat, _ = cv.daily(D, 240, lags=0)
    assert np.trace(recent) > np.trace(flat)                               # the recent wild days count more


def test_weightings_sum_to_one_long_only_and_follow_their_definitions():
    corr = np.full((4, 4), 0.3) + np.eye(4) * 0.7
    cov = cov_of([0.1, 0.2, 0.3, 0.4], corr)
    for name, f in wt.METHODS.items():
        w = f(cov)
        assert w.sum() == pytest.approx(1) and (w >= -1e-9).all(), name
    iv = wt.inverse_volatility(cov)
    assert iv[0] / iv[1] == pytest.approx(2)
    erc = wt.equal_risk(cov)
    rc = erc * (cov @ erc)
    assert np.allclose(rc / rc.sum(), 0.25, atol=1e-4)                     # equal risk contributions
    md = wt.max_diversification(cov)
    dr = lambda w: (w @ np.sqrt(np.diag(cov))) / np.sqrt(w @ cov @ w)  # noqa: E731
    for other in (iv, erc, wt.equal(cov), wt.hrp(cov)):
        assert dr(md) >= dr(other) - 1e-6                                  # the largest diversification ratio


def test_hrp_on_two_clean_clusters_splits_by_inverse_variance_of_the_halves():
    corr = np.eye(4)
    corr[0, 1] = corr[1, 0] = corr[2, 3] = corr[3, 2] = 0.9
    cov = cov_of([0.1, 0.1, 0.2, 0.2], corr)
    w = wt.hrp(cov)
    assert w[0] == pytest.approx(w[1]) and w[2] == pytest.approx(w[3])
    assert w[0] + w[1] == pytest.approx(0.8, abs=1e-6)                    # variances 1 : 4 -> weights 4 : 1


def test_the_variance_test_finds_a_real_difference_and_not_a_false_one():
    rng = np.random.default_rng(3)
    a = rng.normal(0, 0.010, 300)
    same = st.variance_test(a, a * 1.0 + rng.normal(0, 1e-6, 300), draws=999)
    assert same["p_value"] > 0.2
    calmer = st.variance_test(a * 0.7 + rng.normal(0, 0.001, 300), a, draws=999)
    assert calmer["ratio"] < 0.6 and calmer["p_value"] < 0.01


def test_holm_adjusts_in_step_down_order():
    adj = st.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_limits_are_met_with_the_smallest_moves():
    w = np.array([0.40, 0.25, 0.15, 0.10, 0.06, 0.04])
    out = wt.within_limits(w, cap=0.25, floor=0.08, sectors=["A", "A", "B", "B", "C", "C"], sector_cap=0.45)
    assert out.sum() == pytest.approx(1) and out.max() <= 0.25 + 1e-9 and out.min() >= 0.08 - 1e-9
    assert out[0] + out[1] <= 0.45 + 1e-9
    assert np.all(np.argsort(-out[2:]) == np.argsort(-w[2:]))              # the order of the others is kept
    with pytest.raises(ValueError):
        wt.within_limits(w, cap=0.1, floor=0.0)
