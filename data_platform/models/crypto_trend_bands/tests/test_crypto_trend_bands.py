"""crypto_trend_bands: the running fits equal an ordinary (and a weighted) least-squares fit of each prefix; an exact
power law is recovered; the bands and the position are what the method says; rows never change later."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from conftest import CryptoInputs, assert_point_in_time, model_parameters, run_models, synthetic_btc
from data_platform.models._lib.crypto import GENESIS
from data_platform.models.crypto_trend_bands import compute as fv


def test_running_fit_equals_least_squares_on_every_prefix():
    rng = np.random.default_rng(2)
    x = np.sort(rng.uniform(6.9, 8.8, 400))
    y = 1.5 + 5.7 * x + rng.normal(0, 0.6, 400)
    w = 1.0 / np.exp(x)
    f = fv.running_fit(x, y, w)
    for i in (50, 199, 399):
        # weighted least squares: polyfit minimises sum((w_poly * resid)^2), so pass sqrt(w)
        b, a = np.polyfit(x[: i + 1], y[: i + 1], 1, w=np.sqrt(w[: i + 1]))
        assert f["slope"][i] == pytest.approx(b, rel=1e-9) and f["intercept"][i] == pytest.approx(a, rel=1e-9)
        resid = y[: i + 1] - (a + b * x[: i + 1])
        n = i + 1
        expected_sd = math.sqrt(np.sum(w[:n] * resid ** 2) / np.sum(w[:n]) * n / (n - 2))
        assert f["sd"][i] == pytest.approx(expected_sd, rel=1e-8)
    plain = fv.running_fit(x, y, np.ones_like(x))
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    assert plain["slope"][-1] == pytest.approx(b) and plain["sd"][-1] == pytest.approx(np.std(resid, ddof=2))


def test_a_power_law_is_recovered_and_the_bands_follow_the_method():
    rng = np.random.default_rng(5)
    days = [dt.date(2011, 9, 14) + dt.timedelta(days=i) for i in range(4000)]
    t = np.array([(d - GENESIS).days for d in days], dtype=float)
    closes = 10 ** (-17.01 + 5.82 * np.log10(t) + rng.normal(0, 0.25, len(t)))
    params = model_parameters("crypto_trend_bands")
    out = fv.compute(CryptoInputs({"btcusd": dict(zip(days, closes.tolist()))}, params), None)["models.crypto_trend_band"]
    last = {r["fit"]: r for r in out if r["day"] == days[-1]}
    pl, lr = last["power_law"], last["log_regression"]
    assert pl["slope"] == pytest.approx(5.82, abs=0.1) and pl["intercept"] == pytest.approx(-17.01, abs=0.35)
    assert lr["slope"] == pytest.approx(5.82, abs=0.15)                       # same exponent, other weighting
    assert lr["intercept"] / math.log(10) == pytest.approx(-17.01, abs=0.5)   # ln units, so divide by ln 10
    assert pl["resid_sd"] == pytest.approx(0.25, abs=0.02)
    mid = math.log10(pl["fitted"])
    assert math.log10(pl["upper_2"]) == pytest.approx(mid + 2 * pl["resid_sd"])
    assert math.log10(pl["lower_1"]) == pytest.approx(mid - pl["resid_sd"])
    assert pl["position"] == pytest.approx((math.log10(pl["close"]) - math.log10(pl["lower_2"]))
                                          / (math.log10(pl["upper_2"]) - math.log10(pl["lower_2"])))
    assert min(r["day"] for r in out) == days[params["min_observations"] - 1]   # a year of closes first
    assert {r["pair"] for r in out} == {"btcusd"}


def test_rows_never_change_when_later_days_arrive():
    closes = {"btcusd": synthetic_btc()}
    for cut in (dt.date(2017, 12, 17), dt.date(2025, 10, 6)):
        assert_point_in_time(fv.compute, closes, model_parameters("crypto_trend_bands"), cut,
                             {"models.crypto_trend_band": ["pair", "day", "fit"]})


@pytest.mark.db
def test_the_model_runs_on_the_database(conn, store):
    from data_platform.collectors.bitstamp.collector import store as store_candles
    from data_platform.core import db

    now = dt.datetime(2026, 10, 18, 1, tzinfo=dt.timezone.utc)
    fetch_id, sha = db.record_fetch(conn, store, source_id="bitstamp", method="GET", url="https://x/", params={},
                                    http_status=200, body=b"{}", content_type="application/json", fetched_at=now)
    history = synthetic_btc(start=dt.date(2020, 1, 1), end=dt.date(2022, 1, 1))
    store_candles(conn, [{"pair": "btcusd", "day": d, "open": c, "high": c, "low": c, "close": c, "volume": 1.0}
                         for d, c in history.items()], fetch_id, sha, now)
    conn.commit()
    run_models(conn, ["crypto_trend_bands"])
    n = conn.execute("select count(*) n from models.crypto_trend_band").fetchone()["n"]
    assert n == 2 * (len(history) - 364)
