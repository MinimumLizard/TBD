"""crypto_market: returns, the distance from the highest close, volatility, checked by hand; rows never change
when later days arrive; and the model runs through the framework on a database."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from conftest import CryptoInputs, assert_point_in_time, model_parameters, run_models, synthetic_btc
from data_platform.models.crypto_market import compute as cm

D0 = dt.date(2026, 1, 1)


def series(values: list[float], start: dt.date = D0) -> dict:
    return {start + dt.timedelta(days=i): v for i, v in enumerate(values)}


def rows_by_day(closes: dict, pair="btcusd") -> dict:
    out = cm.compute(CryptoInputs({pair: closes}, model_parameters("crypto_market")), None)
    return {r["day"]: r for r in out["models.crypto_market_daily"] if r["pair"] == pair}


def test_returns_and_the_highest_close_by_hand():
    closes = [100.0, 110.0, 99.0, 121.0, 108.9] + [108.9] * 30
    rows = rows_by_day(series(closes))
    d = lambda k: D0 + dt.timedelta(days=k)  # noqa: E731
    assert rows[d(0)]["ret_1d"] is None and rows[d(0)]["drawdown"] == 0.0
    assert rows[d(1)]["ret_1d"] == pytest.approx(0.10)
    assert rows[d(2)]["drawdown"] == pytest.approx(99 / 110 - 1) and rows[d(2)]["days_since_ath"] == 1
    assert rows[d(3)]["ath_close"] == 121.0 and rows[d(3)]["ath_day"] == d(3) and rows[d(3)]["drawdown"] == 0.0
    assert rows[d(4)]["drawdown"] == pytest.approx(-0.1) and rows[d(4)]["days_since_ath"] == 1
    assert rows[d(7)]["ret_7d"] == pytest.approx(108.9 / 100 - 1)
    assert rows[d(29)]["ret_30d"] is None and rows[d(30)]["ret_30d"] == pytest.approx(108.9 / 100 - 1)
    assert rows[d(34)]["ret_1y"] is None


def test_volatility_is_the_annualised_standard_deviation_of_daily_log_returns():
    rng = np.random.default_rng(1)
    closes = (100 * np.exp(np.cumsum(rng.normal(0, 0.03, 120)))).tolist()
    rows = rows_by_day(series(closes))
    last = rows[D0 + dt.timedelta(days=119)]
    logret = np.diff(np.log(closes))
    assert last["vol_30d"] == pytest.approx(np.std(logret[-30:], ddof=1) * math.sqrt(365))
    assert last["vol_90d"] == pytest.approx(np.std(logret[-90:], ddof=1) * math.sqrt(365))
    assert rows[D0 + dt.timedelta(days=29)]["vol_30d"] is None          # 29 returns: not yet
    assert rows[D0 + dt.timedelta(days=30)]["vol_30d"] is not None


def test_a_missing_day_has_no_row_and_returns_use_the_last_close_before():
    closes = series([100.0, 105.0, 0.0, 110.0])
    del closes[D0 + dt.timedelta(days=2)]
    rows = rows_by_day(closes)
    assert D0 + dt.timedelta(days=2) not in rows
    assert rows[D0 + dt.timedelta(days=3)]["ret_1d"] == pytest.approx(110 / 105 - 1)
    assert rows[D0 + dt.timedelta(days=3)]["vol_30d"] is None


def test_rows_never_change_when_later_days_arrive():
    closes = {"btcusd": synthetic_btc(start=dt.date(2023, 1, 1)), "ethbtc": series([0.05, 0.051, 0.049] * 200)}
    for cut in (dt.date(2024, 2, 29), dt.date(2026, 1, 5)):
        assert_point_in_time(cm.compute, closes, model_parameters("crypto_market"), cut,
                             {"models.crypto_market_daily": ["pair", "day"]})


@pytest.mark.db
def test_the_model_runs_on_the_database(conn, store):
    from data_platform.collectors.bitstamp.collector import store as store_candles
    from data_platform.core import db

    now = dt.datetime(2026, 10, 18, 1, tzinfo=dt.timezone.utc)
    fetch_id, sha = db.record_fetch(conn, store, source_id="bitstamp", method="GET", url="https://x/", params={},
                                    http_status=200, body=b"{}", content_type="application/json", fetched_at=now)
    rows = [{"pair": "btcusd", "day": D0 + dt.timedelta(days=i), "open": c, "high": c, "low": c, "close": c,
             "volume": 1.0} for i, c in enumerate([100.0 + i for i in range(40)])]
    store_candles(conn, rows, fetch_id, sha, now)
    conn.commit()
    run_models(conn, ["crypto_market"])
    n = conn.execute("select count(*) n from models.crypto_market_daily where method_version = '1.0.0'").fetchone()
    last = conn.execute("select ret_30d from models.crypto_market_daily where day = %s",
                        (D0 + dt.timedelta(days=39),)).fetchone()
    assert n["n"] == 40 and last["ret_30d"] == pytest.approx(139 / 109 - 1)
