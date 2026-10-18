"""The gap check classifies holes correctly: a real gap (2026-10-05-style), an unlisted holiday, an explained hole."""
from __future__ import annotations

import datetime as dt

import pytest

from data_platform.core import db
from data_platform.jobs import gapcheck


def test_calendar_skips_weekends_and_closures(tmp_path):
    (tmp_path / "x.yaml").write_text("name: X\nstarts: 2026-10-01\nclosures:\n  2026-10-06: {reason: test}\n")
    cal = gapcheck.load_calendar("x", tmp_path)
    assert cal.business_days(dt.date(2026, 10, 1), dt.date(2026, 10, 9)) == [
        dt.date(2026, 10, d) for d in (1, 2, 5, 7, 8, 9)]
    assert cal.back(dt.date(2026, 10, 7), 1) == dt.date(2026, 10, 5)      # skips the closure


def test_a_market_that_never_closes_counts_weekends(tmp_path):
    (tmp_path / "c.yaml").write_text("name: C\nstarts: 2026-10-01\nevery_day: true\nclosures: {}\n")
    cal = gapcheck.load_calendar("c", tmp_path)
    assert len(cal.business_days(dt.date(2026, 10, 1), dt.date(2026, 10, 7))) == 7
    assert cal.back(dt.date(2026, 10, 5), 1) == dt.date(2026, 10, 4)      # a Sunday


@pytest.mark.db
def test_a_missing_crypto_day_is_missing_not_a_holiday(conn, store, tmp_path):
    (tmp_path / "crypto.yaml").write_text("name: C\nstarts: 2026-10-01\nevery_day: true\nclosures: {}\n")
    now = dt.datetime.now(dt.timezone.utc)
    fetch_id, sha = db.record_fetch(conn, store, source_id="bitstamp", method="GET", url="https://x/", params={},
                                    http_status=200, body=b"{}", content_type=None, fetched_at=now)
    for d in (1, 2, 3, 5):                                                # the 4th (a Sunday) is missing
        conn.execute("""insert into crypto.ohlc_daily (pair, day, open, high, low, close, volume, raw_sha256, fetch_id,
                        fetched_at) values ('btcusd', %s, 1, 1, 1, 1, 0, %s, %s, %s)""",
                     (dt.date(2026, 10, d), sha, fetch_id, now))
    datasets = {"c": {"table": "crypto.ohlc_daily", "date_column": "day", "calendar": "crypto",
                      "starts": dt.date(2026, 10, 1), "grace_days": 1}}
    found = gapcheck.check(conn, dt.date(2026, 10, 6), datasets, tmp_path)
    assert [(f["day"].day, f["status"]) for f in found] == [(4, "missing")]


@pytest.mark.db
def test_gap_classification(conn, store, tmp_path):
    (tmp_path / "cse.yaml").write_text("name: CSE\nstarts: 2026-10-01\nclosures: {}\n")
    now = dt.datetime.now(dt.timezone.utc)
    fetch_id, _ = db.record_fetch(conn, store, source_id="t", method="GET", url="https://x/", params={},
                                  http_status=200, body=b"{}", content_type=None, fetched_at=now)
    # market rows exist for every weekday 1-9 Oct; prices are missing on the 5th (a real gap) and the 7th (acked);
    # nothing at all exists for the 8th (an unlisted holiday?).
    for d in (1, 2, 5, 6, 7, 9):
        conn.execute("insert into cse.market_daily (session_date, source, fetch_id, fetched_at) values (%s,'daily',%s,%s)",
                     (dt.date(2026, 10, d), fetch_id, now))
    for d in (1, 2, 6, 9):
        conn.execute("""insert into cse.prices_daily (session_date, symbol, source, close, fetch_id, fetched_at)
                        values (%s, 'X.N0000', 'daily', 1, %s, %s)""", (dt.date(2026, 10, d), fetch_id, now))
    datasets = {
        "prices": {"table": "cse.prices_daily", "date_column": "session_date", "calendar": "cse",
                   "starts": dt.date(2026, 10, 1), "grace_days": 1, "witnesses": ["market"],
                   "acknowledged": {dt.date(2026, 10, 7): "explained"}},
        "market": {"table": "cse.market_daily", "date_column": "session_date", "calendar": "cse",
                   "starts": dt.date(2026, 10, 1), "grace_days": 1},
    }
    found = {(f["dataset"], f["day"].day): f["status"]
             for f in gapcheck.check(conn, dt.date(2026, 10, 12), datasets, tmp_path)}
    assert found[("prices", 5)] == "missing"
    assert found[("prices", 7)] == "acknowledged"
    assert found[("prices", 8)] == "unconfirmed_closure"
    assert found[("market", 8)] == "unconfirmed_closure"
    assert ("prices", 9) not in found and ("prices", 12) not in found       # present; and inside the grace period


def test_real_config_is_consistent():
    datasets = gapcheck.load_datasets()
    for key, cfg in datasets.items():
        gapcheck.load_calendar(cfg["calendar"])
        for w in cfg.get("witnesses", []):
            assert w in datasets, f"{key}: unknown witness {w}"
            assert datasets[w]["calendar"] == cfg["calendar"], f"{key}: witness {w} is another market"
