"""The portfolio lab's universe and risk estimates (audit C8, C9), shared by cse_risk_estimates and the lab report.

A line-for-line port of MinimumLizard/CSE@e05c6f3 cse/returns.py (wednesdays, sample_on_or_before, weekly_returns,
weekly_sum) and cse/estimates.py (daily_turnover, select_universe, dimson_beta, estimate). The arithmetic and the
order of every operation are unchanged, so the numbers agree with the old tool to the last bit on the same inputs.
What differs is plumbing:

  * the old code read the repo's CSV files cut at one session; here the facts arrive once (History: the ASPI
    calendar, each share's prices and total-return index from cse_total_returns) and every estimate date reads only
    the part up to that date (each function below only ever looks at dates on or before it, which the tests check);
  * a share's weekly turnover over one week does not depend on the estimate date, so it is computed once per share and
    week and reused (the same expression on the same rows);
  * the old conflict-of-interest list, the risk-free rate and the market proxy arrive as arguments.

Dates are ISO strings (as in the old CSVs), so comparisons are the old code's string comparisons.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

EQUITY_SUFFIXES = (".N0000", ".X0000")
SUFFIX_KIND = {"R": "rights", "W": "warrant", "P": "preference share", "U": "fund units",
               "D": "no equity prices (debt issuer)"}
EXCLUDED_REASON = "excluded (conflict of interest)"


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str


@dataclass
class Universe:
    symbols: list[str]
    dropped: list[dict]                         # {"symbol", "name", "reason"}
    stats: pd.DataFrame                         # per ordinary share: weeks, traded share, turnover


@dataclass
class Estimates:
    session: str
    weeks: list[str]                            # the Wednesdays the weekly returns end on
    symbols: list[str]
    sectors: dict[str, str]
    returns: pd.DataFrame                       # T x N weekly total returns
    market: pd.Series                           # weekly market (ASPI) returns
    cov: np.ndarray                             # annualised Ledoit-Wolf covariance
    shrinkage: float
    beta: pd.Series                             # Dimson beta
    beta_parts: pd.DataFrame                    # slope on the current and the lagged market return
    er: pd.Series                               # CAPM expected return
    vol: pd.Series                              # sqrt(diag(cov))
    amihud: pd.Series
    median_turnover: pd.Series
    turnover_source: pd.Series                  # "real" / "estimated" / "mixed"
    rf: float = 0.0


# --- old cse/returns.py ------------------------------------------------------------------------------------------

def wednesdays(start: str, end: str) -> list[str]:
    return [d.date().isoformat() for d in pd.date_range(start, end, freq="W-WED")]


def sample_on_or_before(level: pd.Series, dates: list[str]) -> pd.Series:
    """Last value on or before each date (NaN before the first observation)."""
    level = level.sort_index()
    idx = np.searchsorted(np.array(level.index, dtype=object), np.array(dates, dtype=object), side="right") - 1
    vals = [float(level.iloc[i]) if i >= 0 else np.nan for i in idx]
    return pd.Series(vals, index=dates)


def weekly_returns(level: pd.Series, weds: list[str]) -> pd.Series:
    """Wednesday-to-Wednesday returns of a level series (TRI or index), using the last value on or before each
    Wednesday. The first Wednesday has no return; weeks before the first observation are NaN."""
    s = sample_on_or_before(level, weds)
    return (s / s.shift(1) - 1).iloc[1:]


def weekly_sum(daily: pd.Series, weds: list[str]) -> pd.Series:
    """Sum of a daily series over (previous Wednesday, Wednesday]."""
    daily = daily.sort_index()
    out = {}
    for w0, w1 in zip(weds, weds[1:]):
        out[w1] = float(daily[(daily.index > w0) & (daily.index <= w1)].sum())
    return pd.Series(out)


# --- the facts, once ---------------------------------------------------------------------------------------------

class History:
    """Everything the estimates read, for all dates at once; each estimate date uses only the part up to it.

    sessions: the ASPI's session dates (the market calendar); aspi: date -> ASPI value; prices: rows of
    {date, symbol, close, turnover, turnover_est} (one per share and session, daily rows preferred); tri: symbol ->
    {date: total-return index} (cse_total_returns)."""

    def __init__(self, sessions: list[str], aspi: dict[str, float], prices: list[dict], tri: dict[str, dict]):
        self.sessions = sorted(sessions)
        self.aspi = pd.Series(aspi, dtype=float).sort_index()
        frame = pd.DataFrame(prices, columns=["date", "symbol", "close", "turnover", "turnover_est"])
        self.by_sym = {s: g.drop(columns="symbol").set_index("date").sort_index()
                       for s, g in frame.groupby("symbol")}
        self.tri = {s: pd.Series(v, dtype=float).sort_index() for s, v in tri.items() if v}
        self._weekly_turnover: dict[tuple[str, str, str], float] = {}
        self._turnover: dict[str, tuple[pd.Series, pd.Series]] = {}

    def sessions_to(self, session: str) -> list[str]:
        return [s for s in self.sessions if s <= session]

    def weeks_all(self, session: str) -> list[str]:
        """Old all_wednesdays: every Wednesday from the first session to this one."""
        return wednesdays(self.sessions[0], session) if self.sessions else []

    def turnover(self, symbol: str) -> tuple[pd.Series, pd.Series]:
        if symbol not in self._turnover:
            self._turnover[symbol] = daily_turnover(self.by_sym[symbol])
        return self._turnover[symbol]

    def weekly_turnover(self, symbol: str, weeks: list[str]) -> pd.Series:
        """Old weekly_sum(daily_turnover(hist)[0], weeks), each week computed once per share."""
        to, _ = self.turnover(symbol)
        out = {}
        for w0, w1 in zip(weeks, weeks[1:]):
            k = (symbol, w0, w1)
            if k not in self._weekly_turnover:
                self._weekly_turnover[k] = float(to[(to.index > w0) & (to.index <= w1)].sum())
            out[w1] = self._weekly_turnover[k]
        return pd.Series(out)


# --- old cse/estimates.py -----------------------------------------------------------------------------------------

def daily_turnover(hist: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Real turnover where present, otherwise the close x volume estimate (old decision D2)."""
    real = pd.to_numeric(hist["turnover"], errors="coerce")
    est = pd.to_numeric(hist["turnover_est"], errors="coerce")
    return real.fillna(est), real.notna()


