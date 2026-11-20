"""Covariance estimators for the portfolio lab (decision 0025), beside the one the old tool used.

The lab has about 140 shares and, at best, 52 weekly returns: far fewer observations than shares, so the sample
covariance cannot be used as it is. Every estimator here pulls ("shrinks") the sample covariance towards a simpler
matrix, by an amount computed from the data. They differ in what that simpler matrix is:

  identity         every share equally risky, none related (Ledoit & Wolf 2004a; scikit-learn's LedoitWolf: the
                   old tool's estimator and the lab's versions 1.0.0 and 1.1.0);
  oas              the same target, with the Oracle Approximating amount (Chen, Wiesel, Eldar & Hero 2010);
  constant_corr    each share keeps its own variance; every pair has the same, average correlation (Ledoit & Wolf
                   2004b, "Honey, I shrunk the sample covariance matrix");
  single_index     each share keeps its own variance; pairs are related only through the market (Ledoit & Wolf 2003,
                   "Improved estimation of the covariance matrix of stock returns");
  daily            the identity target on daily returns (several times more observations), with the covariances of
                   returns one and two days apart added in (Bartlett weights), because thinly traded shares react to
                   news a day or two late and same-day covariances alone understate how they move together.

All take returns as a T x N array, remove each share's mean, and return the annualised covariance and the shrinkage
amount (0 = the sample covariance, 1 = the target). Pure: no database, no dates. The formulas follow the papers' own
published code; tests/ checks each against a direct statement of its definition.

Which one the lab uses is decided by a walk-forward test on realised risk, never on returns
(scripts/research/lab_tournament.py; docs/research/portfolio-lab-optimisation-2026-11.md).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from sklearn.covariance import OAS, LedoitWolf

from .cse_estimates import sample_on_or_before

METHODS = ("identity", "oas", "constant_corr", "single_index", "daily")
WEEKS_PER_YEAR = 52


def _demean(R: np.ndarray) -> np.ndarray:
    X = np.asarray(R, dtype=float)
    return X - X.mean(axis=0)


def _amount(pi: float, rho: float, gamma: float, T: int) -> float:
    """The shrinkage amount of the two Ledoit-Wolf papers: (pi - rho) / gamma / T, kept within [0, 1]."""
    if gamma <= 0:
        return 0.0
    return float(max(0.0, min(1.0, (pi - rho) / gamma / T)))


def identity(R: np.ndarray, periods: int = WEEKS_PER_YEAR) -> tuple[np.ndarray, float]:
    lw = LedoitWolf().fit(np.asarray(R, dtype=float))
    return lw.covariance_ * periods, float(lw.shrinkage_)


def oas(R: np.ndarray, periods: int = WEEKS_PER_YEAR) -> tuple[np.ndarray, float]:
    m = OAS().fit(np.asarray(R, dtype=float))
    return m.covariance_ * periods, float(m.shrinkage_)


def constant_corr(R: np.ndarray, periods: int = WEEKS_PER_YEAR) -> tuple[np.ndarray, float]:
    """Ledoit & Wolf 2004b. Target: the sample variances, and the average sample correlation for every pair."""
    X = _demean(R)
    T, N = X.shape
    S = X.T @ X / T
    var = np.diag(S).copy()
    sd = np.sqrt(var)
    if N < 2 or (sd <= 0).any():
        return S * periods, 0.0
    corr = S / np.outer(sd, sd)
    rbar = (corr.sum() - N) / (N * (N - 1))
    F = rbar * np.outer(sd, sd)
    np.fill_diagonal(F, var)
    Y = X ** 2
    phi_mat = Y.T @ Y / T - S ** 2                 # the variance of each entry of S
    theta = (X ** 3).T @ X / T - var[:, None] * S  # the covariance of s_ii with s_ij
    np.fill_diagonal(theta, 0.0)
    rho = np.trace(phi_mat) + rbar * (np.outer(1 / sd, sd) * theta).sum()
    gamma = float(((S - F) ** 2).sum())
    d = _amount(float(phi_mat.sum()), float(rho), gamma, T)
    return (d * F + (1 - d) * S) * periods, d


def single_index(R: np.ndarray, market: np.ndarray, periods: int = WEEKS_PER_YEAR) -> tuple[np.ndarray, float]:
    """Ledoit & Wolf 2003. Target: the one-factor (market) model's covariance, with the sample variances."""
    X = _demean(R)
    T, _ = X.shape
    m = np.asarray(market, dtype=float)
    m = m - m.mean()
    S = X.T @ X / T
    cov_m = X.T @ m / T
    var_m = float(m @ m / T)
    if var_m <= 0:
        return S * periods, 0.0
    F = np.outer(cov_m, cov_m) / var_m
    np.fill_diagonal(F, np.diag(S))
    Y = X ** 2
    phi_mat = Y.T @ Y / T - S ** 2
    Z = X * m[:, None]
    v1 = Y.T @ Z / T - cov_m[:, None] * S
    roff1 = (v1 * cov_m[None, :]).sum() / var_m - (np.diag(v1) * cov_m).sum() / var_m
    v3 = Z.T @ Z / T - var_m * S
    roff3 = ((v3 * np.outer(cov_m, cov_m)).sum() - (np.diag(v3) * cov_m ** 2).sum()) / var_m ** 2
    rho = np.trace(phi_mat) + 2 * roff1 - roff3
    gamma = float(((S - F) ** 2).sum())
    d = _amount(float(phi_mat.sum()), float(rho), gamma, T)
    return (d * F + (1 - d) * S) * periods, d


