"""cse_total_returns: each formula against a hand-worked example built from a real event and the real closes around
it (the old terminal's tests, on tests/fixtures/cse/2026-10-02/companyChartDataByStock), the no-double-adjustment
guard, and the model end to end, including the point-in-time rule."""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import FIXTURES, run_models
from data_platform.collectors.cse import collector as cse, parse
from data_platform.core import db
from data_platform.models.cse_corporate_actions.tests.test_corporate_actions import load_facts
from data_platform.models.cse_total_returns import compute as m

CHART = FIXTURES / "cse" / "2026-10-02"
D = dt.date.fromisoformat


def closes(symbol):
    rows = parse.stock_chart((CHART / "companyChartDataByStock" / f"{symbol}.json").read_bytes(), symbol)
    return [r["session_date"] for r in rows], [r["close"] for r in rows]


def on(rows, day):
    return next(r for r in rows if r["session_date"] == D(day))


def tr(symbol, actions, **kw):
    dates, c = closes(symbol)
    return m.total_returns(dates, c, [dict(a, ex_date=D(a["ex_date"])) for a in actions], **kw)


def test_no_actions_is_the_plain_price_return():
    rows = tr("LOLC.N0000", [])
    dates, c = closes("LOLC.N0000")
    assert [r["total_return"] for r in rows[1:]] == pytest.approx([c[i] / c[i - 1] - 1 for i in range(1, len(c))])
    assert [r["price_return"] for r in rows[1:]] == [r["total_return"] for r in rows[1:]]
    assert rows[-1]["tri"] == pytest.approx(c[-1] / c[0]) and rows[0]["tri"] == 1.0


def test_cash_dividend_cic_2026():
    """CIC final dividend Rs 0.50, XD 01 Jul 2026 (announcement 37168). Cum close 30 Jun 31.00, ex close 31.80:
    R = (31.80 + 0.50) / 31.00 - 1."""
    a = [{"symbol": "CIC.N0000", "type": "cash_dividend", "ex_date": "2026-07-01", "amount_per_share": 0.5}]
    assert on(tr("CIC.N0000", a), "2026-07-01")["total_return"] == pytest.approx(32.30 / 31.00 - 1)
    assert on(tr("CIC.N0000", a), "2026-07-01")["price_return"] == pytest.approx(31.80 / 31.00 - 1)
    # with 15% withheld: (31.80 + 0.50 x 0.85) / 31.00 - 1
    assert on(tr("CIC.N0000", a, withholding=0.15), "2026-07-01")["total_return"] == pytest.approx(32.225 / 31.00 - 1)


SPLIT = [{"symbol": "CIC.N0000", "type": "subdivision", "ex_date": "2025-10-22", "factor": 5.0}]


def test_subdivision_cic_2025():
    """CIC 1:5 sub-division (F = 5), trading resumed 22 Oct 2025. Last close before 170.00, first after 34.20:
    R = 34.20 x 5 / 170.00 - 1."""
    row = on(tr("CIC.N0000", SPLIT), "2025-10-22")
    assert row["total_return"] == pytest.approx(171 / 170 - 1) and row["share_factor"] == 5.0
    assert row["price_return"] == pytest.approx(-0.79882, abs=1e-5)          # what the unadjusted price shows
    assert row["events"] == "subdivision ×5"


def test_scrip_comb_2026():
    """COMB scrip, XD 02 Apr 2026: 1 new share per 108.2352945432 held, F = 109.2352945432 / 108.2352945432.
    Cum 31 Mar 204.25, ex 201.75: R = 201.75 x F / 204.25 - 1."""
    f = 109.2352945432 / 108.2352945432
    row = on(tr("COMB.N0000", [{"symbol": "COMB.N0000", "type": "scrip", "ex_date": "2026-04-02", "factor": f}]),
             "2026-04-02")
    assert row["total_return"] == pytest.approx(201.75 * f / 204.25 - 1)
    assert row["total_return"] == pytest.approx(-0.0031141, abs=1e-6)


def test_rights_hayl_2026():
    """HAYL rights: 3 new per 50 held at Rs 200, XR 18 Mar 2026. TERP = (50 x 205.00 + 3 x 200) / 53;
    R = 203.00 / TERP - 1."""
    a = [{"symbol": "HAYL.N0000", "type": "rights", "ex_date": "2026-03-18", "ratio_new": 3.0, "ratio_held": 50.0,
          "subscription_price": 200.0}]
    row = on(tr("HAYL.N0000", a), "2026-03-18")
    terp = (50 * 205.00 + 3 * 200) / 53
    assert row["base_price"] == pytest.approx(terp) and row["total_return"] == pytest.approx(203.00 / terp - 1)
    assert row["total_return"] == pytest.approx(-0.0083871, abs=1e-7)


def test_other_days_have_factor_one_and_no_dividend():
    rows = tr("CIC.N0000", SPLIT)
    others = [r for r in rows[1:] if r["session_date"] != D("2025-10-22")]
    assert all(r["share_factor"] == 1.0 and r["dividend"] == 0.0 and r["events"] == "" for r in others)
    assert all(r["total_return"] == r["price_return"] for r in others)


def test_an_action_lands_on_the_first_trade_on_or_after_its_ex_date():
    a = [dict(SPLIT[0], ex_date="2025-10-18")]                      # a Saturday
    assert on(tr("CIC.N0000", a), "2025-10-22")["total_return"] == pytest.approx(171 / 170 - 1)


