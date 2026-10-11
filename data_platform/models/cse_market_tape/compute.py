"""cse_market_tape: the market summary for each CSE session (audit C1, the old terminal's Panel A).

Version 1 ports the old CSE terminal's definitions (MinimumLizard/CSE@f263830 cse/metrics.py and cse/build.py):

- every index (headline, total return and sector) with its change, and change / previous value;
- market turnover, volume and trades against the mean of the previous 20 sessions of daily market data (the
  average needs 21 sessions; until then the number of sessions still needed is stored);
- foreign purchases, sales and net; the market's P/E, P/B, dividend yield and capitalisation as the CSE publishes
  them;
- breadth: ordinary voting and non-voting shares (.N0000 / .X0000) that traded, and how many closed up, down or
  unchanged on their previous close.

The old terminal computed this for its latest session only; version 1 computes it for every session in the
calendar (the days the ASPI has a value), from the stored facts. See METHOD.md.
"""
from __future__ import annotations

from collections import defaultdict

from .._lib.cse_calendar import ASPI, excluded_sessions, session_filter

AVG_SESSIONS = 20
EQUITY_SUFFIXES = (".N0000", ".X0000")


def pct_of_previous(value, change):
    if change is None or value is None:
        return None
    previous = value - change
    return change / previous if previous else None


def compute(inputs, as_of):
    skip = excluded_sessions(inputs)
    where, params = session_filter(as_of)
    indices = [r for r in inputs.rows("cse.indices_daily_current", "session_date, index_code, value, change",
                                      where=where, params=params, order_by="session_date, index_code")
               if r["session_date"] not in skip]
    # Not filtered by `skip`: the old terminal did capture the 2026-10-05 market summary; it missed only that
    # session's prices and index values.
    market = inputs.rows("cse.market_daily", where=" and ".join(filter(None, ["source = 'daily'", where])),
                         params=params, order_by="session_date")
    prices = [r for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, close, previous_close",
                                     where=where, params=params)
              if r["session_date"] not in skip and r["symbol"].endswith(EQUITY_SUFFIXES)]
    calendar = sorted({r["session_date"] for r in indices if r["index_code"] == ASPI})

    index_rows = [{"session_date": r["session_date"], "index_code": r["index_code"], "value": r["value"],
                   "change": r["change"], "pct": pct_of_previous(r["value"], r["change"])}
                  for r in indices if r["session_date"] in set(calendar)]

    by_session = defaultdict(list)
    for r in prices:
        by_session[r["session_date"]].append(r)
    market_by_date = {r["session_date"]: r for r in market}

    session_rows = []
    for session in calendar:
        daily = [r for r in market if r["session_date"] <= session]
        row = {"session_date": session}
        m = market_by_date.get(session)
        for column in ("turnover", "volume", "trades"):
            row[column] = m[column] if m else None
            row[f"{column}_avg20"] = (sum(r[column] for r in daily[-1 - AVG_SESSIONS:-1]) / AVG_SESSIONS
                                      if m and len(daily) >= AVG_SESSIONS + 1 else None)
        row["sessions_needed"] = max(AVG_SESSIONS + 1 - len(daily), 0) if m else None
        for column in ("foreign_buy", "foreign_sell", "per", "pbv", "dy", "market_cap", "listed"):
            row[column] = m[column] if m else None
        row["traded_all"] = m["traded"] if m else None
        row["foreign_net"] = (m["foreign_buy"] - m["foreign_sell"]) if m else None
        changes = [r["close"] - r["previous_close"] for r in by_session[session] if r["previous_close"] is not None]
        row.update(equities_up=sum(c > 0 for c in changes), equities_down=sum(c < 0 for c in changes),
                   equities_flat=sum(c == 0 for c in changes), equities_traded=len(by_session[session]))
        session_rows.append(row)
    return {"models.cse_market_session": session_rows, "models.cse_index_session": index_rows}
