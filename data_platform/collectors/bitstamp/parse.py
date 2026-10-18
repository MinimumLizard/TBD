"""Bitstamp's daily candles: pure functions, bytes in, rows out. No network, no database.

The endpoint (https://www.bitstamp.net/api/ , "OHLC data"):
    GET /api/v2/ohlc/{pair}/?step=86400&limit=1000&start=<unix seconds>
answers {"data": {"pair": "BTC/USD", "ohlc": [{"timestamp": "1315958400", "open": "5.58", ...}, ...]}}.

What was measured on 2026-10-18 (and is relied on here):
  * each daily candle's timestamp is the start of its UTC day (a multiple of 86400);
  * the answer holds the candles whose timestamp lies in [start, start + limit x step): a window of days, not a count
    (ETH/USD from 2017-08-10 with limit 10 returned 4 candles, from its listing on 2017-08-16);
  * the window includes the current, unfinished day, whose figures keep changing until 24:00 UTC. It is never stored;
  * BTC/USD has a candle for every day from 2011-09-14, with no gaps.
"""
from __future__ import annotations

import datetime as dt
import json
import math

DAY_SECONDS = 86400
# A day's candle is treated as final only this long after its UTC day ends, so a trade booked a moment late can
# never leave a stored day different from Bitstamp's final figure.
SETTLE = dt.timedelta(minutes=10)

# The pairs collected: Bitstamp's url_symbol -> the name its API echoes. Majors with the longest Bitstamp history,
# plus ETH priced in bitcoin. Checked against /api/v2/trading-pairs-info/ on 2026-10-18.
PAIRS: dict[str, str] = {
    "btcusd": "BTC/USD",
    "ethusd": "ETH/USD",
    "xrpusd": "XRP/USD",
    "ltcusd": "LTC/USD",
    "solusd": "SOL/USD",
    "adausd": "ADA/USD",
    "linkusd": "LINK/USD",
    "dogeusd": "DOGE/USD",
    "avaxusd": "AVAX/USD",
    "dotusd": "DOT/USD",
    "ethbtc": "ETH/BTC",
}


class BitstampFormatError(ValueError):
    """The response is not what the collector was built for. Never guessed around: the run fails and says why."""


def _number(value, field: str, day: dt.date) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise BitstampFormatError(f"{day}: {field} is {value!r}, not a number") from None
    if not math.isfinite(x):
        raise BitstampFormatError(f"{day}: {field} is {value!r}")
    return x


def day_of(timestamp) -> dt.date:
    ts = int(timestamp)
    if ts % DAY_SECONDS:
        raise BitstampFormatError(f"timestamp {timestamp} is not the start of a UTC day")
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()


def unix(day: dt.date) -> int:
    return int(dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp())


def parse_ohlc(body: bytes, pair: str) -> list[dict]:
    """Every candle in one response, validated, oldest first: [{pair, day, open, high, low, close, volume}]."""
    try:
        doc = json.loads(body)
    except ValueError as exc:
        raise BitstampFormatError(f"{pair}: the response is not JSON ({exc})") from None
    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict) or "ohlc" not in data:
        raise BitstampFormatError(f"{pair}: no data.ohlc in the response: {str(doc)[:200]}")
    expected = PAIRS.get(pair)
    if expected is None:
        raise BitstampFormatError(f"{pair} is not one of the collected pairs")
    if data.get("pair") != expected:
        raise BitstampFormatError(f"{pair}: the response is for {data.get('pair')!r}, not {expected!r}")
    rows: list[dict] = []
    for candle in data["ohlc"]:
        day = day_of(candle["timestamp"])
        row = {"pair": pair, "day": day}
        for field in ("open", "high", "low", "close", "volume"):
            row[field] = _number(candle.get(field), field, day)
        if not (0 < row["low"] <= min(row["open"], row["close"]) and row["high"] >= max(row["open"], row["close"])):
            raise BitstampFormatError(f"{pair} {day}: inconsistent candle {row}")
        if row["volume"] < 0:
            raise BitstampFormatError(f"{pair} {day}: negative volume {row['volume']}")
        if rows and day <= rows[-1]["day"]:
            raise BitstampFormatError(f"{pair}: candles out of order at {day}")
        rows.append(row)
    return rows


def last_complete_day(now: dt.datetime) -> dt.date:
    """The latest UTC day whose candle is final at `now` (its day ended at least SETTLE ago)."""
    return (now.astimezone(dt.timezone.utc) - SETTLE).date() - dt.timedelta(days=1)


def complete(rows: list[dict], fetched_at: dt.datetime) -> list[dict]:
    """Only candles whose UTC day had ended (plus SETTLE) when the response was fetched."""
    until = last_complete_day(fetched_at)
    return [r for r in rows if r["day"] <= until]

