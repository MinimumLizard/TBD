"""The three lab models end to end on real data (tests/fixtures/cse/2026-10-02: one year of CIC, COMB, HAYL, LOLC and
NTB, the ASPI, the security list and the company profiles): the universe with its reasons, the estimates and the
covariance's factor form, the portfolios and the versions with fewer names, the point-in-time rule, the reuse of
unchanged dates, the forward-only record, and version 1.0.0's need for the private settings. With five shares the
caps are loosened (the parameters of a test, not of the models)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from conftest import FIXTURES, run_models
from data_platform.collectors.cse import collector as cse, parse
from data_platform.core import db
from data_platform.jobs import reviews
from data_platform.models._lib import cse_estimates as est
from data_platform.models.cse_risk_estimates import compute as risk

DAY = FIXTURES / "cse" / "2026-10-02"
NOW = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)
SYMBOLS = ("CIC.N0000", "COMB.N0000", "HAYL.N0000", "LOLC.N0000", "NTB.N0000")
D = dt.date.fromisoformat

RISK = {"min_history_weeks": 40, "first_estimate_date": None, "preview_min_weeks": None}
LAB = {"max_weight": 0.5, "max_sector_weight": 1.0, "max_group_weight": 1.0,
       "fewer_names": {"sizes": [2, 3], "kinds": ["min_variance", "max_sharpe", "equal_weight"], "buffer": 1.5,
                       "rebalance_months": [1, 4, 7, 10]}}
PORTFOLIOS = ["min_variance", "risk_parity", "max_sharpe", "equal_weight"] + [
    f"{kind}_{k}" for k in (2, 3) for kind in ("min_variance", "max_sharpe", "equal_weight")]
PARAMS = {"cse_risk_estimates": {**RISK, "risk_free": {"source": "fixed", "annual": 0.10}},
          "cse_portfolio_lab": LAB, "cse_lab_record": {"portfolios": PORTFOLIOS}}
MODELS = ["cse_corporate_actions", "cse_total_returns", "cse_ownership", "cse_risk_estimates", "cse_portfolio_lab",
          "cse_lab_record"]


def fetch(conn, store, endpoint, body, params):
    return db.record_fetch(conn, store, source_id="cse_api", method="POST", url=cse.API + endpoint, params=params,
                           http_status=200, body=body, content_type="application/json", fetched_at=NOW)


def load(conn, store, until: dt.date | None = None, since: dt.date | None = None):
    keep = lambda rows: [r for r in rows if (until is None or r["session_date"] <= until)  # noqa: E731
                         and (since is None or r["session_date"] > since)]
    if since is None:
        body = (DAY / "allSecurityCode.json").read_bytes()
        fid, _ = fetch(conn, store, "allSecurityCode", body, {})
        cse.store(conn, "cse.security_list", parse.security_list(body, D("2025-10-01")), ["session_date", "symbol"],
                  fid, NOW)
        for s in SYMBOLS:
            body = (DAY / "companyProfile" / f"{s}.json").read_bytes()
            fid, sha = fetch(conn, store, "companyProfile", body, {"symbol": s})
            cse.store(conn, "cse.company_profiles", [dict(parse.company_profile(body, s), raw_sha256=sha)],
                      ["symbol", "raw_sha256"], fid, NOW)
    part = str(until or since)
    for s in SYMBOLS:
        body = (DAY / "companyChartDataByStock" / f"{s}.json").read_bytes()
        fid, _ = fetch(conn, store, "companyChartDataByStock", body, {"symbol": s, "part": part})
        cse.store_prices(conn, keep(parse.stock_chart(body, s)), fid, NOW)
    body = (DAY / "chartData_1_p5.json").read_bytes()
    fid, _ = fetch(conn, store, "chartData", body, {"chartId": 1, "part": part})
    cse.store_indices(conn, keep(parse.index_chart(body, "ASI")), fid, NOW)
    conn.commit()


def settings(conn, tmp_path, excluded=("NTB.N0000",)):
    reviews.sync_sector_overrides(conn, code_version="t")
    private = tmp_path / "lab_private.yaml"
    private.write_text("excluded: [" + ", ".join(excluded) + "]\nportfolio_size_lkr: 5000000\n")
    reviews.sync_lab_private(conn, private, code_version="t")


def same(a: list[dict], b: list[dict]) -> bool:
    key = lambda r: sorted((k, repr(v)) for k, v in r.items())  # noqa: E731
    return sorted(map(key, a)) == sorted(map(key, b))


def rows(conn, table, version="1.1.0", where="true"):
    return [{k: v for k, v in r.items() if k != "run_id"} for r in conn.execute(
        f"select * from {table} where method_version = %s and {where}", (version,))]


@pytest.fixture
def lab(conn, store, tmp_path):
    load(conn, store)
    settings(conn, tmp_path)
    run_models(conn, MODELS, PARAMS)
    return conn


@pytest.mark.db
def test_the_universe_names_every_reason_and_the_private_list_applies_to_version_1_0_0_only(lab):
    last = lab.execute("select max(as_of) d from models.cse_risk_summary where method_version = '1.1.0'"
                       ).fetchone()["d"]
    uni = {r["symbol"]: r for r in rows(lab, "models.cse_risk_universe", where=f"as_of = '{last}'")}
    assert {s for s, r in uni.items() if r["included"]} == set(SYMBOLS)
    reasons = {r["reason"] for r in uni.values() if not r["included"]}
    assert all(r["reason"] for r in uni.values() if not r["included"])          # every one left out says why
    assert any(x.startswith("not an ordinary share") for x in reasons) and "history 0 weeks < 40" in reasons
    old = {r["symbol"]: r for r in rows(lab, "models.cse_risk_universe", "1.0.0", f"as_of = '{last}'")}
    assert old["NTB.N0000"]["reason"] == est.EXCLUDED_REASON and not old["NTB.N0000"]["included"]


@pytest.mark.db
def test_the_covariance_rebuilt_from_the_stored_weekly_returns_gives_the_stored_volatilities(lab):
    s = rows(lab, "models.cse_risk_summary", where="status = 'ok'")[-1]
    e = sorted(rows(lab, "models.cse_risk_estimate", where=f"as_of = '{s['as_of']}'"), key=lambda r: r["symbol"])
    weekly = {}
    for r in rows(lab, "models.cse_weekly_return"):
        weekly.setdefault(r["series"], {})[r["week_end"].isoformat()] = r["weekly_return"]
    from data_platform.models.cse_portfolio_lab.compute import returns_window
    R = returns_window(s, [r["symbol"] for r in e], weekly)
    assert len(R) == s["history_weeks"] == 40
    cov, shrink = est.ledoit_wolf(R)
    assert shrink == s["shrinkage"]
    assert np.sqrt(np.diag(cov)).tolist() == [r["volatility"] for r in e]
    for r in e:                                           # CAPM: E[R] = r_f + beta x premium
        assert r["expected_return"] == pytest.approx(0.10 + r["beta"] * 0.06)


@pytest.mark.db
def test_portfolios_meet_their_constraints_and_the_fewer_name_versions_their_floor(lab):
    day = rows(lab, "models.cse_lab_summary", where="status = 'ok'")[-1]["as_of"]
    ports = {r["portfolio"]: r for r in rows(lab, "models.cse_lab_portfolio", where=f"as_of = '{day}'")}
    assert {"min_variance", "risk_parity", "max_sharpe", "equal_weight", "market"} <= set(ports)
    for name in ("min_variance", "risk_parity", "max_sharpe"):
        assert ports[name]["constraints_ok"] and ports[name]["weight_sum"] == pytest.approx(1.0)
    w = rows(lab, "models.cse_lab_weight", where=f"as_of = '{day}'")
    for k in (2, 3):
        mv = [x for x in w if x["portfolio"] == f"min_variance_{k}"]
        assert len(mv) == k and min(x["weight"] for x in mv) >= 0.5 / k - 1e-6
        assert ports[f"min_variance_{k}"]["tracking_error"] > 0
        assert ports[f"equal_weight_{k}"]["n_names"] == k
    frontier = sorted(rows(lab, "models.cse_lab_frontier", where=f"as_of = '{day}'"), key=lambda r: r["point"])
    assert len(frontier) == 25 and [f["expected_return"] for f in frontier] == sorted(
        f["expected_return"] for f in frontier)


@pytest.mark.db
def test_fewer_name_weights_change_only_on_rebalance_dates(lab):
    by = {}
    for r in rows(lab, "models.cse_lab_portfolio", where="portfolio = 'min_variance_3' and status = 'ok'"):
        by[r["as_of"]] = r["formed_on"]
    formed = sorted(set(by.values()))
    assert formed[0] == min(by)                           # set on the first estimate date
    assert all(d.month in (1, 4, 7, 10) and d.day <= 7 for d in formed[1:])


@pytest.mark.db
def test_a_row_for_a_date_uses_only_data_up_to_it(conn, store, tmp_path):
    """The models run once on the data up to a cut, then again with the rest: the rows for dates up to the cut are
    unchanged (and no revision is recorded)."""
    cut = D("2026-08-14")
    load(conn, store, until=cut)
    settings(conn, tmp_path)
    run_models(conn, MODELS, PARAMS)
    tables = ["models.cse_risk_summary", "models.cse_risk_universe", "models.cse_risk_estimate",
              "models.cse_weekly_return", "models.cse_lab_summary", "models.cse_lab_portfolio", "models.cse_lab_weight",
              "models.cse_lab_frontier"]
    date_col = lambda t: "week_end" if t == "models.cse_weekly_return" else "as_of"  # noqa: E731
    before = {t: rows(conn, t) for t in tables}
    assert before["models.cse_lab_portfolio"]
    load(conn, store, since=cut)
    run_models(conn, MODELS, PARAMS)
    for t in tables:
        assert same(before[t], [r for r in rows(conn, t) if r[date_col(t)] <= cut]), t
    revised = conn.execute("select count(*) n from models.revisions where table_name like 'models.cse_risk%' "
                           "or table_name like 'models.cse_lab%'").fetchone()["n"]
    assert revised == 0


@pytest.mark.db
def test_an_unchanged_date_is_reused_and_reuse_gives_what_a_fresh_computation_gives(lab):
    again = run_models(lab, ["cse_portfolio_lab"], PARAMS)["cse_portfolio_lab"]
    assert again.counts.updated == again.counts.inserted == again.counts.deleted == 0
    stored = {t: rows(lab, t) for t in ("models.cse_lab_portfolio", "models.cse_lab_weight")}
    lab.execute("delete from models.cse_lab_summary where method_version = '1.1.0'")
    lab.commit()
    fresh = run_models(lab, ["cse_portfolio_lab"], PARAMS)["cse_portfolio_lab"]
    assert fresh.counts.updated == 0 and fresh.counts.deleted == 0
    for t, r in stored.items():
        assert same(rows(lab, t), r), t


@pytest.mark.db
def test_the_record_starts_at_the_first_run_and_only_adds_later_sessions(conn, store, tmp_path):
    cut = D("2026-09-15")
    load(conn, store, until=cut)
    settings(conn, tmp_path)
    run_models(conn, MODELS, PARAMS)
    first = rows(conn, "models.cse_lab_nav")
    assert first and {r["session_date"] for r in first} == {cut}             # never backfilled
    assert {r["portfolio"] for r in first} == set(PORTFOLIOS) | {"market"}
    load(conn, store, since=cut)
    run_models(conn, MODELS, PARAMS)
    after = rows(conn, "models.cse_lab_nav")
    assert same([r for r in after if r["session_date"] == cut], first)
    sessions = sorted({r["session_date"] for r in after})
    assert sessions[0] == cut and len(sessions) > 5                    # each later session, in order


@pytest.mark.db
def test_version_1_0_0_computes_nothing_without_the_private_settings(conn, store):
    load(conn, store)
    reviews.sync_sector_overrides(conn, code_version="t")
    run_models(conn, MODELS, PARAMS)
    assert rows(conn, "models.cse_risk_summary", "1.0.0") == [] and rows(conn, "models.cse_lab_summary", "1.0.0") == []
    assert rows(conn, "models.cse_risk_summary")                     # 1.1.0 does not need them


def test_the_bill_yield_is_used_once_a_full_month_has_passed():
    bills = [(D("2026-07-01"), 8.1), (D("2026-08-01"), 8.2), (D("2026-09-01"), 8.3)]
    spec = {"source": "cbsl_tb_12m", "publication_delay_months": 1}
    assert risk.risk_free(spec, bills, D("2026-10-15"))[0] == pytest.approx(0.082)        # August
    assert risk.risk_free(spec, bills, D("2026-11-01"))[0] == pytest.approx(0.083)
    assert risk.risk_free(spec, bills, D("2026-08-31"))[0] is None          # July: not until 1 September
    assert risk.risk_free({"source": "fixed", "annual": 0.099}, [], D("2026-10-15"))[0] == 0.099


def test_sector_labels_map_to_the_20_industry_groups():
    from data_platform.models._lib.cse_sectors import classify
    cases = {"FOOD BEVERAGE & TOBACCO": "Food, Beverage & Tobacco", "Insurance ": "Insurance",
             " Investment Banking & Brokerage": "Diversified Financials", "- Property & Casualty Insurance": "Insurance",
             "45103010 - Application Software": "Software & Services",
             "Real Estate (6010)": "Real Estate Management & Development", "Industrials": None, None: None}
    for label, group in cases.items():
        assert classify("X.N0000", label, {}) == group
    assert classify("MSL.N0000", "Services", {"MSL.N0000": "Transportation"}) == "Transportation"


def test_weekly_returns_use_the_last_value_on_or_before_each_wednesday():
    level = pd.Series({"2026-09-15": 100.0, "2026-09-22": 110.0, "2026-09-25": 99.0, "2026-10-01": 121.0})
    r = est.weekly_returns(level, ["2026-09-16", "2026-09-23", "2026-09-30"])
    assert list(r.index) == ["2026-09-23", "2026-09-30"]
    assert r["2026-09-23"] == pytest.approx(0.10) and r["2026-09-30"] == pytest.approx(99 / 110 - 1)


@pytest.mark.db
def test_the_owners_report_is_marked_internal_has_the_mockups_and_no_banned_wording(lab):
    from data_platform import compliance
    from data_platform.jobs import lab_report

    text = lab_report.build(lab, "1.1.0", LAB)
    assert "INTERNAL RESEARCH ONLY" in text and text.count("MOCK-UP FOR LEGAL REVIEW") == 3
    assert "<script" not in text and "http" not in text                  # self-contained, nothing loaded
    banned, allow = compliance.load_rules()
    assert compliance.scan_text("lab-report.html", text, banned, allow) == []


def test_the_report_refuses_a_path_inside_the_repository(tmp_path):
    from data_platform.core.settings import REPO_ROOT
    from data_platform.jobs import lab_report

    assert lab_report.main(["--out", str(REPO_ROOT / "docs" / "lab.html")]) == 2
    assert not (REPO_ROOT / "docs" / "lab.html").exists()


# --- the walk-forward test (cse_lab_backtest) ------------------------------------------------------------------------

BT_PORTFOLIOS = [f"{kind}_{k}" for k in (2, 3) for kind in ("min_variance", "max_sharpe", "equal_weight")]
BT_PARAMS = {**PARAMS, "cse_lab_backtest": {
    "risk_free": {"source": "fixed", "annual": 0.10}, "max_weight": 0.5, "max_sector_weight": 1.0,
    "max_group_weight": 1.0, "fewer_names": {"sizes": [2, 3], "kinds": ["min_variance", "max_sharpe", "equal_weight"],
                                             "buffer": 1.5},
    "portfolios": BT_PORTFOLIOS}}
BT_MODELS = MODELS + ["cse_lab_backtest"]


def bt_rows(conn, table, where="true"):
    return rows(conn, table, "1.0.0", where)


@pytest.mark.db
def test_the_backtest_starts_when_the_rules_first_can_run_and_covers_both_policies(conn, store, tmp_path):
    load(conn, store)
    settings(conn, tmp_path)
    run_models(conn, BT_MODELS, BT_PARAMS)
    summary = {(r["policy"], r["portfolio"]): r for r in bt_rows(conn, "models.cse_bt_summary")}
    assert set(summary) == {(p, x) for p in ("quarterly", "dynamic") for x in BT_PORTFOLIOS + ["market", "bills"]}
    first = conn.execute("select min(session_date) d from cse.indices_daily").fetchone()["d"]
    start = {r["start_date"] for r in summary.values()}
    assert len(start) == 1 and (start.pop() - first).days >= 26 * 7       # 26 weekly returns before the first date
    nav = bt_rows(conn, "models.cse_bt_nav")
    first_day = min(r["session_date"] for r in nav)
    assert all(r["nav"] == pytest.approx(1_000_000) for r in nav
               if r["session_date"] == first_day and r["portfolio"] in ("market", "bills"))
    # bills grow at the stated rate, never fall
    bills = sorted((r["session_date"], r["nav"]) for r in nav if r["portfolio"] == "bills" and r["policy"] == "quarterly")
    assert all(b >= a for (_, a), (_, b) in zip(bills, bills[1:])) and bills[-1][1] > bills[0][1]
    # every portfolio paid the cost of its first purchases
    events = bt_rows(conn, "models.cse_bt_event")
    inception = [e for e in events if e["kind"] == "inception"]
    assert len(inception) == 2 * len(BT_PORTFOLIOS) and all(e["cost"] > 0 for e in inception)


@pytest.mark.db
def test_quarterly_rebalances_only_on_quarter_dates_and_dynamic_only_on_monthly_checks(conn, store, tmp_path):
    load(conn, store)
    settings(conn, tmp_path)
    run_models(conn, BT_MODELS, BT_PARAMS)
    events = [e for e in bt_rows(conn, "models.cse_bt_event") if e["kind"] in ("scheduled", "threshold")]
    sessions = sorted(r["session_date"] for r in conn.execute(
        "select distinct session_date from cse.indices_daily where index_code = 'ASI'"))
    first_of_month = {min(s for s in sessions if (s.year, s.month) == (d.year, d.month)) for d in sessions}
    for e in events:
        assert e["session_date"] in first_of_month, e
        if e["policy"] == "quarterly":
            assert e["kind"] == "scheduled" and e["session_date"].month in (1, 4, 7, 10)
        if e["kind"] == "threshold":
            assert e["policy"] == "dynamic" and (e["left_universe"] or e["tracking_error"] > 0.03)
    targets = bt_rows(conn, "models.cse_bt_target", "today")
    assert targets and not any(t["applied"] for t in targets)            # today's portfolio is shown, not applied
    for p in BT_PORTFOLIOS:
        w = [t["weight"] for t in targets if t["portfolio"] == p and t["policy"] == "dynamic"]
        assert sum(w) == pytest.approx(1.0) and len(w) == int(p[-1])


@pytest.mark.db
def test_a_backtest_decision_uses_only_data_up_to_its_date(conn, store, tmp_path):
    """Run on the data up to a cut, then with the rest: every value, rebalance, trade and model weight up to the cut is
    unchanged (today's portfolio, which is the latest session's, aside)."""
    cut = D("2026-08-14")
    load(conn, store, until=cut)
    settings(conn, tmp_path)
    run_models(conn, BT_MODELS, BT_PARAMS)
    tables = {"models.cse_bt_nav": "session_date", "models.cse_bt_event": "session_date",
              "models.cse_bt_trade": "session_date", "models.cse_bt_target": "as_of"}
    before = {t: [r for r in bt_rows(conn, t) if not r.get("today")] for t in tables}
    assert before["models.cse_bt_nav"] and before["models.cse_bt_event"]
    load(conn, store, since=cut)
    run_models(conn, BT_MODELS, BT_PARAMS)
    for t, col in tables.items():
        after = [r for r in bt_rows(conn, t) if r[col] <= cut and not r.get("today")]
        assert same(before[t], after), t
