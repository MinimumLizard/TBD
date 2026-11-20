"""Checks every stored row of the portfolio lab against the rules it claims to follow (the owner asked for a bug hunt,
2026-11-20). For the owner and for tests; reads the database, writes nothing.

    python -m data_platform.jobs.lab_audit [--backtest 1.1.0] [--lab 1.2.0] [--record 1.2.0]

What is checked, for each version named:

  walk-forward test (cse_lab_backtest)
    B1  every set of model weights sums to 1, and no weight is above its cap or below its floor
    B2  no sector is above 30 % and no ownership group above 20 % of a set of model weights
    B3  every trade's value is shares x price, its cost is the cost per side x its value, shares are whole
    B4  rebuilt from the trades alone, the cash after each session equals the cash stored, and the shares held
        valued at that session's prices (the record's own Pricer) plus the cash equal the value stored
    B5  the number of names stored is the number of shares held
    B6  treasury bills never lose value; the market's value moves exactly with the ASPI
    B7  a scheduled rebalance falls on the first session of January, April, July or October, and a threshold
        rebalance only under the dynamic policy, past its threshold or after a share left the universe
    B8  each summary's return and costs agree with the values and trades stored
  model portfolios (cse_portfolio_lab)
    L1  every formed portfolio's weights sum to 1, within its caps and floor; its sector and group totals within theirs
  forward record (cse_lab_record)
    R1  every holding's value is shares x price; holdings plus cash equal the value stored

Each check returns the rows that fail it; none should.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
from collections import defaultdict

from ..core import db, settings as settings_mod
from ..models import registry
from ..models._lib import cse_record as rec

TOL = 1e-6


def q(conn, sql: str, *params) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def market(conn) -> tuple[list[str], dict, dict, list[dict]]:
    """The ASPI calendar and values, every share's closes and the corporate actions in use, as the models read them."""
    aspi = {r["session_date"].isoformat(): r["value"] for r in q(
        conn, "select session_date, value from cse.indices_daily_current where index_code = 'ASI'")}
    closes: dict[str, dict[str, float]] = defaultdict(dict)
    for r in q(conn, "select session_date, symbol, close from cse.prices_daily_current"):
        closes[r["symbol"]][r["session_date"].isoformat()] = r["close"]
    actions = [{"symbol": a["symbol"], "type": a["action_type"], "ex_date": a["ex_date"].isoformat(),
                "amount_per_share": a["amount_per_share"], "ratio_new": a["ratio_new"], "ratio_held": a["ratio_held"],
                "factor": a["factor"], "subscription_price": a["subscription_price"]}
               for a in q(conn, """select symbol, action_type, ex_date, amount_per_share, ratio_new, ratio_held, factor,
                                  subscription_price from models.cse_corporate_action_used
                                  where method_version = '1.0.0' and ex_date is not null order by ex_date, action_id""")]
    return sorted(aspi), aspi, dict(closes), actions


def cap_floor(portfolio: str, max_weight: float) -> tuple[float, float | None]:
    kind, k = portfolio.rsplit("_", 1)
    k = int(k)
    return max(max_weight, 1.5 / k), (None if kind == "equal_weight" else 0.5 / k)


