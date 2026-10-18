"""cse_total_returns: each share's return with dividends, sub-divisions, scrip and rights issues taken into account
(audit C7, the old terminal's total-return index).

Version 1 ports MinimumLizard/CSE@f263830 cse/returns.py (total_returns, check_adjustment) and build_tris in
cse/estimates.py. For consecutive traded closes P0 -> P1, with every action in use (models.cse_corporate_action_used)
whose ex-date falls after the first close and on or before the second:

    F    = product of the share-count factors (sub-division, scrip)
    D    = sum of the cash dividends per share
    base = (n x P0 + m x S) / (n + m) if a rights issue of m new shares per n at price S goes ex (the theoretical
           ex-rights price), otherwise P0
    R    = (P1 x F + D x (1 - withholding)) / base - 1,      TRI = product of (1 + R), 1 at the first close

An action therefore applies on the first traded close on or after its ex-date. Prices are the CSE's own, which are
unadjusted; check_adjustment refuses to run when a large confirmed split or scrip issue does not show in the prices
(they would then be adjusted twice). New here: the price-only return, and the total return over 5, 21 and 63
sessions with the same windows as cse_security_metrics. See METHOD.md.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict

from .._lib.cse_calendar import ASPI, excluded_sessions, session_filter

EQUITY_SUFFIXES = (".N0000", ".X0000")
WINDOWS = {"1w": 5, "1m": 21, "3m": 63}


class AdjustmentMismatch(RuntimeError):
    """The price series contradicts the history_adjusted setting at a share-count event."""


def check_adjustment(dates: list, closes: list[float], actions: list[dict], history_adjusted: bool) -> None:
    """At every share-count event with factor >= 1.5, the close must drop by roughly the factor if prices are
    unadjusted, and must not drop if they are adjusted (old cse/returns.check_adjustment)."""
    for a in actions:
        f = a.get("factor")
        if a["type"] not in ("subdivision", "scrip") or not f or f < 1.5:
            continue
        before = [i for i, d in enumerate(dates) if d < a["ex_date"]]
        after = [i for i, d in enumerate(dates) if d >= a["ex_date"]]
        if not before or not after:
            continue
        raw = float(closes[after[0]]) / float(closes[before[-1]])
        # Log-distance to "dropped by f" against "did not drop": whichever is nearer wins.
        dropped = abs(math.log(raw) + math.log(f)) < abs(math.log(raw))
        if dropped and history_adjusted:
            raise AdjustmentMismatch(
                f"{a['symbol']} {a['type']} x{f:g} on {a['ex_date']}: raw close moved {raw:.3f}x "
                "(an unadjusted drop) but history_adjusted is true")
        if not dropped and not history_adjusted:
            raise AdjustmentMismatch(
                f"{a['symbol']} {a['type']} x{f:g} on {a['ex_date']}: raw close moved {raw:.3f}x, "
                "so prices already look adjusted; refusing to adjust them a second time")


def total_returns(dates: list, closes: list[float], actions: list[dict], withholding: float = 0.0,
                  history_adjusted: bool = False) -> list[dict]:
    """One row per traded close: the step's total return and its parts, and the TRI (1 at the first close).
    `dates` sorted, `actions` this share's actions in use, sorted by ex-date (old cse/returns.total_returns)."""
    out = [{"session_date": dates[0], "close": float(closes[0]), "price_return": None, "total_return": None,
            "share_factor": 1.0, "dividend": 0.0, "base_price": None, "events": "", "tri": 1.0}]
    tri = 1.0
    for j in range(1, len(dates)):
        t0, t1 = dates[j - 1], dates[j]
        p0, p1 = float(closes[j - 1]), float(closes[j])
        f, d, rights, applied = 1.0, 0.0, None, []
        for a in actions:
            if not (t0 < a["ex_date"] <= t1):
                continue
            if a["type"] == "cash_dividend" and a.get("amount_per_share"):
                d += a["amount_per_share"]
                applied.append(f"div {a['amount_per_share']:g}")
            elif a["type"] in ("subdivision", "scrip") and a.get("factor") and not history_adjusted:
                f *= a["factor"]
                applied.append(f"{a['type']} ×{a['factor']:.6g}")
            elif a["type"] == "rights" and not history_adjusted:
                rights = a
                applied.append(f"rights {a['ratio_new']:g}:{a['ratio_held']:g} @ {a['subscription_price']:g}")
        base = p0
        if rights is not None:
            n, m, s = rights["ratio_held"], rights["ratio_new"], rights["subscription_price"]
            base = (n * p0 + m * s) / (n + m)
        r = (p1 * f + d * (1 - withholding)) / base - 1
        tri *= 1 + r
        out.append({"session_date": t1, "close": p1, "price_return": p1 / p0 - 1, "total_return": r,
                    "share_factor": f, "dividend": d, "base_price": base, "events": "; ".join(applied), "tri": tri})
    return out


def compute(inputs, as_of):
    withholding = float(inputs.params.get("dividend_withholding", 0.0))
    history_adjusted = bool(inputs.params.get("history_adjusted", False))
    skip = excluded_sessions(inputs)
    where, params = session_filter(as_of)

    calendar = sorted({r["session_date"] for r in inputs.rows(
        "cse.indices_daily_current", "session_date", where=" and ".join(filter(None, ["index_code = %s", where])),
        params=(ASPI, *params))} - skip)
    position = {d: i for i, d in enumerate(calendar)}

    closes: dict[str, dict] = defaultdict(dict)
    for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, close",
                         where=" and ".join(filter(None, ["right(symbol, 6) in ('.N0000', '.X0000')", where])),
                         params=params):
        if r["session_date"] not in skip:
            closes[r["symbol"]][r["session_date"]] = r["close"]
    actions: dict[str, list[dict]] = defaultdict(list)
    for a in inputs.rows("models.cse_corporate_action_used",
                         "action_id, symbol, action_type, ex_date, amount_per_share, ratio_new, ratio_held, factor, "
                         "subscription_price", order_by="ex_date, action_id"):
        actions[a["symbol"]].append({**a, "type": a["action_type"]})

    rows = []
    for symbol in sorted(closes):
        dates = sorted(closes[symbol])
        series = [closes[symbol][d] for d in dates]
        acts = actions.get(symbol, [])
        check_adjustment(dates, series, acts, history_adjusted)
        steps = total_returns(dates, series, acts, withholding, history_adjusted)
        tris = [s["tri"] for s in steps]
        for s in steps:
            i = position.get(s["session_date"])
            for label, k in WINDOWS.items():
                s[f"tr_{label}"] = None
                if i is None or i < k:
                    continue
                j = bisect_right(dates, calendar[i - k]) - 1
                if j >= 0:
                    s[f"tr_{label}"] = s["tri"] / tris[j] - 1
            rows.append({"symbol": symbol, **s})
    return {"models.cse_total_return": rows}