def daily(D: np.ndarray, periods: float, lags: int = 2) -> tuple[np.ndarray, float]:
    """The identity target on daily returns D (T x N), after adding the covariances of returns up to `lags` days apart
    with Bartlett weights 1 - l / (lags + 1) (which keep the matrix positive semi-definite). `periods` is the number
    of sessions in a year. The shrinkage amount is the Ledoit-Wolf amount of the daily returns themselves."""
    X = _demean(D)
    T, N = X.shape
    S = X.T @ X / T
    for lag in range(1, lags + 1):
        if T <= lag:
            break
        G = X[lag:].T @ X[:-lag] / T
        S = S + (1 - lag / (lags + 1)) * (G + G.T)
    d = float(LedoitWolf().fit(X).shrinkage_)
    return ((1 - d) * S + d * (np.trace(S) / N) * np.eye(N)) * periods, d


def nonlinear(S: np.ndarray, n: int) -> np.ndarray:
    """Ledoit & Wolf (2020), "Analytical nonlinear shrinkage of large-dimensional covariance matrices", Annals of
    Statistics 48(5): each sample eigenvalue is replaced by its own estimate of the population eigenvalue (a kernel
    estimate of the spectral density and its Hilbert transform, Epanechnikov kernel, bandwidth n^(-1/3)); the
    eigenvectors are kept. `S` is a covariance matrix estimated from `n` observations. A transcription of the
    authors' published code, both cases: n >= the dimension p, and n < p (the p - n null eigenvalues get one value)."""
    p = S.shape[0]
    lam, u = np.linalg.eigh(S)                          # ascending
    lam = np.maximum(lam, 0.0)
    nz = lam[max(0, p - n):]                            # the min(p, n) eigenvalues that can be non-zero
    nz = np.maximum(nz, 1e-18)
    m = len(nz)
    h = n ** (-1 / 3)
    L = np.tile(nz, (m, 1)).T
    H = h * L.T
    with np.errstate(divide="ignore", invalid="ignore"):
        x = (L - L.T) / H
        f = 3 / 4 / np.sqrt(5) * np.mean(np.maximum(1 - x ** 2 / 5, 0) / H, axis=1)
        hf = (-3 / 10 / np.pi) * x + (3 / 4 / np.sqrt(5) / np.pi) * (1 - x ** 2 / 5) * np.log(
            np.abs((np.sqrt(5) - x) / (np.sqrt(5) + x)))
    edge = np.abs(x) == np.sqrt(5)
    hf[edge] = (-3 / 10 / np.pi) * x[edge]
    hf = np.mean(np.nan_to_num(hf) / H, axis=1)
    c = p / n
    if p <= n:
        d = nz / ((np.pi * c * nz * f) ** 2 + (1 - c - np.pi * c * nz * hf) ** 2)
    else:
        hf0 = (1 / np.pi) * (3 / 10 / h ** 2 + 3 / 4 / np.sqrt(5) / h * (1 - 1 / 5 / h ** 2)
                             * np.log((1 + np.sqrt(5) * h) / (1 - np.sqrt(5) * h))) * np.mean(1 / nz)
        d0 = 1 / (np.pi * (p - n) / n * hf0)
        d1 = nz / (np.pi ** 2 * nz ** 2 * (f ** 2 + hf ** 2))
        d = np.concatenate([np.full(p - n, d0), d1])
    return (u * d) @ u.T


