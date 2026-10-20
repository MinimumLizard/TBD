"""Long-only, fully invested model portfolios with cvxpy and the Clarabel solver (audit C10), and the retail versions
with fewer names (docs/plan-retail-features.md §6). Shared by cse_portfolio_lab and the lab report.

The first part is a line-for-line port of MinimumLizard/CSE@e05c6f3 cse/optimize.py: the same problems, written in
the same order, solved by the same solver version, so the weights agree with the old tool's to the last bit on the
same inputs. Constraints for minimum variance, risk parity and maximum Sharpe:

  0 <= w_i <= cap_i,  cap_i = min(max_weight, participation x median daily turnover_i x days_to_build / notional)
  sum over a sector of w_i <= max_sector_weight,   sum over an ownership group of w_i <= max_group_weight,
  sum of w_i = 1.

A group is the companies whose ownership traces to the same holder (cse_ownership); a one-share group adds a
constraint only when max_group_weight is tighter than max_weight. When the constraints cannot all hold,
check_feasible names the binding one and nothing is solved.

The second part (retail_*) is new: a portfolio of K names, taken from the full portfolio's largest weights with a
buffer for names already in it, re-optimised on those names only, as scripts/research/fewer_names.py measured it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np
import pandas as pd

SOLVER = "CLARABEL"
FULL = ("min_variance", "risk_parity", "max_sharpe", "equal_weight")
LABELS = {"min_variance": "Minimum variance", "risk_parity": "Risk parity", "max_sharpe": "Maximum Sharpe",
          "equal_weight": "Equal weight", "market": "Market (ASPI)"}


class Infeasible(RuntimeError):
    """The constraints admit no fully invested portfolio. The message names what binds."""


@dataclass
class Problem:
    symbols: list[str]
    sectors: list[str]
    cov: np.ndarray
    er: np.ndarray
    rf: float
    caps: np.ndarray
    liq_caps: np.ndarray
    max_weight: float
    max_sector_weight: float
    groups: list[str] | None = None            # group key per share (None: no group constraint)
    max_group_weight: float | None = None

    @property
    def sector_names(self) -> list[str]:
        return sorted(set(self.sectors))

    def sector_matrix(self) -> np.ndarray:
        return np.array([[1.0 if s == name else 0.0 for s in self.sectors] for name in self.sector_names])

    @property
    def group_names(self) -> list[str]:
        """Groups that need a constraint: those with two or more shares in the problem, plus every one-share group
        when max_group_weight is tighter than max_weight."""
        if not self.groups or self.max_group_weight is None:
            return []
        counts = pd.Series(self.groups).value_counts()
        need = 1 if self.max_group_weight < self.max_weight else 2
        return sorted(counts[counts >= need].index)

    def group_matrix(self) -> np.ndarray:
        return np.array([[1.0 if g == name else 0.0 for g in self.groups] for name in self.group_names]) \
            if self.group_names else np.zeros((0, len(self.symbols)))


def make_problem(symbols: list[str], sectors: dict[str, str], cov: np.ndarray, er: pd.Series, rf: float,
                 median_turnover: pd.Series, cfg: dict, groups: dict[str, str] | None = None) -> Problem:
    """Old make_problem(est, cfg, groups). cfg["notional_lkr"] is the portfolio size the liquidity caps are computed
    for (the old portfolio_size_lkr)."""
    med = median_turnover.reindex(symbols).to_numpy()
    liq = cfg["participation"] * med * cfg["days_to_build"] / cfg["notional_lkr"]
    caps = np.minimum(cfg["max_weight"], liq)
    return Problem(symbols=list(symbols), sectors=[sectors[s] for s in symbols],
                   cov=np.asarray(cov), er=er.reindex(symbols).to_numpy(), rf=rf,
                   caps=caps, liq_caps=liq, max_weight=cfg["max_weight"],
                   max_sector_weight=cfg["max_sector_weight"],
                   groups=[groups.get(s, s) for s in symbols] if groups and cfg.get("max_group_weight") else None,
                   max_group_weight=cfg.get("max_group_weight") if groups else None)


def check_feasible(p: Problem) -> None:
    """sum(caps) >= 1 and the sum over sectors of min(sector cap, the sector's caps) >= 1 are necessary and, for box
    and sector constraints alone, sufficient. Group caps overlap sectors, so with groups the same reach test is
    applied per group and an exact LP decides what remains."""
    n_liq = int((p.liq_caps < p.max_weight).sum())
    total = float(p.caps.sum())
    if total < 1 - 1e-9:
        raise Infeasible(
            f"per-stock caps sum to {total:.3f} < 1: max_weight {p.max_weight:.0%} across {len(p.symbols)} "
            f"stocks allows {min(1, p.max_weight * len(p.symbols)):.0%}, and the liquidity cap is tighter "
            f"than max_weight for {n_liq} of them. Binding: "
            + ("max_weight (too few stocks)" if p.max_weight * len(p.symbols) < 1 else "liquidity caps"))
    S = p.sector_matrix()
    reach = np.minimum(p.max_sector_weight, S @ p.caps)
    if reach.sum() < 1 - 1e-9:
        raise Infeasible(
            f"sector caps bind: with max_sector_weight {p.max_sector_weight:.0%} and the per-stock caps, "
            f"the {len(p.sector_names)} sectors can hold at most {reach.sum():.3f} in total")
    G = p.group_matrix()
    if len(G):
        alone = 1 - G.sum(axis=0)                  # shares in no multi-share group
        greach = float(np.minimum(p.max_group_weight, G @ p.caps).sum() + alone @ p.caps)
        if greach < 1 - 1e-9:
            raise Infeasible(
                f"group caps bind: with max_group_weight {p.max_group_weight:.0%} and the per-stock caps, "
                f"the universe can hold at most {greach:.3f} in total")
        w = cp.Variable(len(p.symbols))
        prob = cp.Problem(cp.Minimize(0), _constraints(p, w) + [cp.sum(w) == 1])
        prob.solve(solver=SOLVER)
        if prob.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            raise Infeasible(f"sector and group caps bind together (max_sector_weight {p.max_sector_weight:.0%}, "
                             f"max_group_weight {p.max_group_weight:.0%}): no fully invested portfolio satisfies both")


def _constraints(p: Problem, w, scale=1.0):
    """Linear constraints on w; `scale` homogenises them (w = y / kappa formulations)."""
    S, G = p.sector_matrix(), p.group_matrix()
    cons = [w >= 0, w <= p.caps * scale, S @ w <= p.max_sector_weight * scale]
    return cons + ([G @ w <= p.max_group_weight * scale] if len(G) else [])


def _solve(prob: cp.Problem, what: str):
    prob.solve(solver=SOLVER)
    if prob.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
        raise Infeasible(f"{what}: solver status {prob.status}")


def _clean(w: np.ndarray) -> np.ndarray:
    w = np.where(w < 1e-7, 0.0, w)
    return w / w.sum()


def min_variance(p: Problem) -> np.ndarray:
    w = cp.Variable(len(p.symbols))
    _solve(cp.Problem(cp.Minimize(cp.quad_form(w, cp.psd_wrap(p.cov))),
                      _constraints(p, w) + [cp.sum(w) == 1]), "minimum variance")
    return _clean(w.value)


def max_sharpe(p: Problem) -> np.ndarray:
    """Homogenised form: min y'Sy s.t. (mu - rf)'y = 1, y = kappa w with the constraints scaled by kappa."""
    excess = p.er - p.rf
    if (excess <= 0).all():
        raise Infeasible("maximum Sharpe: no stock has a positive expected excess return")
    y, k = cp.Variable(len(p.symbols)), cp.Variable(nonneg=True)
    _solve(cp.Problem(cp.Minimize(cp.quad_form(y, cp.psd_wrap(p.cov))),
                      _constraints(p, y, k) + [cp.sum(y) == k, excess @ y == 1]), "maximum Sharpe")
    return _clean(y.value / k.value)


def risk_parity(p: Problem) -> np.ndarray:
    """Equal risk contribution via the convex log-barrier formulation (Spinu 2013): min 1/2 y'Sy - (1/n) sum log y_i,
    then w = y / sum(y). The caps enter as homogeneous linear constraints on y (y_i <= cap_i sum(y), sector sums
    <= cap sum(y)). Where a cap binds, contributions cannot all be equal; the actual contributions are reported."""
    n = len(p.symbols)
    y = cp.Variable(n)
    t = cp.sum(y)
    obj = 0.5 * cp.quad_form(y, cp.psd_wrap(p.cov)) - cp.sum(cp.log(y)) / n
    G = p.group_matrix()
    _solve(cp.Problem(cp.Minimize(obj), [y >= 1e-9, y <= p.caps * t,
                                         p.sector_matrix() @ y <= p.max_sector_weight * t]
                      + ([G @ y <= p.max_group_weight * t] if len(G) else [])), "risk parity")
    return _clean(y.value / y.value.sum())


def max_return(p: Problem) -> float:
    w = cp.Variable(len(p.symbols))
    _solve(cp.Problem(cp.Maximize(p.er @ w), _constraints(p, w) + [cp.sum(w) == 1]), "maximum return")
    return float(p.er @ w.value)


def frontier(p: Problem, points: int = 25) -> list[dict]:
    """Constrained efficient frontier: minimum variance at target expected returns from the minimum-variance
    portfolio's return up to the highest feasible return."""
    w0 = min_variance(p)
    lo, hi = float(p.er @ w0), max_return(p)
    out = []
    for target in np.linspace(lo, hi, points):
        w = cp.Variable(len(p.symbols))
        prob = cp.Problem(cp.Minimize(cp.quad_form(w, cp.psd_wrap(p.cov))),
                          _constraints(p, w) + [cp.sum(w) == 1, p.er @ w >= target - 1e-10])
        prob.solve(solver=SOLVER)
        if prob.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            wv = np.clip(w.value, 0, None)
            out.append({"er": float(p.er @ wv), "vol": float(np.sqrt(wv @ p.cov @ wv))})
    return out


def risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Share of portfolio variance from each holding: w_i (Sw)_i / w'Sw (sums to 1)."""
    var = float(w @ cov @ w)
    return w * (cov @ w) / var if var > 0 else np.zeros_like(w)


def summary(name: str, w: np.ndarray, p: Problem) -> dict:
    vol = float(np.sqrt(w @ p.cov @ w))
    er = float(p.er @ w)
    rc = risk_contributions(w, p.cov)
    sector = pd.Series(w, index=p.sectors).groupby(level=0).sum()
    holdings = [{"symbol": s, "weight": float(wi), "risk_contribution": float(ri), "cap": float(c),
                 "sector": sec, "er": float(e)}
                for s, wi, ri, c, sec, e in zip(p.symbols, w, rc, p.caps, p.sectors, p.er) if wi > 1e-6]
    holdings.sort(key=lambda h: -h["weight"])
    groups = {}
    if p.group_names:
        gw = pd.Series(w, index=p.groups).groupby(level=0).sum()
        groups = {k: float(gw[k]) for k in p.group_names if gw[k] > 1e-6}
        groups = dict(sorted(groups.items(), key=lambda kv: -kv[1]))
    return {"groups": groups, "name": name, "er": er, "vol": vol, "sharpe": (er - p.rf) / vol if vol else None,
            "holdings": holdings,
            "sectors": {k: float(v) for k, v in sector[sector > 1e-6].sort_values(ascending=False).items()},
            "n": len(holdings)}


def constraint_report(w: np.ndarray, p: Problem, tol: float = 1e-6) -> dict:
    """Every constraint, checked numerically (old constraint_report)."""
    S, G = p.sector_matrix(), p.group_matrix()
    group_over = float((G @ w - p.max_group_weight).max()) if len(G) else -1.0
    return {"sum": float(w.sum()), "min": float(w.min()),
            "max_over_cap": float((w - p.caps).max()),
            "max_sector_over": float((S @ w - p.max_sector_weight).max()),
            "max_group_over": group_over,
            "ok": bool(abs(w.sum() - 1) < tol and w.min() >= -tol and (w - p.caps).max() <= tol
                       and (S @ w - p.max_sector_weight).max() <= tol and group_over <= tol)}


def solve_full(p: Problem) -> dict[str, np.ndarray]:
    """Old lab.compute(): feasibility, the three optimised portfolios (each checked against every constraint) and
    equal weight. Raises Infeasible naming the binding constraint."""
    check_feasible(p)
    w = {"min_variance": min_variance(p), "risk_parity": risk_parity(p), "max_sharpe": max_sharpe(p)}
    for name, wv in w.items():
        rep = constraint_report(wv, p)
        if not rep["ok"]:
            raise RuntimeError(f"{name} violates constraints: {rep}")
    w["equal_weight"] = np.full(len(p.symbols), 1 / len(p.symbols))
    return w


# --- what binds (new: the old page showed the constraint report only) ----------------------------------------------

AT_CAP = 1e-6


def binding(w: np.ndarray, p: Problem, floor: float | None = None) -> list[str]:
    """The constraints that hold with equality at w (to 1e-6), in words: shares at their cap (and whether the cap
    is the per-share maximum or the liquidity cap), sectors and ownership groups at theirs, names at the retail floor.
    Equal weight has no caps: nothing binds."""
    out = []
    at_cap = [i for i in range(len(w)) if w[i] >= p.caps[i] - AT_CAP and w[i] > AT_CAP]
    liq = sum(1 for i in at_cap if p.liq_caps[i] < p.max_weight)
    if at_cap:
        out.append(f"{len(at_cap)} {'share' if len(at_cap) == 1 else 'shares'} at the {p.max_weight:.1%} cap per share"
                   + (f" ({liq} at the liquidity cap)" if liq else ""))
    sector = pd.Series(w, index=p.sectors).groupby(level=0).sum()
    for name, v in sector.items():
        if v >= p.max_sector_weight - AT_CAP:
            out.append(f"sector {name} at the {p.max_sector_weight:.0%} cap")
    if p.group_names:
        gw = pd.Series(w, index=p.groups).groupby(level=0).sum()
        for name in p.group_names:
            if gw[name] >= p.max_group_weight - AT_CAP:
                out.append(f"ownership group {name} at the {p.max_group_weight:.0%} cap")
    if floor is not None:
        n = sum(1 for x in w if AT_CAP < x <= floor + AT_CAP)
        if n:
            out.append(f"{n} {'name' if n == 1 else 'names'} at the {floor:.1%} floor")
    return out


# --- retail versions with fewer names (new; docs/plan-retail-features.md §6) ---------------------------------------

def retail_cap(k: int, max_weight: float) -> float:
    """The per-share cap of a K-name portfolio: max(max_weight, 1.5 / K) (ten names at a 10 % cap leave no choice)."""
    return max(max_weight, 1.5 / k)


def retail_floor(k: int) -> float:
    """The smallest weight of a name in a K-name portfolio: 0.5 / K, so every holding is worth having."""
    return 0.5 / k


def ranking(full: np.ndarray, symbols: list[str]) -> list[str]:
    """The full portfolio's names (weight > 1e-6), largest weight first (numpy's argsort, as the research script)."""
    order = np.argsort(-full)
    return [symbols[i] for i in order if full[i] > 1e-6]


def retail_names(ranked: list[str], k: int, previous: list[str] | None, buffer: float) -> list[str]:
    """The K names: names already in the portfolio stay while they rank within the top floor(buffer x K) of the full
    portfolio; the remaining places go to the highest-ranked names not yet in. Without a previous portfolio: the top
    K. Returned in ranking order."""
    rank = {s: i for i, s in enumerate(ranked)}
    keep = [s for s in (previous or []) if s in rank and rank[s] < int(buffer * k)]
    for s in ranked:
        if len(keep) >= k:
            break
        if s not in keep:
            keep.append(s)
    return sorted(keep, key=lambda s: rank[s])


def subproblem(p: Problem, idx: list[int], cap: float) -> Problem:
    """The full problem on the chosen names only: the same sector, group and liquidity caps, per-share cap `cap`
    (as the research script)."""
    return Problem(
        symbols=[p.symbols[i] for i in idx], sectors=[p.sectors[i] for i in idx],
        cov=p.cov[np.ix_(idx, idx)], er=p.er[idx], rf=p.rf,
        caps=np.minimum(cap, p.liq_caps[idx]), liq_caps=p.liq_caps[idx], max_weight=cap,
        max_sector_weight=p.max_sector_weight,
        groups=[p.groups[i] for i in idx] if p.groups else None, max_group_weight=p.max_group_weight)


def solve_retail(kind: str, p: Problem, floor: float) -> np.ndarray:
    """Minimum variance or maximum Sharpe on the chosen names with every name at or above `floor` (the research
    script's problems). Equal weight: 1/K, no caps (the comparison, like the full equal-weight portfolio).
    Raises Infeasible when the caps and the floor cannot all hold."""
    n = len(p.symbols)
    if kind == "equal_weight":
        return np.full(n, 1 / n)
    if kind == "max_sharpe":                       # the old optimize.max_sharpe, homogenised, plus the floor
        y, k = cp.Variable(n), cp.Variable(nonneg=True)
        cons = _constraints(p, y, k) + [cp.sum(y) == k, (p.er - p.rf) @ y == 1, y >= floor * k]
        problem = cp.Problem(cp.Minimize(cp.quad_form(y, cp.psd_wrap(p.cov))), cons)
        problem.solve(solver=SOLVER)
        if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            raise Infeasible(f"maximum Sharpe on {n} names: the sector or group caps and the floor cannot all hold")
        return _clean(y.value / k.value)
    if kind != "min_variance":
        raise ValueError(f"no retail version of {kind}")
    x = cp.Variable(n)
    problem = cp.Problem(cp.Minimize(cp.quad_form(x, cp.psd_wrap(p.cov))),
                         _constraints(p, x) + [cp.sum(x) == 1, x >= floor])
    problem.solve(solver=SOLVER)
    if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
        raise Infeasible(f"minimum variance on {n} names: the sector or group caps and the floor cannot all hold")
    return _clean(x.value)


def tracking_error(w: np.ndarray, full: np.ndarray, cov: np.ndarray) -> float:
    """Estimated annual tracking error against the full portfolio: sqrt((w - w_full)' S (w - w_full))."""
    d = w - full
    return float(np.sqrt(d @ cov @ d))


def stats(w: np.ndarray, p: Problem) -> dict:
    er, vol = float(w @ p.er), float(np.sqrt(w @ p.cov @ w))
    return {"expected_return": er, "volatility": vol, "sharpe": (er - p.rf) / vol if vol else None}