def test_unadjusted_prices_are_adjusted_once_and_adjusted_prices_never_twice():
    dates, c = closes("CIC.N0000")
    split = [dict(SPLIT[0], ex_date=D("2025-10-22"))]
    m.check_adjustment(dates, c, split, history_adjusted=False)     # the real data: passes
    with pytest.raises(m.AdjustmentMismatch, match="history_adjusted is true"):
        m.check_adjustment(dates, c, split, history_adjusted=True)
    adjusted = [p if d >= D("2025-10-22") else p / 5 for d, p in zip(dates, c)]
    with pytest.raises(m.AdjustmentMismatch, match="refusing to adjust them a second time"):
        m.check_adjustment(dates, adjusted, split, history_adjusted=False)
    row = on(m.total_returns(dates, adjusted, split, history_adjusted=True), "2025-10-22")
    assert row["total_return"] == pytest.approx(34.2 / 34.0 - 1) and row["events"] == ""


# --- end to end ---------------------------------------------------------------------------------------------------

NOW = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)


def load_prices(conn, store, until: dt.date | None = None, since: dt.date | None = None):
    """CIC's and HAYL's real one-year chart and the ASPI's, optionally only part of it."""
    keep = lambda rows: [r for r in rows if (until is None or r["session_date"] <= until)  # noqa: E731
                         and (since is None or r["session_date"] > since)]
    for symbol in ("CIC.N0000", "HAYL.N0000"):
        body = (CHART / "companyChartDataByStock" / f"{symbol}.json").read_bytes()
        fid, _ = db.record_fetch(conn, store, source_id="cse_api", method="POST", url=cse.API + "companyChartDataByStock",
                                 params={"symbol": symbol, "part": str(until or since)}, http_status=200, body=body,
                                 content_type="application/json", fetched_at=NOW)
        cse.store_prices(conn, keep(parse.stock_chart(body, symbol)), fid, NOW)
    body = (CHART / "chartData_1_p5.json").read_bytes()
    fid, _ = db.record_fetch(conn, store, source_id="cse_api", method="POST", url=cse.API + "chartData",
                             params={"chartId": 1, "part": str(until or since)}, http_status=200, body=body,
                             content_type="application/json", fetched_at=NOW)
    cse.store_indices(conn, keep(parse.index_chart(body, "ASI")), fid, NOW)
    conn.commit()


def rows(conn, symbol):
    return {r["session_date"]: r for r in conn.execute(
        "select * from models.cse_total_return where symbol = %s order by session_date", (symbol,))}


@pytest.mark.db
def test_the_model_applies_the_confirmed_actions_and_only_those(conn, store):
    load_facts(conn, store)
    load_prices(conn, store)
    run_models(conn, ["cse_corporate_actions", "cse_total_returns"])
    cic = rows(conn, "CIC.N0000")
    assert cic[D("2026-07-01")]["total_return"] == pytest.approx(32.30 / 31.00 - 1)
    assert cic[D("2026-07-01")]["events"] == "div 0.5"
    assert cic[D("2025-10-22")]["total_return"] == pytest.approx(171 / 170 - 1)
    hayl = rows(conn, "HAYL.N0000")
    assert hayl[D("2026-03-18")]["events"] == ""                    # the rights issue awaits confirmation
    # the 1-week total return is the TRI's change over the ASPI's last 5 sessions
    sessions = [r["session_date"] for r in conn.execute(
        "select session_date from cse.indices_daily where index_code = 'ASI' order by 1")]
    day = sessions[-1]
    start = max(d for d in cic if d <= sessions[-6])
    assert cic[day]["tr_1w"] == pytest.approx(cic[day]["tri"] / cic[start]["tri"] - 1)
    assert cic[sessions[3]]["tr_1w"] is None                         # five sessions are not there yet


@pytest.mark.db
def test_a_row_for_a_day_never_changes_when_later_days_arrive(conn, store):
    load_facts(conn, store)
    cut = D("2026-06-15")
    load_prices(conn, store, until=cut)
    run_models(conn, ["cse_corporate_actions", "cse_total_returns"])
    before = {k: {c: v for c, v in r.items() if c != "run_id"} for k, r in rows(conn, "CIC.N0000").items()}
    load_prices(conn, store, since=cut)                            # the later sessions, including the dividend
    result = run_models(conn, ["cse_corporate_actions", "cse_total_returns"])["cse_total_returns"]
    assert result.counts.updated == 0 and result.counts.deleted == 0 and result.counts.inserted > 0
    after = {k: {c: v for c, v in r.items() if c != "run_id"} for k, r in rows(conn, "CIC.N0000").items()}
    assert all(after[k] == v for k, v in before.items())
    assert after[D("2026-07-01")]["events"] == "div 0.5"


@pytest.mark.db
def test_confirming_a_rights_issue_changes_the_total_return_on_its_ex_date(conn, store, tmp_path):
    from data_platform.jobs import reviews

    load_facts(conn, store)
    load_prices(conn, store)
    review = tmp_path / "r.yaml"
    review.write_text('confirm:\n  "35920:HAYL.N0000": {subscription_price: 200}\n')
    reviews.sync(conn, review, code_version="t")
    run_models(conn, ["cse_corporate_actions", "cse_total_returns"])
    row = rows(conn, "HAYL.N0000")[D("2026-03-18")]
    terp = (50 * 205.00 + 3 * 200) / 53
    assert row["events"] == "rights 3:50 @ 200" and row["total_return"] == pytest.approx(203.00 / terp - 1)