def ewma(D: np.ndarray, periods: float, decay: float = 0.97, lags: int = 2) -> tuple[np.ndarray, float]:
    """An exponentially weighted covariance of the daily returns (RiskMetrics 1996), recent sessions weighted more
    (weight decay^age, normalised), with the same lagged terms and Ledoit-Wolf amount as `daily`."""
    T = len(D)
    w = decay ** np.arange(T - 1, -1, -1)
    w = w / w.sum()
    X = D - w @ D
    S = (X * w[:, None]).T @ X
    for lag in range(1, lags + 1):
        if T <= lag:
            break
        wl = w[lag:] / w[lag:].sum()
        G = (X[lag:] * wl[:, None]).T @ X[:-lag]
        S = S + (1 - lag / (lags + 1)) * (G + G.T)
    d = float(LedoitWolf().fit(D - D.mean(axis=0)).shrinkage_)
    N = S.shape[0]
    return ((1 - d) * S + d * (np.trace(S) / N) * np.eye(N)) * periods, d


def daily_nonlinear(D: np.ndarray, periods: float, lags: int = 2) -> tuple[np.ndarray, float]:
    """The lag-adjusted daily matrix of `daily`, with nonlinear shrinkage in place of the linear one. The second value
    is the average relative change of the eigenvalues (for reporting; there is no single amount)."""
    X = _demean(D)
    T = len(X)
    S = X.T @ X / T
    for lag in range(1, lags + 1):
        if T <= lag:
            break
        G = X[lag:].T @ X[:-lag] / T
        S = S + (1 - lag / (lags + 1)) * (G + G.T)
    C = nonlinear(S, T)
    before, after = np.linalg.eigvalsh(S), np.linalg.eigvalsh(C)
    return C * periods, float(np.mean(np.abs(after - before) / np.maximum(before, 1e-18)))


def estimate(method: str, weekly: np.ndarray, market_weekly: np.ndarray | None = None,
             daily_returns: np.ndarray | None = None, sessions_per_year: float | None = None) -> tuple[np.ndarray, float]:
    """The annualised covariance and shrinkage amount by `method` (one of METHODS)."""
    if method == "identity":
        return identity(weekly)
    if method == "oas":
        return oas(weekly)
    if method == "constant_corr":
        return constant_corr(weekly)
    if method == "single_index":
        if market_weekly is None:
            raise ValueError("single_index needs the market's weekly returns")
        return single_index(weekly, market_weekly)
    if method == "daily":
        if daily_returns is None or not sessions_per_year:
            raise ValueError("daily needs the daily returns and the number of sessions in a year")
        return daily(daily_returns, sessions_per_year)
    raise ValueError(f"unknown covariance method {method!r}; one of {METHODS}")


def daily_window(tri: dict[str, pd.Series], sessions: list[str], symbols: list[str], first_week: str,
                 session: str) -> tuple[np.ndarray, float]:
    """The daily total returns of `symbols` over the same span as an estimate's weekly returns (from the Wednesday
    before its first week, `first_week`, to the estimate date `session`), a session without a trade counting as no
    change, and the number of sessions in a year over that span. Reads only levels on or before `session`.

    Shared by cse_lab_backtest, cse_risk_estimates and cse_portfolio_lab (from their versions 1.1.0, 1.2.0 and
    1.2.0), so the three compute the same covariance on the same date."""
    first = (dt.date.fromisoformat(first_week) - dt.timedelta(days=7)).isoformat()
    days = [s for s in sessions if first <= s <= session]
    levels = np.column_stack([sample_on_or_before(tri[s], days).to_numpy() for s in symbols])
    D = levels[1:] / levels[:-1] - 1
    D = np.where(np.isfinite(D), D, 0.0)
    years = max((dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])).days / 365.25, 1 / 365.25)
    return D, (len(days) - 1) / years
