"""crypto_cycle: weekly and daily averages by hand, crossings, the cycle table's peaks and lows, completed months
only, and rows that never change when later days arrive."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from conftest import CryptoInputs, assert_point_in_time, model_parameters, run_models, synthetic_btc
from data_platform.models._lib import crypto as lib
from data_platform.models.crypto_cycle import compute as cc


def daily(values, start=dt.date(2026, 1, 5)) -> pd.Series:      # 2026-01-05 is a Monday
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def test_ema_starts_from_a_simple_average():
    e = lib.ema(np.array([1.0, 2.0, 3.0, 4.0]), 3)
    assert np.isnan(e[:2]).all() and e[2] == 2.0
    assert e[3] == pytest.approx(0.5 * 4.0 + 0.5 * 2.0)              # alpha = 2 / (3 + 1)


def test_weekly_averages_use_previous_sundays_and_todays_close():
    s = daily(np.arange(1.0, 29.0))                                    # four Monday-to-Sunday weeks: 1..28
    w = lib.weekly_sma_and_ema(s, sma_weeks=[2], ema_weeks=[2])
    sundays = {7.0, 14.0, 21.0, 28.0}
    assert set(s[s.index.dayofweek == 6]) == sundays
    assert np.isnan(w["sma_2w"].iloc[5])                                # the first week: no previous Sunday
    assert w["sma_2w"].loc["2026-01-14"] == pytest.approx((7.0 + 10.0) / 2)   # Wednesday of week 2
    assert w["sma_2w"].loc["2026-01-18"] == pytest.approx((7.0 + 14.0) / 2)   # its Sunday: the final value
    assert w["ema_2w"].loc["2026-01-18"] == pytest.approx((7.0 + 14.0) / 2)   # the seed is the simple average
    alpha = 2 / 3
    assert w["ema_2w"].loc["2026-01-21"] == pytest.approx(alpha * 17.0 + (1 - alpha) * 10.5)


def test_crossings_are_the_first_day_a_relation_holds():
    idx = pd.date_range("2026-01-01", periods=6, freq="D")
    lines = pd.DataFrame({"pi_sma_111": [1, 1, 3, 3, 1, 3], "pi_sma_350x2": [2, 2, 2, 2, 2, 2],
                          "pi_ema_150": [np.nan, 5, 1, 1, 5, 5], "pi_sma_471x0745": [2, 2, 2, 2, 2, 2]},
                         index=idx, dtype=float)
    got = [(d.day, k) for d, k in cc.crossings(lines)]
    assert got == [(3, "pi_bottom_cross"), (3, "pi_top_cross"), (6, "pi_top_cross")]


def test_the_cycle_peak_is_the_start_of_the_epochs_largest_fall():
    # epoch 3 (2020-05-11 to 2024-04-19): a peak in 2021, a deep low in 2022, then a HIGHER close in March 2024 that is
    # followed by only a small dip. The cycle is 2021 -> 2022, not March 2024.
    points = {"2020-05-11": 9000, "2021-11-08": 67000, "2022-11-21": 15800, "2024-03-13": 73000,
              "2024-04-17": 61000, "2024-04-20": 65000, "2024-06-01": 70000}
    s = pd.Series({pd.Timestamp(k): float(v) for k, v in points.items()}).asfreq("D").interpolate()
    rows = cc.anchors("btcusd", s)
    last = {(r["kind"], r["epoch"]): r for r in rows if r["day"] == dt.date(2024, 6, 1)}
    assert last[("cycle_peak", 3)]["anchor_day"] == dt.date(2021, 11, 8)
    assert last[("cycle_low", 3)]["anchor_day"] == dt.date(2022, 11, 21)
    assert last[("cycle_low", 3)]["change_from_prior"] == pytest.approx(15800 / 67000 - 1)
    assert not last[("cycle_peak", 3)]["provisional"] and last[("cycle_peak", 4)]["provisional"]
    assert last[("halving", 4)]["anchor_close"] == 65000 and last[("halving", 4)]["roi"] == pytest.approx(70000 / 65000 - 1)
    # since halving 4 the path only rises: no fall yet, so the peak is the high so far and there is no low
    assert last[("cycle_peak", 4)]["anchor_day"] == dt.date(2024, 6, 1) and ("cycle_low", 4) not in last
    # on the day of the 2021 top, no fall has happened yet in this simple path: the peak is the high so far
    top_day = {(r["kind"], r["epoch"]): r for r in rows if r["day"] == dt.date(2021, 11, 8)}
    assert top_day[("cycle_peak", 3)]["anchor_day"] == dt.date(2021, 11, 8) and ("cycle_low", 3) not in top_day
    order = [r["kind"] for r in rows if r["day"] == dt.date(2024, 6, 1)]
    assert order == ["halving", "cycle_peak", "cycle_low", "halving", "cycle_peak"]


def test_months_are_published_only_once_complete():
    s = daily(np.linspace(100, 200, 60), start=dt.date(2026, 1, 1))     # Jan, Feb, and 1 day of March
    rows = cc.monthly("btcusd", s)
    assert [r["month"] for r in rows] == [dt.date(2026, 1, 1), dt.date(2026, 2, 1)]
    assert rows[0]["ret_month"] is None and rows[1]["day"] == dt.date(2026, 2, 28)
    assert rows[1]["ret_month"] == pytest.approx(s.loc["2026-02-28"] / s.loc["2026-01-31"] - 1)


def test_mayer_halving_and_month_to_date_on_a_long_history():
    closes = {"btcusd": synthetic_btc(), "ethusd": synthetic_btc(start=dt.date(2017, 8, 16), seed=3)}
    out = cc.compute(CryptoInputs(closes, model_parameters("crypto_cycle")), None)
    rows = {(r["pair"], r["day"]): r for r in out["models.crypto_cycle_daily"]}
    r = rows[("btcusd", dt.date(2025, 3, 15))]
    s = pd.Series(closes["btcusd"])
    window = [closes["btcusd"][dt.date(2025, 3, 15) - dt.timedelta(days=k)] for k in range(200)]
    assert r["sma_200"] == pytest.approx(np.mean(window)) and r["mayer"] == pytest.approx(r["close"] / np.mean(window))
    assert r["last_halving"] == dt.date(2024, 4, 20) and r["days_since_halving"] == 329
    assert r["roi_since_halving"] == pytest.approx(r["close"] / closes["btcusd"][dt.date(2024, 4, 20)] - 1)
    assert r["ret_mtd"] == pytest.approx(r["close"] / closes["btcusd"][dt.date(2025, 2, 28)] - 1)
    eth = rows[("ethusd", dt.date(2018, 1, 1))]
    assert eth["last_halving"] == dt.date(2016, 7, 9) and eth["roi_since_halving"] is None   # no ETH close then
    assert rows[("btcusd", dt.date(2012, 1, 1))]["sma_200w"] is None
    assert len(s) and {e["kind"] for e in out["models.crypto_cycle_event"]} <= {"pi_top_cross", "pi_bottom_cross"}


def test_rows_never_change_when_later_days_arrive():
    closes = {"btcusd": synthetic_btc(), "ethusd": synthetic_btc(start=dt.date(2017, 8, 16), seed=3)}
    tables = {"models.crypto_cycle_daily": ["pair", "day"], "models.crypto_cycle_event": ["pair", "kind", "day"],
              "models.crypto_cycle_anchor": ["pair", "day", "kind", "epoch"],
              "models.crypto_cycle_monthly": ["pair", "month"]}
    for cut in (dt.date(2021, 11, 30), dt.date(2025, 10, 7)):
        assert_point_in_time(cc.compute, closes, model_parameters("crypto_cycle"), cut, tables)


@pytest.mark.db
def test_the_model_runs_on_the_database(conn, store):
    from data_platform.collectors.bitstamp.collector import store as store_candles
    from data_platform.core import db

    now = dt.datetime(2026, 10, 18, 1, tzinfo=dt.timezone.utc)
    fetch_id, sha = db.record_fetch(conn, store, source_id="bitstamp", method="GET", url="https://x/", params={},
                                    http_status=200, body=b"{}", content_type="application/json", fetched_at=now)
    history = synthetic_btc(start=dt.date(2023, 1, 1), end=dt.date(2025, 6, 30))
    store_candles(conn, [{"pair": "btcusd", "day": d, "open": c, "high": c, "low": c, "close": c, "volume": 1.0}
                         for d, c in history.items()], fetch_id, sha, now)
    conn.commit()
    run_models(conn, ["crypto_cycle"])
    n = {t: conn.execute(f"select count(*) n from models.{t}").fetchone()["n"]
         for t in ("crypto_cycle_daily", "crypto_cycle_anchor", "crypto_cycle_monthly")}
    assert n["crypto_cycle_daily"] == len(history) and n["crypto_cycle_monthly"] == 30 and n["crypto_cycle_anchor"] > 0
