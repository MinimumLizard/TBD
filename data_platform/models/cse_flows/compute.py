"""cse_flows: where the directors' money moved, per company and per account, over 30, 90 and 365 days (audit C19,
the dealings half of the old terminal's "Money flows" page).

Version 1 ports MinimumLizard/CSE@e05c6f3 cse/flows.py build(): the per-actor and per-company tables, the counts and
the per-dealing flags; only names and comments are reworded, and the old labels for the two sides are the neutral
`purchase` and `disposal`. The arithmetic is unchanged, including the order in which values are added up.

What differs from the old page, and why (METHOD.md):
  * point in time: the old page was computed once, as of its latest dealing date. Here every dealing date D gets
    its own rows, from the dealings dated on or before D, so a row for D never changes when later dealings arrive
    (only when a notice dated D or earlier arrives late, or a re-filing replaces one). The latest D is the old page;
  * the quarter-to-quarter top-20 list changes (audit C20), the "own group" flag and the actors' group labels need
    the ownership facts, which the platform does not have yet; the "watchlist" flag was the old owner's personal
    list. All four are left out;
  * the old page showed the top 60 actors and top 40 companies; every row is stored here.

Outputs: models.cse_flow_company, models.cse_flow_summary and models.cse_flow_dealing (no names), and
models.cse_flow_actor (account names; unpublished).
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import statistics
from collections import defaultdict

from . import entities

WINDOWS = (30, 90, 365)
LARGE_LKR = 10_000_000
TOP_CODES = 6


def _f(x) -> float:
    return float(x) if x not in (None, "") else 0.0


def _iso(d: dt.date | None) -> str:
    """Dates as the old CSV's text ('' when missing), so rows sort as the old file did."""
    return d.isoformat() if d else ""


class Lists:
    """The CSE's security lists: for a date, the latest list on or before it (before the first list: the first)."""

    def __init__(self, rows: list[dict]):
        by: dict[dt.date, list[dict]] = defaultdict(list)
        for r in rows:
            by[r["session_date"]].append(r)
        self.dates = sorted(by)
        self._rows = by
        self._markets: dict[dt.date, entities.Market] = {}

    def market(self, day: dt.date | None) -> entities.Market:
        if not self.dates:
            return entities.Market({}, {})
        i = bisect.bisect_right(self.dates, day) - 1 if day else len(self.dates) - 1
        d = self.dates[max(i, 0)]
        if d not in self._markets:
            self._markets[d] = entities.market(self._rows[d])
        return self._markets[d]


def deals(dealings: list[dict], filed: dict[str, dict], lists: Lists) -> list[dict]:
    """The counted transactions (re-filed notices left out), in the old CSV's order, each with the account that dealt
    (old flows.dealings_rows). Each account is resolved against the security list in force on its dealing date."""
    out = []
    cache: dict[tuple, entities.Entity] = {}
    for r in dealings:
        f = filed[r["transaction_id"]]
        account = entities.account_name(f["account"], f["director"], r["company"])
        m = lists.market(r["deal_date"])
        key = (account, id(m))
        if key not in cache:
            cache[key] = entities.actor_entity(account, m)
        e = cache[key]
        out.append({**r, "actor_key": e.key, "actor": e.name, "actor_type": e.type, "value": _f(r["value"]),
                    "value_as_disclosed": r["value"],
                    "date": r["deal_date"].isoformat() if r["deal_date"] else ""})
    return out


def window(deals_: list[dict], end: dt.date, days: int) -> list[dict]:
    """Purchases and disposals dated in (end - days, end]."""
    start, last = (end - dt.timedelta(days=days)).isoformat(), end.isoformat()
    return [d for d in deals_ if d["date"] and start < d["date"] <= last and d["side"] in ("purchase", "disposal")]


def per_actor(rows: list[dict]) -> list[dict]:
    """Old build(): per account, purchases, disposals, net, transactions and the net by company (largest six)."""
    per: dict[str, dict] = {}
    for d in rows:
        a = per.setdefault(d["actor_key"], {"key": d["actor_key"], "name": d["actor"], "type": d["actor_type"],
                                            "purchases": 0.0, "disposals": 0.0, "n": 0, "codes": defaultdict(float)})
        v = d["value"] if d["side"] == "purchase" else -d["value"]
        a["purchases" if v > 0 else "disposals"] += abs(v)
        a["n"] += 1
        a["codes"][d["symbol"]] += v
    for a in per.values():
        a["net"] = a["purchases"] - a["disposals"]
        a["codes"] = dict(sorted(a["codes"].items(), key=lambda kv: -abs(kv[1]))[:TOP_CODES])
    return sorted(per.values(), key=lambda a: -abs(a["net"]))