def select_universe(securities: list[Security], h: History, sectors: dict[str, str | None], excluded: set[str],
                    cfg: dict, session: str, weeks_all: list[str]) -> Universe:
    """Apply the filters in order and record a reason for every security left out (old select_universe)."""
    window_start = (dt.date.fromisoformat(session) - dt.timedelta(weeks=52)).isoformat()
    win = [s for s in h.sessions if window_start < s <= session]
    dropped, keep, stats = [], [], []
    for sec in sorted(securities, key=lambda s: s.symbol):
        sym = sec.symbol
        if not sym.endswith(EQUITY_SUFFIXES):
            kind = SUFFIX_KIND.get(sym.split(".")[1][0] if "." in sym else "", "not an ordinary share")
            dropped.append({"symbol": sym, "name": sec.name, "reason": f"not an ordinary share ({kind})"})
            continue
        hist = h.by_sym.get(sym)
        tri = h.tri.get(sym)
        n_weeks = 0
        if tri is not None:
            n_weeks = int(weekly_returns(tri, weeks_all).notna().sum())
        traded = hist.index.isin(win).sum() / len(win) if hist is not None and win else 0.0
        if hist is not None:
            to, is_real = h.turnover(sym)
            med = float(to.reindex(win).fillna(0).median()) if win else 0.0
            real_share = float(is_real.reindex(win).fillna(False).mean()) if win else 0.0
        else:
            med, real_share = 0.0, 0.0
        stats.append({"symbol": sym, "weeks": n_weeks, "traded_share": traded, "median_turnover": med,
                      "real_turnover_share": real_share, "sector": sectors.get(sym)})
        reason = None
        if sym in excluded:
            reason = EXCLUDED_REASON
        elif n_weeks < cfg["min_history_weeks"]:
            reason = f"history {n_weeks} weeks < {cfg['min_history_weeks']}"
        elif traded < cfg["min_traded_share"]:
            reason = f"traded on {traded:.0%} of sessions < {cfg['min_traded_share']:.0%}"
        elif med < cfg["min_median_turnover_lkr"]:
            reason = f"median daily turnover Rs {med / 1e6:.2f} mn < Rs {cfg['min_median_turnover_lkr'] / 1e6:.2f} mn"
        elif not sectors.get(sym):
            reason = "sector unclassified (add it to config/sector_overrides.yaml)"
        if reason:
            dropped.append({"symbol": sym, "name": sec.name, "reason": reason})
        else:
            keep.append(sym)
    return Universe(keep, dropped, pd.DataFrame(stats).set_index("symbol") if stats else pd.DataFrame())


def dimson_beta(y: pd.Series, m: pd.Series) -> tuple[float, float, float]:
    """OLS of the excess share return on the current and the one-week-lagged excess market return.
    Returns (beta = b0 + b1, b0, b1)."""
    df = pd.DataFrame({"y": y, "m0": m, "m1": m.shift(1)}).dropna()
    X = np.column_stack([np.ones(len(df)), df["m0"], df["m1"]])
    coef, *_ = np.linalg.lstsq(X, df["y"].to_numpy(), rcond=None)
    return float(coef[1] + coef[2]), float(coef[1]), float(coef[2])