def check_backtest(conn, version: str, facts) -> dict[str, list]:
    p = registry.load_all()["cse_lab_backtest"].version(version).parameters
    sessions, aspi, closes, actions = facts
    fails: dict[str, list] = defaultdict(list)
    # B1, B2: the model weights
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in q(conn, "select * from models.cse_bt_target where method_version = %s", version):
        groups[(r["as_of"], r["policy"], r["portfolio"], r["today"])].append(r)
    for key, rows in groups.items():
        cap, floor = cap_floor(key[2], p["max_weight"])
        total = sum(r["weight"] for r in rows)
        if abs(total - 1) > TOL:
            fails["B1 weights sum to 1"].append((key, total))
        k = int(key[2].rsplit("_", 1)[1])
        if len(rows) != k:
            fails["B1 K names"].append((key, len(rows)))
        for r in rows:
            if key[2].startswith("equal_weight"):
                if abs(r["weight"] - 1 / k) > TOL:
                    fails["B1 equal weight is 1/K"].append((key, r["symbol"], r["weight"]))
                continue
            if r["weight"] > cap + TOL:
                fails["B1 within the cap"].append((key, r["symbol"], r["weight"], cap))
            if floor is not None and r["weight"] < floor - TOL:
                fails["B1 above the floor"].append((key, r["symbol"], r["weight"], floor))
        if not key[2].startswith("equal_weight"):
            by_sector, by_group = defaultdict(float), defaultdict(float)
            for r in rows:
                by_sector[r["sector"]] += r["weight"]
                by_group[r["group_key"]] += r["weight"]
            for s, w in by_sector.items():
                if w > p["max_sector_weight"] + TOL:
                    fails["B2 sector within 30 %"].append((key, s, w))
            for g, w in by_group.items():
                if w > p["max_group_weight"] + TOL:
                    fails["B2 group within 20 %"].append((key, g, w))
    # B3: trades
    trades = q(conn, "select * from models.cse_bt_trade where method_version = %s order by session_date, seq", version)
    for t in trades:
        if t["action"] in (rec.INCREASE, rec.DECREASE):
            if abs(t["value"] - t["shares"] * t["price"]) > 1e-6 * max(1, t["value"]):
                fails["B3 value = shares x price"].append((t["session_date"], t["portfolio"], t["symbol"]))
            if abs(t["cost"] - p["cost_per_side"] * t["value"]) > 1e-6 * max(1, t["value"]):
                fails["B3 cost = cost per side x value"].append((t["session_date"], t["portfolio"], t["symbol"],
                                                                 t["cost"], t["value"]))
            if t["shares"] != math.floor(t["shares"]) or t["shares"] <= 0:
                fails["B3 whole shares"].append((t["session_date"], t["portfolio"], t["symbol"], t["shares"]))
        elif t["cost"] != 0:
            fails["B3 no cost on corporate actions"].append((t["session_date"], t["portfolio"], t["symbol"]))
    # B4, B5, B6: rebuild every book from its trades and revalue it
    by_book: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        by_book[(t["policy"], t["portfolio"])].append(t)
    navs: dict[tuple, list[dict]] = defaultdict(list)
    for r in q(conn, "select * from models.cse_bt_nav where method_version = %s order by session_date", version):
        navs[(r["policy"], r["portfolio"])].append(r)
    notional = float(p["record_notional_lkr"])
    for book, rows in navs.items():
        if book[1] in ("market", "bills"):
            vals = [r["nav"] for r in rows]
            if book[1] == "bills" and any(b < a - TOL for a, b in zip(vals, vals[1:])):
                fails["B6 bills never fall"].append(book)
            if book[1] == "market":
                first = rows[0]
                for r in rows:
                    want = notional / aspi[first["session_date"].isoformat()] * aspi[r["session_date"].isoformat()]
                    if abs(r["nav"] - want) > 1e-6 * want:
                        fails["B6 market follows the ASPI"].append((book, r["session_date"]))
                        break
            continue
        shares: dict[str, float] = defaultdict(float)
        cash = notional
        ts = by_book.get(book, [])
        i = 0
        for r in rows:
            day = r["session_date"]
            while i < len(ts) and ts[i]["session_date"] <= day:
                t = ts[i]
                if t["action"] == rec.INCREASE:
                    shares[t["symbol"]] += t["shares"]
                    cash -= t["value"] + t["cost"]
                elif t["action"] == rec.DECREASE:
                    shares[t["symbol"]] -= t["shares"]
                    cash += t["value"] - t["cost"]
                elif t["action"] == "dividend":
                    cash += t["value"]
                elif t["action"] in ("subdivision", "scrip"):
                    shares[t["symbol"]] += t["shares"]
                elif t["action"] == "rights":
                    shares[t["symbol"]] += t["shares"]
                    cash -= t["value"]
                i += 1
            if abs(cash - r["cash"]) > 1e-4:
                fails["B4 cash rebuilt from the trades"].append((book, day, round(cash, 4), round(r["cash"], 4)))
                break
            if cash < -1e-6:
                fails["B4 cash never negative"].append((book, day, cash))
            pricer = rec.Pricer(closes, actions, day.isoformat())
            value = cash + sum(n * (pricer.price(s) or 0.0) for s, n in shares.items())
            if abs(value - r["nav"]) > 1e-4 * max(1, r["nav"]) * 1e-3:
                fails["B4 value rebuilt from the trades and prices"].append((book, day, round(value, 2), round(r["nav"], 2)))
                break
            held = sum(1 for n in shares.values() if n > 0)
            if r["n_names"] is not None and held != r["n_names"]:
                fails["B5 names held"].append((book, day, held, r["n_names"]))
                break
    # B7: when rebalances happen
    for e in q(conn, "select * from models.cse_bt_event where method_version = %s", version):
        s = e["session_date"].isoformat()
        if e["kind"] == "scheduled" and not rec.is_scheduled(s, sessions, p["rebalance_months"]):
            fails["B7 scheduled only on review dates"].append((e["policy"], e["portfolio"], s))
        if e["kind"] == "threshold" and not (e["policy"] == "dynamic" and (
                e["left_universe"] or (e["tracking_error"] or 0) > p["te_threshold"])):
            fails["B7 threshold only past the threshold"].append((e["policy"], e["portfolio"], s))
    # B8: the summaries
    for srow in q(conn, "select * from models.cse_bt_summary where method_version = %s", version):
        rows = navs[(srow["policy"], srow["portfolio"])]
        ret = rows[-1]["nav"] / rows[0]["nav"] - 1
        if abs(ret - srow["total_return"]) > 1e-9:
            fails["B8 summary return"].append((srow["policy"], srow["portfolio"], ret, srow["total_return"]))
        if srow["costs"] is not None:
            cost = sum(t["cost"] for t in by_book.get((srow["policy"], srow["portfolio"]), []))
            if abs(cost - srow["costs"]) > 1e-6:
                fails["B8 summary costs"].append((srow["policy"], srow["portfolio"], cost, srow["costs"]))
    return fails