def per_company(rows: list[dict]) -> list[dict]:
    """Old build(): per company, purchases, disposals, net, the distinct accounts on each side (one entry per
    account, not per spelling) and the cluster flag: two or more distinct purchasers and net purchases above zero."""
    per: dict[str, dict] = {}
    for d in rows:
        c = per.setdefault(d["symbol"], {"symbol": d["symbol"], "company": d["company"], "purchases": 0.0,
                                         "disposals": 0.0, "purchasers": {}, "disposers": {}, "n": 0})
        if d["side"] == "purchase":
            c["purchases"] += d["value"]
            c["purchasers"].setdefault(d["actor_key"], d["actor"])
        else:
            c["disposals"] += d["value"]
            c["disposers"].setdefault(d["actor_key"], d["actor"])
        c["n"] += 1
    for c in per.values():
        c["net"] = c["purchases"] - c["disposals"]
        c["cluster"] = len(c["purchasers"]) >= 2 and c["net"] > 0
        c["purchasers"], c["disposers"] = sorted(c["purchasers"].values()), sorted(c["disposers"].values())
    return sorted(per.values(), key=lambda c: -abs(c["net"]))


def summary(deals_: list[dict], end: dt.date) -> dict:
    """Old build(): how many dealings (any side) and trades (purchases and disposals), and the median lag."""
    known = [d for d in deals_ if d["date"] and d["date"] <= end.isoformat()]
    lags = [float(d["lag_days"]) for d in known if d["lag_days"] not in ("", None)]
    return {"n_dealings": len(known), "n_trades": sum(1 for d in known if d["side"] in ("purchase", "disposal")),
            "lag_median": statistics.median(lags) if lags else None}


def flags(d: dict, large_lkr: float = LARGE_LKR) -> dict:
    """Old build()'s feed flags that need no ownership facts or watchlist: large (Rs 10 mn or more) and related
    account."""
    return {"large": d["value"] >= large_lkr, "related_account": d["account_type"] == "related"}


# --- inputs ------------------------------------------------------------------------------------------------------

DEALING_COLUMNS = ("transaction_id, announcement_id, line_no, symbol, company, account_type, trade_date, deal_date, "
                   "side, value, announced_date, lag_days, superseded_by")


def inputs_of(inputs, as_of: dt.date | None) -> tuple[list[dict], dict[str, dict], Lists]:
    """The counted transactions of cse_dealings (as the old CSV: re-filed notices left out), their accounts as filed,
    and the security lists. With as_of: only notices announced on or before it, and a re-filing counts only if it was
    announced by then too."""
    rows = inputs.rows("models.cse_dealing", DEALING_COLUMNS)
    announced = {r["announcement_id"]: r["announced_date"] for r in rows}
    known = (lambda d: d is not None and d <= as_of) if as_of else (lambda d: True)
    rows = [r for r in rows if known(r["announced_date"])
            and not (r["superseded_by"] is not None and known(announced.get(r["superseded_by"])))]
    rows.sort(key=lambda r: (_iso(r["deal_date"]), _iso(r["announced_date"]), r["announcement_id"], r["line_no"]))
    filed = {r["transaction_id"]: r for r in inputs.rows("models.cse_dealing_as_filed",
                                                          "transaction_id, director, account")}
    lists = Lists(inputs.rows("cse.security_list", "session_date, symbol, name",
                              where="session_date <= %s" if as_of else "", params=(as_of,) if as_of else (),
                              order_by="session_date, symbol"))
    if as_of and not lists.dates:      # before the first stored list: the first list, as for corporate actions
        lists = Lists(inputs.rows("cse.security_list", "session_date, symbol, name",
                                  where="session_date = (select min(session_date) from cse.security_list)",
                                  order_by="symbol"))
    return rows, filed, lists


def compute(inputs, as_of):
    windows = tuple(inputs.params.get("windows_days", WINDOWS))
    large = float(inputs.params.get("large_lkr", LARGE_LKR))
    rows, filed, lists = inputs_of(inputs, as_of)
    all_deals = deals(rows, filed, lists)
    days = sorted({d["deal_date"] for d in all_deals if d["deal_date"]})
    if as_of:
        days = [d for d in days if d <= as_of]
    company, actor, summ = [], [], []
    for end in days:
        summ.append({"as_of": end, **summary(all_deals, end)})
        for w in windows:
            rows_w = window(all_deals, end, w)
            for c in per_company(rows_w):
                company.append({"as_of": end, "window_days": w, "symbol": c["symbol"], "company": c["company"],
                                "purchase_value": c["purchases"], "disposal_value": c["disposals"],
                                "net_value": c["net"], "n_purchasers": len(c["purchasers"]),
                                "n_disposers": len(c["disposers"]), "n_transactions": c["n"],
                                "cluster": c["cluster"]})
            for a in per_actor(rows_w):
                actor.append({"as_of": end, "window_days": w, "actor_key": a["key"], "actor": a["name"],
                              "actor_type": a["type"], "purchase_value": a["purchases"],
                              "disposal_value": a["disposals"], "net_value": a["net"], "n_transactions": a["n"],
                              "companies": json.dumps([[k, v] for k, v in a["codes"].items()])})
    dealing = [{"transaction_id": d["transaction_id"], "symbol": d["symbol"], "deal_date": d["deal_date"],
                "side": d["side"], "value": d["value_as_disclosed"], "actor_type": d["actor_type"], **flags(d, large)}
               for d in all_deals if not as_of or (d["deal_date"] and d["deal_date"] <= as_of)]
    return {"models.cse_flow_company": company, "models.cse_flow_summary": summ, "models.cse_flow_dealing": dealing,
            "models.cse_flow_actor": actor}