def returns_matrix(h: History, symbols: list[str], weeks: list[str]) -> pd.DataFrame:
    """The T x N weekly total returns over `weeks` (T + 1 Wednesdays), as the old estimate() built it."""
    return pd.DataFrame({s: weekly_returns(h.tri[s], weeks) for s in symbols})


def ledoit_wolf(R: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf covariance of the weekly returns (scikit-learn, default target), annualised by 52, and the
    shrinkage intensity."""
    lw = LedoitWolf().fit(R.to_numpy())
    return lw.covariance_ * 52, float(lw.shrinkage_)


def estimate(universe: Universe, h: History, sectors: dict[str, str], cfg: dict, session: str,
             weeks_all: list[str]) -> Estimates:
    """Old estimate(): weekly returns, covariance, Dimson beta, CAPM expected return, volatility, Amihud."""
    T = cfg["min_history_weeks"]
    weeks = weeks_all[-(T + 1):]                 # T returns need T + 1 Wednesdays
    syms = universe.symbols
    R = returns_matrix(h, syms, weeks)
    if R.isna().any().any():
        bad = R.columns[R.isna().any()].tolist()
        raise ValueError(f"incomplete weekly returns for {bad}")
    mkt = weekly_returns(h.aspi, weeks)
    rf_w = (1 + cfg["risk_free_annual"]) ** (1 / 52) - 1

    cov, shrinkage = ledoit_wolf(R)

    betas, parts = {}, []
    for s in syms:
        b, b0, b1 = dimson_beta(R[s] - rf_w, mkt - rf_w)
        betas[s] = b
        parts.append({"symbol": s, "b0": b0, "b1": b1})
    beta = pd.Series(betas)
    er = cfg["risk_free_annual"] + beta * cfg["equity_risk_premium"]

    amihud, med, src = {}, {}, {}
    for s in syms:
        wto = h.weekly_turnover(s, weeks) / 1e6
        ratio = (R[s].abs() / wto).replace([np.inf], np.nan)
        amihud[s] = float(ratio[wto > 0].mean())
        med[s] = float(universe.stats.loc[s, "median_turnover"])
        rs = universe.stats.loc[s, "real_turnover_share"]
        src[s] = "real" if rs >= 0.999 else ("estimated" if rs == 0 else "mixed")
    return Estimates(
        session=session, weeks=weeks[1:], symbols=syms, sectors={s: sectors[s] for s in syms},
        returns=R, market=mkt, cov=cov, shrinkage=shrinkage, beta=beta,
        beta_parts=pd.DataFrame(parts).set_index("symbol"), er=er,
        vol=pd.Series(np.sqrt(np.diag(cov)), index=syms), amihud=pd.Series(amihud),
        median_turnover=pd.Series(med), turnover_source=pd.Series(src), rf=cfg["risk_free_annual"],
    )


def max_weeks(universe: Universe) -> int:
    return int(universe.stats["weeks"].max()) if not universe.stats.empty else 0


@dataclass
class Outcome:
    """One estimate date: the universe, and the estimates when there are any (preview: on the longest history
    available, because the full one is not there yet; the old lab's preview, never used for a record)."""
    session: str
    status: str                                  # ok | waiting
    message: str
    universe: Universe
    estimates: Estimates | None = None
    preview_weeks: int | None = None
    preview_universe: Universe | None = None
    extra: dict = field(default_factory=dict)


PREVIEW_MIN_WEEKS = 26


def run_date(h: History, securities: list[Security], sectors: dict[str, str | None], excluded: set[str],
             cfg: dict, session: str, preview_min_weeks: int | None = PREVIEW_MIN_WEEKS) -> Outcome:
    """Old lab.run() up to the estimates, for one session: the universe; if it has two shares or more, the estimates;
    otherwise "waiting", with a preview on the longest history available when that is at least preview_min_weeks
    weekly returns (None: no preview)."""
    weeks_all = h.weeks_all(session)
    universe = select_universe(securities, h, sectors, excluded, cfg, session, weeks_all)
    if len(universe.symbols) >= 2:
        est = estimate(universe, h, sectors, cfg, session, weeks_all)
        return Outcome(session, "ok", f"{len(universe.symbols)} stocks, {len(est.weeks)} weekly returns",
                       universe, est)
    longest, need = max_weeks(universe), cfg["min_history_weeks"]
    out = Outcome(session, "waiting", f"universe has {len(universe.symbols)} stocks: the longest history is {longest} "
                                      f"weekly returns and {need} are required.", universe)
    if preview_min_weeks is not None and longest >= preview_min_weeks:
        pcfg = {**cfg, "min_history_weeks": longest}
        puni = select_universe(securities, h, sectors, excluded, pcfg, session, weeks_all)
        out.preview_weeks, out.preview_universe = longest, puni
        if len(puni.symbols) >= 2:
            out.estimates = estimate(puni, h, sectors, pcfg, session, weeks_all)
    return out