def check_lab(conn, version: str) -> dict[str, list]:
    p = registry.load_all()["cse_portfolio_lab"].version(version).parameters
    fails: dict[str, list] = defaultdict(list)
    ports = {(r["as_of"], r["portfolio"]): r for r in q(
        conn, "select * from models.cse_lab_portfolio where method_version = %s", version)}
    weights: dict[tuple, list[dict]] = defaultdict(list)
    for w in q(conn, "select * from models.cse_lab_weight where method_version = %s", version):
        weights[(w["as_of"], w["portfolio"])].append(w)
    for key, ws in weights.items():
        port = ports.get(key)
        if port is None or port["status"] != "ok":
            continue
        total = sum(w["weight"] for w in ws)
        if abs(total - 1) > TOL:
            fails["L1 weights sum to 1"].append((key, total))
        if port["family"] == "fewer_names" and not key[1].startswith("equal_weight"):
            cap, floor = cap_floor(key[1], p["max_weight"])
            for w in ws:
                if w["weight"] > cap + TOL or (floor and w["weight"] < floor - TOL):
                    fails["L1 within cap and floor"].append((key, w["symbol"], w["weight"]))
        if port["family"] == "full" and key[1] != "equal_weight":
            for w in ws:
                if w["cap"] is not None and w["weight"] > w["cap"] + TOL:
                    fails["L1 within the cap"].append((key, w["symbol"], w["weight"], w["cap"]))
            if port["constraints_ok"] is False:
                fails["L1 constraint report"].append(key)
    return fails


def check_record(conn, version: str) -> dict[str, list]:
    fails: dict[str, list] = defaultdict(list)
    navs = {(r["series"], r["session_date"], r["portfolio"]): r for r in q(
        conn, "select * from models.cse_lab_nav where method_version = %s", version)}
    held: dict[tuple, float] = defaultdict(float)
    for h in q(conn, "select * from models.cse_lab_holding where method_version = %s", version):
        if h["price"] is not None and abs(h["shares"] * h["price"] - h["value"]) > 1e-6 * max(1, h["value"]):
            fails["R1 value = shares x price"].append((h["session_date"], h["portfolio"], h["symbol"]))
        held[(h["series"], h["session_date"], h["portfolio"])] += h["value"] or 0.0
    for key, n in navs.items():
        if n["portfolio"] == "market":
            continue
        if abs(held.get(key, 0.0) + n["cash"] - n["nav"]) > 1e-4:
            fails["R1 holdings + cash = value"].append((key, held.get(key, 0.0) + n["cash"], n["nav"]))
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backtest", nargs="*", default=None)
    ap.add_argument("--lab", nargs="*", default=None)
    ap.add_argument("--record", nargs="*", default=None)
    args = ap.parse_args(argv)
    manifests = registry.load_all()
    active = lambda name: [v.method_version for v in manifests[name].active_versions]  # noqa: E731
    conn = db.connect(settings_mod.load().database_url)
    facts = market(conn)
    report: dict[str, dict[str, list]] = {}
    for v in args.backtest if args.backtest is not None else active("cse_lab_backtest"):
        report[f"cse_lab_backtest {v}"] = check_backtest(conn, v, facts)
    for v in args.lab if args.lab is not None else active("cse_portfolio_lab"):
        report[f"cse_portfolio_lab {v}"] = check_lab(conn, v)
    for v in args.record if args.record is not None else active("cse_lab_record"):
        report[f"cse_lab_record {v}"] = check_record(conn, v)
    bad = 0
    for model, fails in report.items():
        n = sum(len(v) for v in fails.values())
        bad += n
        print(f"{model}: {'all checks pass' if not n else f'{n} failure(s)'}")
        for check, rows in sorted(fails.items()):
            print(f"  {check}: {len(rows)}; e.g. {rows[:3]}")
    print(f"checked at {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
