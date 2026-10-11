"""bond_liquidity: how much each bond has traded, and where it sits in the auction cycle, as of each day (audit B8).

Version 1 is the old tool's signals/liquidity.py (MinimumLizard/Nelson-Siegel@1c33084), ported line for line and
evaluated for every day that has a curve. Tiers:

  core    auctioned in the last 120 days (a current benchmark) and traded on at least 8 of the last 60 days
  active  traded on at least 10 of the last 60 days
  wider   quoted, rarely traded

Trading facts are counted to the last day whose trade file had been published (trade files arrive a day or more
after the quotes), unless that is more than 7 days old. Nothing uses information published after the day scored.
See METHOD.md.
"""
from __future__ import annotations

import datetime as dt

from .._lib import bond_workspace as ws

WINDOW_DAYS = 60
MIN_DAYS_TRADED = 10
BENCHMARK_MIN_DAYS = 8
BENCHMARK_DAYS = 120
POST_AUCTION_DAYS = 14
MAX_TRADE_DATA_LAG_DAYS = 7

EMPTY = {"turnover_lkr": 0, "n_trades": 0, "days_traded": 0, "is_benchmark": False, "last_auction": None,
         "days_since_auction": None, "post_auction": False, "bid_to_cover": None, "tier": "wider",
         "last_trade_date": None, "last_trade_yield": None, "days_since_trade": None, "trades_through": None,
         "trade_data_lag_days": None}


def last_complete_trade_day(conn, obs_date: str) -> str | None:
    """The newest day at or before obs_date whose trade file has published, unless it is over 7 days old."""
    row = conn.execute("""SELECT MAX(obs_date) AS d FROM trade_summary
                          WHERE security_type = 'TBond' AND obs_date <= ?""", (obs_date,)).fetchone()
    latest = row["d"] if row else None
    if not latest:
        return None
    lag = (dt.date.fromisoformat(obs_date) - dt.date.fromisoformat(latest)).days
    return latest if lag <= MAX_TRADE_DATA_LAG_DAYS else None


def profile(conn, obs_date: str) -> dict:
    """{isin: liquidity and auction facts} as of obs_date."""
    today = dt.date.fromisoformat(obs_date)
    benchmark_start = (today - dt.timedelta(days=BENCHMARK_DAYS)).isoformat()
    trades_through = last_complete_trade_day(conn, obs_date) or obs_date
    start = (dt.date.fromisoformat(trades_through) - dt.timedelta(days=WINDOW_DAYS)).isoformat()

    out: dict[str, dict] = {}
    for row in conn.execute(
            """SELECT isin, SUM(volume_lkr) AS turnover, SUM(n_trades) AS trades, COUNT(*) AS days_traded
                 FROM trade_summary
                WHERE obs_date > ? AND obs_date <= ? AND security_type = 'TBond'
                GROUP BY isin""", (start, trades_through)):
        out[row["isin"]] = dict(EMPTY, turnover_lkr=row["turnover"] or 0, n_trades=row["trades"] or 0,
                                days_traded=row["days_traded"] or 0)

    # >= on the lower bound: a bond auctioned exactly 120 days ago is still a benchmark (old liquidity.py).
    for row in conn.execute(
            """SELECT isin, MAX(auction_date) AS last_auction FROM auctions
                WHERE auction_date >= ? AND auction_date <= ?
                GROUP BY isin""", (benchmark_start, obs_date)):
        entry = out.setdefault(row["isin"], dict(EMPTY))
        since = (today - dt.date.fromisoformat(row["last_auction"])).days
        entry.update(is_benchmark=True, last_auction=row["last_auction"], days_since_auction=since,
                     post_auction=0 <= since <= POST_AUCTION_DAYS)

    for row in conn.execute(
            """SELECT isin, bids_lkr, offered_lkr FROM auctions
                WHERE kind = 'auction' AND bids_lkr IS NOT NULL
                  AND offered_lkr > 0 AND auction_date <= ?
                ORDER BY auction_date""", (obs_date,)):
        if row["isin"] in out:
            out[row["isin"]]["bid_to_cover"] = row["bids_lkr"] / row["offered_lkr"]

    for row in conn.execute(
            """SELECT isin, obs_date, wavg_yield FROM trade_summary
                WHERE security_type = 'TBond' AND wavg_yield IS NOT NULL
                  AND obs_date <= ? ORDER BY obs_date""", (obs_date,)):
        entry = out.setdefault(row["isin"], dict(EMPTY))
        entry.update(last_trade_date=row["obs_date"], last_trade_yield=row["wavg_yield"],
                     days_since_trade=(today - dt.date.fromisoformat(row["obs_date"])).days)

    for facts in out.values():
        facts["tier"] = tier(facts)
        facts["trades_through"] = trades_through
        facts["trade_data_lag_days"] = (today - dt.date.fromisoformat(trades_through)).days
    return out


def tier(facts: dict) -> str:
    if facts["is_benchmark"] and facts["days_traded"] >= BENCHMARK_MIN_DAYS:
        return "core"
    if facts["days_traded"] >= MIN_DAYS_TRADED:
        return "active"
    return "wider"


def build_workspace(inputs, as_of):
    conn = ws.open_workspace()
    day = ("obs_date <= %s", (as_of,)) if as_of else ("", ())
    auction_day = ("auction_date <= %s", (as_of,)) if as_of else ("", ())
    ws.load_trades(conn, inputs.rows("bonds.trades_current", where=day[0], params=day[1]))
    ws.load_auctions(conn, inputs.rows("bonds.auction_results_current", where=auction_day[0], params=auction_day[1]),
                     inputs.rows("bonds.auction_announcements_current", where=auction_day[0],
                                 params=auction_day[1]))
    return conn


def compute(inputs, as_of):
    day = ("obs_date <= %s", (as_of,)) if as_of else ("", ())
    dates = [r["obs_date"].isoformat() for r in inputs.rows("models.bond_curve_fit", "obs_date", where=day[0],
                                                             params=day[1], order_by="obs_date")]
    conn = build_workspace(inputs, as_of)
    rows = []
    for obs_date in dates:
        for isin, facts in sorted(profile(conn, obs_date).items()):
            rows.append({"obs_date": obs_date, "isin": isin, **facts})
    return {"models.bond_liquidity": rows}
