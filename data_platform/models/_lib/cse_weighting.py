"""Ways of weighting a given set of shares, from the portfolio-construction literature, for the lab's research
(docs/research/portfolio-lab-optimisation-2026-11.md §7). Each takes a covariance matrix and returns long-only
weights summing to 1. Pure: no database, no dates.

  inverse_volatility       w_i proportional to 1 / sigma_i
  equal_risk               each share contributes the same share of the variance (Maillard, Roncalli & Teiletche
                           2010), by the convex form of Spinu (2013)
  max_diversification      maximises sum(w_i sigma_i) / sigma_p, the diversification ratio (Choueifaty & Coignard
                           2008)
  hrp                      hierarchical risk parity (Lopez de Prado 2016): cluster by correlation, order, then split
                           the weight top-down in inverse proportion to each half's variance
  equal                    1 / N (DeMiguel, Garlappi & Uppal 2009)
"""
from __future__ import annotations

import cvxpy as cp
import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform

SOLVER = "CLARABEL"


def equal(cov: np.ndarray) -> np.ndarray:
    n = cov.shape[0]
    return np.full(n, 1 / n)


def inverse_volatility(cov: np.ndarray) -> np.ndarray:
    iv = 1 / np.sqrt(np.diag(cov))
    return iv / iv.sum()


def equal_risk(cov: np.ndarray) -> np.ndarray:
    """min 1/2 y'Sy - (1/n) sum log y (Spinu 2013); w = y / sum y gives equal risk contributions."""
    n = cov.shape[0]
    y = cp.Variable(n)
    cp.Problem(cp.Minimize(0.5 * cp.quad_form(y, cp.psd_wrap(cov)) - cp.sum(cp.log(y)) / n), [y >= 1e-12]).solve(
        solver=SOLVER)
    w = np.maximum(y.value, 0)
    return w / w.sum()


def max_diversification(cov: np.ndarray) -> np.ndarray:
    """min y'Sy subject to sigma'y = 1, y >= 0; w = y / sum y maximises the diversification ratio."""
    n = cov.shape[0]
    sd = np.sqrt(np.diag(cov))
    y = cp.Variable(n)
    cp.Problem(cp.Minimize(cp.quad_form(y, cp.psd_wrap(cov))), [y >= 0, sd @ y == 1]).solve(solver=SOLVER)
    w = np.maximum(y.value, 0)
    return w / w.sum()


def hrp(cov: np.ndarray) -> np.ndarray:
    """Lopez de Prado (2016): single-linkage clustering on the distance sqrt((1 - rho) / 2), the leaves in cluster
    order, then recursive bisection, each half weighted in inverse proportion to its inverse-variance portfolio's
    variance."""
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    sd = np.sqrt(np.diag(cov))
    corr = np.clip(cov / np.outer(sd, sd), -1, 1)
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, None))
    np.fill_diagonal(dist, 0)
    order = list(leaves_list(linkage(squareform(dist, checks=False), method="single")))
    w = np.ones(n)

    def cluster_var(items: list[int]) -> float:
        c = cov[np.ix_(items, items)]
        iv = 1 / np.diag(c)
        iv = iv / iv.sum()
        return float(iv @ c @ iv)

    stack = [order]
    while stack:
        items = stack.pop()
        if len(items) < 2:
            continue
        half = len(items) // 2
        left, right = items[:half], items[half:]
        vl, vr = cluster_var(left), cluster_var(right)
        alpha = 1 - vl / (vl + vr)
        w[left] *= alpha
        w[right] *= 1 - alpha
        stack += [left, right]
    return w / w.sum()


METHODS = {"inverse_volatility": inverse_volatility, "equal_risk": equal_risk, "max_diversification": max_diversification,
           "hrp": hrp, "equal": equal}


def within_limits(w: np.ndarray, cap: float, floor: float, sectors: list[str] | None = None,
                  sector_cap: float | None = None, rounds: int = 200) -> np.ndarray:
    """Bring weights within the lab's limits (each between `floor` and `cap`, each sector at most `sector_cap`) by
    the smallest proportional moves: weight above a limit is taken off and shared among the others in proportion to
    their room, repeated until nothing moves. Used to give HRP the same limits as minimum variance."""
    w = np.asarray(w, float).copy()
    n = len(w)
    if cap * n < 1 - 1e-12 or floor * n > 1 + 1e-12:
        raise ValueError("the limits cannot all be met")
    for _ in range(rounds):
        moved = False
        low = w < floor - 1e-12
        if low.any():
            need = float((floor - w[low]).sum())
            w[low] = floor
            room = np.where(~low, w - floor, 0)
            w -= need * room / room.sum()
            moved = True
        high = w > cap + 1e-12
        if high.any():
            extra = float((w[high] - cap).sum())
            w[high] = cap
            room = np.where(~high, cap - w, 0)
            w += extra * room / room.sum()
            moved = True
        if sectors is not None and sector_cap is not None:
            for sec in set(sectors):
                idx = np.array([s == sec for s in sectors])
                tot = w[idx].sum()
                if tot > sector_cap + 1e-12:
                    w[idx] *= sector_cap / tot
                    room = np.where(~idx, cap - w, 0)
                    w += (tot - sector_cap) * room / room.sum()
                    moved = True
        if not moved:
            break
    return w / w.sum()
