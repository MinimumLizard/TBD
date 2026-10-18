"""Bitstamp collector: parsers against real responses recorded on 2026-10-18 (tests/fixtures/bitstamp, a few
candles each), and the collector against a fake API that answers the way Bitstamp's does (no network)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import psycopg
import pytest

from data_platform.collectors.bitstamp import collector as bs
from data_platform.collectors.bitstamp import parse
from data_platform.core.collector import Context
from data_platform.core.http import Response

FIX = Path(__file__).parent / "fixtures" / "bitstamp"
UTC = dt.timezone.utc


def body(name: str) -> bytes:
    return (FIX / name).read_bytes()


# --- parsers ----------------------------------------------------------------------------------------------------

def test_the_first_candles_of_bitstamp_history():
    rows = parse.parse_ohlc(body("btcusd_2011-09-14.json"), "btcusd")
    assert [r["day"] for r in rows] == [dt.date(2011, 9, 14), dt.date(2011, 9, 15), dt.date(2011, 9, 16)]
    assert rows[0] == {"pair": "btcusd", "day": dt.date(2011, 9, 14), "open": 5.58, "high": 5.72, "low": 5.52,
                       "close": 5.53, "volume": 61.14598362}


def test_a_window_starting_before_a_listing_holds_only_the_listed_days():
    rows = parse.parse_ohlc(body("ethusd_2017-08-10_limit10.json"), "ethusd")
    assert rows[0]["day"] == dt.date(2017, 8, 16) and len(rows) == 4     # asked from 08-10: a window, not a count


def test_the_unfinished_day_is_never_kept():
    recorded_at = dt.datetime(2026, 10, 18, 7, 53, tzinfo=UTC)            # when the fixture was fetched
    rows = parse.parse_ohlc(body("btcusd_2026-10-16_with_current.json"), "btcusd")
    assert rows[-1]["day"] == dt.date(2026, 10, 18)                      # Bitstamp serves the current day too
    assert [r["day"] for r in parse.complete(rows, recorded_at)] == [dt.date(2026, 10, 16), dt.date(2026, 10, 17)]


def test_a_day_is_final_ten_minutes_after_midnight_utc():
    assert parse.last_complete_day(dt.datetime(2026, 10, 18, 0, 9, tzinfo=UTC)) == dt.date(2026, 10, 16)
    assert parse.last_complete_day(dt.datetime(2026, 10, 18, 0, 10, tzinfo=UTC)) == dt.date(2026, 10, 17)
    colombo = dt.timezone(dt.timedelta(hours=5, minutes=30))
    assert parse.last_complete_day(dt.datetime(2026, 10, 18, 5, 45, tzinfo=colombo)) == dt.date(2026, 10, 17)


def _doc(pair="BTC/USD", **candle):
    c = {"timestamp": "1315958400", "open": "5.58", "high": "5.72", "low": "5.52", "close": "5.53", "volume": "1"}
    c.update(candle)
    return json.dumps({"data": {"pair": pair, "ohlc": [c]}}).encode()


@pytest.mark.parametrize("doc, message", [
    (_doc(pair="ETH/USD"), "is for 'ETH/USD'"),
    (_doc(high="5.50"), "inconsistent candle"),
    (_doc(low="0"), "inconsistent candle"),
    (_doc(close="n/a"), "not a number"),
    (_doc(close="NaN"), "close is 'NaN'"),
    (_doc(volume="-1"), "negative volume"),
    (_doc(timestamp="1315958401"), "not the start of a UTC day"),
    (b'{"code": "400.002", "errors": [{"message": "Invalid pair"}]}', "no data.ohlc"),
    (b"<html>Just a moment...</html>", "not JSON"),
])
def test_anything_unexpected_is_refused_with_a_reason(doc, message):
    with pytest.raises(parse.BitstampFormatError, match=message):
        parse.parse_ohlc(doc, "btcusd")


def test_candles_must_be_in_order_and_the_pair_must_be_known():
    two = json.dumps({"data": {"pair": "BTC/USD", "ohlc": [
        {"timestamp": "1316044800", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"},
        {"timestamp": "1315958400", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}]}}).encode()
    with pytest.raises(parse.BitstampFormatError, match="out of order"):
        parse.parse_ohlc(two, "btcusd")
    with pytest.raises(parse.BitstampFormatError, match="not one of the collected pairs"):
        parse.parse_ohlc(_doc(), "xyzusd")


# --- the collector, against a fake API ---------------------------------------------------------------------------

class FakeBitstamp:
    """Answers like Bitstamp: the candles in [start, start + limit days), including the unfinished current day."""

    def __init__(self, listed: dict[str, dt.date], now: dt.datetime, silent: set[str] = frozenset()):
        self.listed, self.now, self.silent = listed, now, silent
        self.calls: list[tuple[str, dt.date]] = []

    def close(self, pair: str, day: dt.date) -> float:
        return 100.0 + (day - dt.date(2026, 1, 1)).days + (1000 if pair == "ethusd" else 0)

    def request(self, method, url, params=None):
        pair = url.rstrip("/").rsplit("/", 1)[-1]
        start = dt.datetime.fromtimestamp(params["start"], UTC).date()
        self.calls.append((pair, start))
        today = self.now.date()
        candles = []
        for k in range(params["limit"]):
            day = start + dt.timedelta(days=k)
            if day > today or day < self.listed[pair] or pair in self.silent:
                continue
            c = self.close(pair, day)
            candles.append({"timestamp": str(parse.unix(day)), "open": str(c), "high": str(c + 1), "low": str(c - 1),
                            "close": str(c), "volume": "2.5"})
        doc = {"data": {"pair": parse.PAIRS[pair], "ohlc": candles}}
        return Response(method, url, params, 200, json.dumps(doc).encode(), "application/json", self.now)


@pytest.fixture
def small_history(monkeypatch):
    """Two pairs, history from 2026-09-01, ten-day windows: every path of the collector in a few requests."""
    monkeypatch.setattr(bs, "HISTORY_START", dt.date(2026, 9, 1))
    monkeypatch.setattr(bs, "WINDOW_DAYS", 10)
    monkeypatch.setattr(bs.BitstampCollector, "pairs", ("btcusd", "ethusd"))
    return {"btcusd": dt.date(2026, 9, 1), "ethusd": dt.date(2026, 9, 25)}     # ETH "listed" later


def run(conn, store, http):
    collector = bs.BitstampCollector(Context(conn, store, http, None, http.now))
    result = collector.collect()
    conn.commit()
    return result


def stored(conn, pair):
    return conn.execute("select day, close, volume from crypto.ohlc_daily where pair = %s order by day",
                        (pair,)).fetchall()


@pytest.mark.db
def test_backfill_then_increments_and_reruns_add_nothing(conn, store, small_history):
    now = dt.datetime(2026, 10, 18, 0, 20, tzinfo=UTC)
    http = FakeBitstamp(small_history, now)
    first = run(conn, store, http)
    btc, eth = stored(conn, "btcusd"), stored(conn, "ethusd")
    assert btc[0]["day"] == dt.date(2026, 9, 1) and btc[-1]["day"] == dt.date(2026, 10, 17)   # never 10-18
    assert eth[0]["day"] == dt.date(2026, 9, 25) and len(eth) == 23
    assert len(btc) == 47 and first.rows_added == 47 + 23 and first.new_data
    assert btc[-1]["close"] == http.close("btcusd", dt.date(2026, 10, 17)) and btc[-1]["volume"] == 2.5
    # every response was archived and catalogued before it was parsed
    fetches = conn.execute("select count(*) n from ops.raw_fetches where source_id = 'bitstamp'").fetchone()["n"]
    assert fetches == len(http.calls) == 10                  # five ten-day windows per pair

    again = run(conn, store, FakeBitstamp(small_history, now))
    assert not again.new_data and again.rows_added == 0

    tomorrow = FakeBitstamp(small_history, now + dt.timedelta(days=1))
    later = run(conn, store, tomorrow)
    assert later.rows_added == 2                             # one new day per pair
    assert tomorrow.calls == [("btcusd", dt.date(2026, 10, 18)), ("ethusd", dt.date(2026, 10, 18))]


@pytest.mark.db
def test_a_pair_that_goes_quiet_fails_the_run_after_the_others_are_stored(conn, store, small_history):
    now = dt.datetime(2026, 10, 18, 0, 20, tzinfo=UTC)
    run(conn, store, FakeBitstamp(small_history, now))
    quiet = FakeBitstamp(small_history, now + dt.timedelta(days=2), silent={"ethusd"})
    with pytest.raises(RuntimeError, match=r"ethusd .*no candles from 2026-10-18"):
        run(conn, store, quiet)
    conn.rollback()
    assert stored(conn, "btcusd")[-1]["day"] == dt.date(2026, 10, 19)   # BTC was still stored and committed
    assert stored(conn, "ethusd")[-1]["day"] == dt.date(2026, 10, 17)


@pytest.mark.db
def test_a_pair_with_no_history_at_all_is_an_error(conn, store, small_history):
    http = FakeBitstamp(small_history, dt.datetime(2026, 10, 18, 0, 20, tzinfo=UTC), silent={"ethusd"})
    with pytest.raises(RuntimeError, match="no candles at all"):
        run(conn, store, http)


@pytest.mark.db
def test_a_refetched_day_that_differs_is_recorded_never_written_over(conn, store):
    from data_platform.core import db

    now = dt.datetime(2026, 10, 18, 7, 44, tzinfo=UTC)
    rows = parse.complete(parse.parse_ohlc(body("btcusd_2026-10-16_with_current.json"), "btcusd"), now)
    f1, sha1 = db.record_fetch(conn, store, source_id="bitstamp", method="GET", url="u", params={}, http_status=200,
                               body=b"{}", content_type="application/json", fetched_at=now)
    assert bs.store(conn, rows, f1, sha1, now) == (2, 0)
    assert bs.store(conn, rows, f1, sha1, now) == (0, 0)                  # identical: nothing, no conflict
    changed = [dict(rows[0], close=rows[0]["close"] + 1)]
    f2, sha2 = db.record_fetch(conn, store, source_id="bitstamp", method="GET", url="u", params={"x": 1},
                               http_status=200, body=b"{ }", content_type="application/json", fetched_at=now)
    assert bs.store(conn, changed, f2, sha2, now) == (0, 1)
    assert stored(conn, "btcusd")[0]["close"] == rows[0]["close"]
    conflict = conn.execute("select stored, incoming from ops.value_conflicts").fetchone()
    assert conflict["incoming"]["close"] == rows[0]["close"] + 1
    with pytest.raises(psycopg.Error):                                    # and the table refuses edits outright
        conn.execute("update crypto.ohlc_daily set close = 1")
