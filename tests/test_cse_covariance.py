"""The portfolio lab's covariance estimators (data_platform/models/_lib/cse_covariance.py): each against a direct
statement of its definition, and the properties every covariance must have."""
from __future__ import annotations

import numpy as np
import pytest
from sklearn.covariance import LedoitWolf

from data_platform.models._lib import cse_covariance as cv


def sample(T=40, N=12, seed=7, rho=0.3):
    rng = np.random.default_rng(seed)
    market = rng.normal(0, 0.02, T)
    beta = rng.uniform(0.4, 1.6, N)
    R = np.outer(market, beta) * np.sqrt(rho) + rng.normal(0, 0.03, (T, N)) * rng.uniform(0.5, 2.0, N)
    return R, market


@pytest.mark.parametrize("method", cv.METHODS)
def test_every_estimator_gives_a_symmetric_positive_definite_matrix_with_fewer_weeks_than_shares(method):
    R, market = sample(T=30, N=45)
    rng = np.random.default_rng(1)
    D = rng.normal(0, 0.012, (150, 45))
    cov, d = cv.estimate(method, R, market, D, 240)
    assert cov.shape == (45, 45)
    assert np.allclose(cov, cov.T)
    assert 0 <= d <= 1
    assert np.linalg.eigvalsh(cov).min() > 0


def test_identity_is_the_old_tools_estimator_to_the_last_bit():
    R, _ = sample()
    cov, d = cv.identity(R)
    lw = LedoitWolf().fit(R)
    assert (cov == lw.covariance_ * 52).all() and d == lw.shrinkage_


def test_constant_correlation_target_keeps_variances_and_uses_the_average_correlation():
    R, _ = sample()
    X = R - R.mean(axis=0)
    S = X.T @ X / len(X)
    cov, d = cv.constant_corr(R)
    assert 0 < d < 1
    assert np.allclose(np.diag(cov), np.diag(S) * 52)          # variances are never shrunk
    sd = np.sqrt(np.diag(S))
    corr = S / np.outer(sd, sd)
    n = len(sd)
    rbar = (corr.sum() - n) / (n * (n - 1))
    target = rbar * np.outer(sd, sd)
    np.fill_diagonal(target, np.diag(S))
    assert np.allclose(cov, (d * target + (1 - d) * S) * 52)


def test_constant_correlation_shrinks_fully_when_every_pair_truly_has_the_same_correlation():
    rng = np.random.default_rng(3)
    common = rng.normal(0, 1, (200, 1))
    R = 0.02 * (np.sqrt(0.4) * common + np.sqrt(0.6) * rng.normal(0, 1, (200, 30)))
    _, d = cv.constant_corr(R)
    _, d_few = cv.constant_corr(R[:30])
    assert d > 0.5 and d_few >= d                                # less data, more shrinkage


def test_single_index_target_is_the_market_model_with_the_sample_variances():
    R, market = sample()
    X = R - R.mean(axis=0)
    m = market - market.mean()
    S = X.T @ X / len(X)
    cov_m = X.T @ m / len(X)
    target = np.outer(cov_m, cov_m) / (m @ m / len(m))
    np.fill_diagonal(target, np.diag(S))
    cov, d = cv.single_index(R, market)
    assert 0 < d <= 1
    assert np.allclose(cov, (d * target + (1 - d) * S) * 52)
    assert np.allclose(np.diag(cov), np.diag(S) * 52)


def test_daily_adds_the_lagged_covariances_that_stale_prices_hide():
    # three shares react to the common news on the day, three one day late: the same-day covariance between the two
    # groups is near zero, though they all move together. The lagged terms recover the relation.
    rng = np.random.default_rng(11)
    news = rng.normal(0, 0.01, 2001)
    D = np.column_stack([news[1:] + rng.normal(0, 0.004, 2000) for _ in range(3)]
                        + [news[:-1] + rng.normal(0, 0.004, 2000) for _ in range(3)])
    with_lags, _ = cv.daily(D, 240, lags=2)
    without, _ = cv.daily(D, 240, lags=0)
    corr = lambda c: c[0, 3] / np.sqrt(c[0, 0] * c[3, 3])
    assert abs(corr(without)) < 0.1 and corr(with_lags) > 0.3
    assert np.linalg.eigvalsh(with_lags).min() > 0


def test_unknown_method_and_missing_inputs_are_refused():
    R, _ = sample()
    with pytest.raises(ValueError, match="unknown covariance method"):
        cv.estimate("sample", R)
    with pytest.raises(ValueError, match="market"):
        cv.estimate("single_index", R)
    with pytest.raises(ValueError, match="daily"):
        cv.estimate("daily", R)
