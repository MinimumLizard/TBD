"""Seed a throwaway database for the tier-leak tests (web/tests/leak). Run from the repository root:

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres uv run python web/tests/leak/seed.py

Creates (or recreates) the database `tbd_leak` (or $LEAK_DB_NAME), applies every migration, and writes a small, consistent set of
model outputs in which certain values are MARKERS: numbers that appear nowhere else, so the tests can tell exactly
which model's data reached a page or an API response. Two dates per model: NEW (yesterday) and OLD (five days ago,
the last day a 5-day free preview may show); the preview model also has MID (four days ago), which a preview must
never show; the yield curve also has ANCIENT (40 days ago), beyond the 30-day recent window a free visitor sees. Every model also gets rows under
a reference version that the site must never show to anyone.

Prints the database URL the web app should use (as the read-only web_reader role).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from data_platform.core import db  # noqa: E402
from data_platform.models.framework import write_table  # noqa: E402
from data_platform.models.registry import load_all  # noqa: E402

SLT = dt.timezone(dt.timedelta(hours=5, minutes=30))
TODAY = dt.datetime.now(SLT).date()
NEW = TODAY - dt.timedelta(days=1)
OLD = TODAY - dt.timedelta(days=5)    # exactly the free preview's last visible day (delay 5 days)
MID = TODAY - dt.timedelta(days=4)    # one day inside the delay: never visible to a free visitor
ANCIENT = TODAY - dt.timedelta(days=40)   # outside a 30-day recent window: only the window's full-history tier sees it
MARKERS = Path(__file__).with_name("markers.json")
PERSON = "Mr. Q. Zyxwvut"                  # a made-up private individual: in unpublished tables only
GROUP_HEAD = "Leakcheck Holdings (Pvt) Ltd"   # a made-up company: companies may be named
DB_NAME = os.environ.get("LEAK_DB_NAME", "tbd_leak")   # another name lets two checkouts test at once


def seed(conn) -> dict:
    manifests = load_all()
    current = {name: m.current.method_version for name, m in manifests.items()}
    run_id = conn.execute("insert into models.runs (model, method_version, code_version) values ('seed', '0', 'leak') "
                          "returning run_id").fetchone()["run_id"]

    def put(model: str, table: str, rows: list[dict], version: str | None = None):
        write_table(conn, table, rows, method_version=version or current[model], run_id=run_id, model=model)

    bonds = ["LKB00530H016", "LKB01035F159"]
    put("bond_identity", "models.bond_reference", [
        {"isin": bonds[0], "coupon_pct": 10.0, "maturity_date": "2030-08-15", "tenor_years": 5, "series_label": "10.00%2030A"},
        {"isin": bonds[1], "coupon_pct": 10.7, "maturity_date": "2035-06-15", "tenor_years": 10, "series_label": "10.70%2035A"}])
    quotes = []
    for d in (OLD, NEW):
        for i, isin in enumerate(bonds):
            quotes.append({"obs_date": d, "isin": isin, "bid_yield": 10.1 + i, "offer_yield": 10.0 + i, "mid_yield": 10.05 + i,
                           "bid_price": 100.0, "offer_price": 100.5, "resolved_by": "label", "raw_sha256": "0" * 64})
    put("bond_identity", "models.bond_quotes", quotes)
    put("bond_ns_curve", "models.bond_curve_fit", [
        {"obs_date": d, "beta0": 12.0, "beta1": -3.0, "beta2": 1.0, "lambda_years": 2.82, "n_quotes": 2,
         "rmse_bp": rmse, "n_trades": 0} for d, rmse in ((ANCIENT, 13.1313), (OLD, 11.11), (NEW, 12.12))])
    # ANCIENT is older than the yield curve's 30-day recent window: Plus and above see it, free visitors never do.
    put("bond_ns_curve", "models.bond_curve_point", [
        {"obs_date": d, "isin": isin, "source": "quote", "tau_years": 4.0 + 5 * i,
         "observed_yield": {NEW: 10.0571, OLD: 10.0461, ANCIENT: 10.0391}[d] + i, "fitted_yield": 10.0 + i,
         "residual_bp": 63.9 if d == ANCIENT else 5.0, "weight": 1.0}
        for d in (ANCIENT, OLD, NEW) for i, isin in enumerate(bonds)])
    put("bond_liquidity", "models.bond_liquidity", [
        {"obs_date": d, "isin": isin, "turnover_lkr": 1_000_000_000, "n_trades": 3, "days_traded": 12, "is_benchmark": False,
         "post_auction": False, "tier": "active", "trades_through": d, "trade_data_lag_days": 0}
        for d in (OLD, NEW) for isin in bonds])
    put("bond_rv_zscores", "models.bond_residual_zscore", [
        {"obs_date": d, "isin": bonds[0], "residual_bp": 5.0, "mean_bp": 1.0, "sd_bp": 2.0, "deviation_bp": 4.0,
         "zscore": z, "n_window": 60} for d, z in ((OLD, 6.6641), (MID, 2.2221), (NEW, 7.7731))])
    put("bond_rv_zscores", "models.bond_pair_zscore", [
        {"obs_date": d, "isin_a": bonds[0], "isin_b": bonds[1], "tau_a": 4.0, "tau_b": 9.0, "spread_bp": 3.0,
         "mean_bp": 1.0, "sd_bp": 2.0, "deviation_bp": 2.0, "zscore": z, "n_window": 60}
        for d, z in ((OLD, 4.4411), (MID, 1.1121), (NEW, 5.5521))])
    put("bond_rv_zscores", "models.model_stats", [{"stat_key": "pair_reversion_10d_z2", "value": 31.4159, "n": 99}])
    put("bond_execution_gap", "models.bond_execution_gap", [
        {"obs_date": d, "gap_bp": g, "n": 9, "window_days": 20} for d, g in ((OLD, 22.27), (NEW, 33.37))])
    put("bond_carry", "models.bond_funding", [
        {"obs_date": d, "bill_pct": 9.0, "rate_pct": 9.05, "spread_bp": 5.0, "bill_as_of": d, "stale_days": 0, "n_bills": 1,
         "window_days": 5} for d in (OLD, NEW)])
    put("bond_carry", "models.bond_carry", [
        {"obs_date": d, "isin": bonds[0], "entry_gap_bp": 0.0, "entry_yield": 10.05, "price": 100.0, "duration": 3.0,
         "carry_bp": 100.0, "roll_bp": 20.0, "total_bp": 120.0, "per_duration_bp": p, "convexity": c}
        for d, p, c in ((OLD, 77.71, 36.21), (NEW, 88.81, 47.31))])

    put("cse_market_tape", "models.cse_market_session", [
        {"session_date": d, "turnover": t, "volume": 1000.0, "trades": 100.0, "sessions_needed": 3, "foreign_buy": 10.0,
         "foreign_sell": 5.0, "foreign_net": 5.0, "per": 10.0, "pbv": 1.0, "dy": 3.0, "market_cap": 1e12, "listed": 280,
         "traded_all": 250, "equities_up": 1, "equities_down": 1, "equities_flat": 0, "equities_traded": 2}
        for d, t in ((OLD, 111_000_000.0), (NEW, 222_000_000.0))])
    put("cse_market_tape", "models.cse_index_session", [
        {"session_date": d, "index_code": code, "value": v, "change": 1.0, "pct": 0.001}
        for d in (OLD, NEW) for code, v in (("ASI", 20000.0), ("S&P SL20", 6000.0), ("BNK", 900.0))])
    put("cse_security_metrics", "models.cse_security_session", [
        {"session_date": d, "symbol": s, "traded": True, "close": c, "change": 1.0, "pct": 0.01, "turnover": 5_000_000.0,
         "volume": 1000.0, "range_flag": False} for d in (OLD, NEW) for s, c in (("AAA.N0000", 55.5), ("BBB.N0000", 66.6))])
    action = {"symbol": "AAA.N0000", "action_type": "cash_dividend", "ex_date": NEW, "amount_per_share": 8.7654,
              "status": "confirmed", "note": "", "source_url": "https://cdn.cse.lk/x.pdf", "announced_date": OLD}
    put("cse_corporate_actions", "models.cse_corporate_action", [
        {**action, "action_id": "1:AAA.N0000", "announcement_id": 1, "use_status": "used"},
        {"action_id": "2:AAA.N0000", "symbol": "AAA.N0000", "action_type": "rights", "ex_date": None, "ratio_new": 3.0,
         "ratio_held": 50.0, "status": "needs_review", "note": "", "source_url": "", "announcement_id": 2,
         "announced_date": OLD, "use_status": "awaiting_confirmation"}])
    put("cse_corporate_actions", "models.cse_corporate_action_used", [{**action, "action_id": "1:AAA.N0000"}])
    put("cse_total_returns", "models.cse_total_return", [
        {"symbol": "AAA.N0000", "session_date": d, "close": 55.5, "share_factor": 1.0, "dividend": 0.0, "events": "",
         "tri": tri, "tr_1w": w} for d, tri, w in ((OLD, 1.0, None), (NEW, 1.2345, 0.031415))])

    # Company figures (free) on the shares list and the share page; ownership (free) on the share page. The two
    # ownership tables that name people are unpublished: PERSON (a made-up individual) and 424242.17 must never
    # appear anywhere, to anyone.
    put("cse_fundamentals", "models.cse_fundamentals", [
        {"session_date": d, "code": "AAA", "price": 55.5, "price_date": d, "shares": 1e6, "fye": "31 Mar", "nav": 20.0,
         "nav_period": OLD, "pb": 2.775, "ttm_profit": 1e6, "ttm_eps": 1.0, "ttm_to": OLD, "ttm_note": "", "pe": pe,
         "earnings_yield": 0.02, "roe": 0.05, "div_ttm": 1.0, "dy": 0.018, "report_id": 7, "report_period": OLD,
         "report_url": "https://cdn.cse.lk/r.pdf"} for d, pe in ((OLD, 61.4321), (NEW, 87.6543))])
    put("cse_fundamentals", "models.cse_report_figures", [
        {"report_id": 7, "code": "AAA", "period_date": OLD, "fye": "1", "shares": 1e6, "eps": 0.25, "eps_class": "quarter",
         "eps_status": "verified", "profit": 250000.0, "unit": 1.0, "eps_line": "Basic earnings per share 0.25",
         "nav": 20.0, "nav_status": "verified", "equity": 2e7, "nav_line": "Net assets per share 20.00",
         "source_url": "https://cdn.cse.lk/r.pdf", "as_of": NEW}])
    put("cse_ownership", "models.cse_company_ownership", [
        {"session_date": d, "code": "AAA", "report_id": 7, "period_date": OLD, "report_status": "ok",
         "table_status": "verified", "top20_pct": 80.0, "pct_listed": 10.0, "pct_company": 30.0, "pct_institution": 5.0,
         "pct_individual": 35.0, "pct_joint": 0.0, "pct_estate": 0.0, "pct_trust": 0.0, "pct_nominee": 0.0,
         "pct_own_shares": 0.0, "controller_type": "individual", "controller_name": None, "control_pct": 35.0,
         "control_level": "influence", "group_id": "G:AAA", "group_head_type": "company", "group_head_name": GROUP_HEAD,
         "group_size": 2, "free_float_pct": ff, "market_cap": 5.55e7, "source_url": "https://cdn.cse.lk/r.pdf"}
        for d, ff in ((OLD, 52.1234), (NEW, 63.719))] + [
        {"session_date": NEW, "code": "BBB", "report_status": "ok", "table_status": "verified", "top20_pct": 90.0,
         "group_id": "G:AAA", "group_size": 2, "free_float_pct": 40.0}])
    put("cse_ownership", "models.cse_ownership_detail", [
        {"session_date": NEW, "code": "AAA", "name": "AAA PLC", "report_status": "ok", "controller_key": "ZYXWVUT",
         "controller_name": PERSON, "controller_type": "individual", "control_pct": 35.0, "control_level": "influence",
         "chain": f"AAA <- {PERSON}", "group_key": "ZYXWVUT", "group_name": PERSON, "market_cap": 424242.17}])
    put("cse_ownership", "models.cse_holding", [
        {"report_id": 7, "share_class": "N", "row_no": 1, "rank": 1, "period_date": OLD, "code": "AAA", "symbol": "AAA.N0000",
         "name_as_filed": PERSON, "shares": 424242.17, "pct": 35.0, "fraction": 0.35, "owner_key": "ZYXWVUT",
         "owner_name": PERSON, "owner_type": "individual", "owner_symbol": "", "via": "", "rule": "",
         "table_status": "verified", "source_url": "https://cdn.cse.lk/r.pdf", "as_of": NEW}])

    # Savings education (monthly data): the latest complete month is the first of last month.
    month = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    put("lk_savings_compare", "models.savings_rates", [
        {"month": month, "fd_rate_pct": 13.5791, "fd_series": "AWNFDR", "bill_published_pct": 9.5, "bill_rate_pct": 9.5,
         "cpi": 400.0, "cpi_base": "2021", "inflation_yoy": 0.05, "fd_tax_pct": 10.0}])
    summary = []
    for instrument, ahead in (("fd", 61), ("tbill", 36)):
        for basis in (("nominal", "nominal_after_tax", "real", "real_after_tax") if instrument == "fd" else ("nominal", "real")):
            summary.append({"horizon_years": 1, "instrument": instrument, "basis": basis, "n_periods": 97,
                            "first_start": "2003-01-01", "last_start": "2011-01-01",
                            "n_ahead": None if "after_tax" in basis else ahead, "n_above_start": 50,
                            "median_value": 108000.0, "best_value": 123456.789, "best_start": "2005-01-01",
                            "worst_value": 95000.0, "worst_start": "2008-01-01", "median_annual": 0.08,
                            "best_annual": 0.23456789, "worst_annual": -0.05})
    put("lk_savings_compare", "models.savings_summary", summary)

    # A reference version beside each current one: the site shows only current versions, to everyone.
    put("lk_savings_compare", "models.savings_rates", [
        {"month": month, "fd_rate_pct": 97.79, "fd_series": "AWNFDR", "bill_published_pct": 96.69, "bill_rate_pct": 96.69,
         "cpi": 400.0, "cpi_base": "2021", "inflation_yoy": 0.05, "fd_tax_pct": 10.0}], version="0.9.0")
    put("bond_ns_curve", "models.bond_curve_fit", [
        {"obs_date": NEW, "beta0": 12.0, "beta1": -3.0, "beta2": 1.0, "lambda_years": 2.82, "n_quotes": 2,
         "rmse_bp": 97.79, "n_trades": 0}], version="0.9.0")
    put("cse_total_returns", "models.cse_total_return", [
        {"symbol": "AAA.N0000", "session_date": NEW, "close": 55.5, "share_factor": 1.0, "dividend": 0.0, "events": "",
         "tri": 1.0, "tr_1w": 0.9561}], version="0.9.0")
    put("bond_execution_gap", "models.bond_execution_gap", [
        {"obs_date": NEW, "gap_bp": 96.69, "n": 9, "window_days": 20}], version="0.9.0")
    conn.commit()

    # What each model's data looks like in an API response (raw) and on a page (formatted, as lib/format.ts does).
    return {
        "today": TODAY.isoformat(), "new": NEW.isoformat(), "old": OLD.isoformat(), "mid": MID.isoformat(),
        "ancient": ANCIENT.isoformat(),
        # the yield curve's history beyond its 30-day recent window (API: the fit's error; page: the residual)
        "recent_window": {"bond_ns_curve": {"api": ["13.1313", "10.0391"], "page": ["63.9"]}},
        "models": {
            "bond_ns_curve": {"new": {"api": ["12.12", "10.0571"], "page": ["10.0571"]},
                              "old": {"api": ["11.11", "10.0461"], "page": []}},
            "bond_rv_zscores": {"new": {"api": ["7.7731", "5.5521"], "page": ["+7.77", "+5.55"]},
                                "mid": {"api": ["2.2221", "1.1121"], "page": ["+2.22", "+1.11"]},
                                "old": {"api": ["6.6641", "4.4411"], "page": ["+6.66", "+4.44"]}},
            "bond_execution_gap": {"new": {"api": ["33.37"], "page": ["+33.4 bp"]}, "old": {"api": ["22.27"], "page": []}},
            "bond_carry": {"new": {"api": ["88.81"], "page": ["+88.8"]}, "old": {"api": ["77.71"], "page": ["+77.7"]}},
            "cse_market_tape": {"new": {"api": ["222000000"], "page": ["Rs 222.0 mn"]}, "old": {"api": ["111000000"], "page": []}},
            "cse_security_metrics": {"new": {"api": ["66.6"], "page": ["66.60"]}, "old": {"api": [], "page": []}},
            # free education: everyone sees it (the latest deposit rate, and a count in the summary table)
            "lk_savings_compare": {"new": {"api": ["13.5791", "123456.789"], "page": ["13.58%", "61 of 97"]},
                                   "old": {"api": [], "page": []}},
            "cse_corporate_actions": {"new": {"api": ["8.7654"], "page": ["Rs 8.7654 per share"]},
                                      "old": {"api": [], "page": []}},
            "cse_total_returns": {"new": {"api": ["0.031415"], "page": ["+3.14%"]}, "old": {"api": [], "page": []}},
            # free company figures: the latest P/E (shares list and share page); free ownership: the latest free float
            # and the group head, a company (an individual is never named)
            "cse_fundamentals": {"new": {"api": ["87.6543"], "page": ["87.7"]}, "old": {"api": [], "page": []}},
            "cse_ownership": {"new": {"api": ["63.719", "Leakcheck Holdings"], "page": ["63.7%", "Leakcheck Holdings"]},
                              "old": {"api": [], "page": []}},
        },
        # the bond page's own analysis (formatted as that page shows it): Pro's convexity, Plus's latest z-score
        "bond_page": {"bond_carry": {"new": ["47.3"], "old": ["36.2"]},
                      "bond_rv_zscores": {"new": ["+7.77"], "mid": ["+2.22"], "old": ["+6.66"]}},
        # the weekly bond e-mail (as /email/bonds shows it): Plus's z-scores (no delayed preview in an e-mail) and
        # Pro's carry range and funding rate
        "email_bonds": {"bond_rv_zscores": ["+7.77", "+6.66", "+2.22"], "bond_carry": ["+120 to +120 bp", "9.05%"]},
        # reference versions and unpublished statistics: never shown to anyone, raw or formatted
        "never": ["97.79", "97.8 bp", "96.69", "96.7 bp", "31.4159", "31.42", "0.9561", "+95.61%",
                  # the unpublished ownership tables: an individual's name, and a number only they carry
                  "Zyxwvut", "ZYXWVUT", "424242", "424,242"],
    }


def main() -> int:
    admin = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'drop database if exists "{DB_NAME}" with (force)')
        c.execute(f'create database "{DB_NAME}"')
    url = psycopg.conninfo.make_conninfo(admin, dbname=DB_NAME)
    conn = psycopg.connect(url, row_factory=dict_row)
    db.migrate(conn)
    conn.execute("alter role web_reader with login")
    password = os.environ.get("WEB_READER_PASSWORD")
    if password:
        conn.execute(psycopg.sql.SQL("alter role web_reader with password {}").format(psycopg.sql.Literal(password)))
    markers = seed(conn)
    MARKERS.write_text(json.dumps(markers, indent=2) + "\n")
    parts = psycopg.conninfo.conninfo_to_dict(url)
    secret = f":{quote(password, safe='')}" if password else ""
    print(f"postgresql://web_reader{secret}@{parts.get('host', 'localhost')}:{parts.get('port', 5432)}/{DB_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
