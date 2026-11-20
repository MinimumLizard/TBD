"""Statistical tests for the lab's research (docs/research/portfolio-lab-optimisation-2026-11.md §7). Pure.

  variance_test   Ledoit & Wolf (2011), "Robust performance hypothesis testing with the variance", Wilmott: is the
                  variance of one return series different from another's, measured on the same days? The statistic
                  is the difference in log variances; its p-value comes from a studentized circular block
                  bootstrap, which respects the dependence over time and between the two series.
  holm            Holm's (1979) step-down adjustment of p-values for a family of tests.
"""
from __future__ import annotations

import numpy as np


def _delta_and_psi(a: np.ndarray, b: np.ndarray) -> tuple[float, np.ndarray]:
    """d = log var(a) - log var(b), and its influence values psi_t (the delta method on the four moments)."""
    m1, m2 = a.mean(), b.mean()
    q1, q2 = (a * a).mean(), (b * b).mean()
    v1, v2 = q1 - m1 * m1, q2 - m2 * m2
    grad = np.array([-2 * m1 / v1, 1 / v1, 2 * m2 / v2, -1 / v2])
    Y = np.column_stack([a - m1, a * a - q1, b - m2, b * b - q2])
    return float(np.log(v1) - np.log(v2)), Y @ grad


def _hac_se(psi: np.ndarray, bandwidth: int) -> float:
    """Newey-West (Bartlett kernel) standard error of the mean of psi."""
    T = len(psi)
    lrv = psi @ psi / T
    for k in range(1, bandwidth + 1):
        lrv += 2 * (1 - k / (bandwidth + 1)) * (psi[k:] @ psi[:-k]) / T
    return float(np.sqrt(max(lrv, 1e-300) / T))


def _block_se(psi: np.ndarray, block: int) -> float:
    """The standard error of the mean of a block-bootstrap sample, from its block sums (Gotze & Kunsch 1996)."""
    T = len(psi)
    k = T // block
    sums = psi[: k * block].reshape(k, block).sum(axis=1)
    return float(np.sqrt(max((sums @ sums) / (k * block), 1e-300) / T))


def variance_test(a: np.ndarray, b: np.ndarray, block: int = 10, draws: int = 4999, seed: int = 20261120) -> dict:
    """Two-sided test of equal variances of a and b (paired, same days). Returns the ratio var(a) / var(b), the
    difference in log variances, its HAC standard error and the bootstrap p-value."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    T = len(a)
    d, psi = _delta_and_psi(a, b)
    se = _hac_se(psi, block)
    rng = np.random.default_rng(seed)
    k = int(np.ceil(T / block))
    exceed = 0
    for _ in range(draws):
        starts = rng.integers(0, T, size=k)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:T] % T       # circular blocks
        d_star, psi_star = _delta_and_psi(a[idx], b[idx])
        se_star = _block_se(psi_star, block)
        if abs(d_star - d) / se_star >= abs(d) / se:
            exceed += 1
    return {"ratio": float(np.exp(d)), "log_difference": d, "se": se, "p_value": (exceed + 1) / (draws + 1), "n": T}


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm's step-down adjusted p-values (control of the family-wise error rate)."""
    order = sorted(p_values, key=p_values.get)
    m, out, running = len(order), {}, 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * p_values[k]))
        out[k] = running
    return out
