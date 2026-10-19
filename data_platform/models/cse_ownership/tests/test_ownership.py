"""cse_ownership: the ported table parser and owner rules on a synthetic report (tests/fixtures/cse/reports: every
company, fund and person in it is made up), the model end to end, what may be published, and the point-in-time
rule. The exactness of the port is proven against the old code by the legacy parity test."""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import FIXTURES, run_models
from data_platform.collectors.cse import collector as cse
from data_platform.collectors.cse.reports import store_report, store_text
from data_platform.core import db
from data_platform.jobs import reviews
from data_platform.models._lib import cse_names as names
from data_platform.models._lib import cse_ownership as own
from data_platform.models._lib import cse_tables as tables
from data_platform.models.cse_ownership import compute as m

TEXT = (FIXTURES / "cse" / "reports" / "synthetic_interim.txt").read_text()
NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)
D1, D2 = dt.date(2026, 10, 1), dt.date(2026, 10, 2)
PERSON = "Testperson"            # the made-up individual in the fixture


# --- the ported parser and rules ---------------------------------------------------------------------------------

def test_the_top20_table_is_found_checked_and_the_directors_table_is_not_merged():
    best = tables.best_tables(tables.find_tables(TEXT), {"N": 100e6, "X": None})
    t = best["N"]
    assert t.status == "verified" and len(t.rows) == 8
    assert t.stated_total_pct == 83.5 and t.period_total == 100e6
    assert t.rows[0]["name"] == "Example Holdings (Private) Limited" and t.rows[0]["shares"] == 55e6


def test_a_table_whose_rows_disagree_with_the_share_count_is_not_used():
    assert tables.best_tables(tables.find_tables(TEXT), {"N": 250e6, "X": None})["N"].status == "unverified"


@pytest.mark.parametrize("filed, owner, typ, via", [
    ("Bank of Ceylon A/C Sample Growth Fund", "Sample Growth Fund", "institution", "Bank of Ceylon"),
    ("Seylan Bank PLC/Example Traders (Pvt) Ltd", "Example Traders (Pvt) Ltd", "company", "Seylan Bank PLC"),
    ("DEUTSCHE BANK AG AS TRUSTEE TO SAMPLE INCOME FUND", "SAMPLE INCOME FUND", "institution",
     "DEUTSCHE BANK AG AS TRUSTEE TO"),
    ("SAMPLE ASSURANCE PLC-UNIVERSAL LIFE FUND", "SAMPLE ASSURANCE PLC-UNIVERSAL LIFE FUND", "institution", ""),
    ("ESTATE OF LATE A. SAMPLE", "ESTATE OF LATE A. SAMPLE", "estate", ""),
    ("Mr. Q. Testperson & Mrs. R. Testperson", "Mr. Q. Testperson & Mrs. R. Testperson", "joint", ""),
    ("Mr. Q. Testperson", "Mr. Q. Testperson", "individual", ""),
])
def test_beneficial_owner_rules(filed, owner, typ, via):
    e = names.resolve(filed, {}, {})
    assert (e.name, e.type, e.via) == (owner, typ, via)


def test_a_listed_holder_is_recognised_through_its_accounts():
    listed = names.listed_index([{"symbol": "SLP.N0000", "name": "SAMPLE LISTED PLC"}])
    for filed in ("SAMPLE LISTED PLC", "Sample Listed PLC A/C No. 2", "SAMPLE LISTED LIMITED"):
        assert (names.resolve(filed, listed, {}).type, names.resolve(filed, listed, {}).symbol) == ("listed", "SLP")


def test_individuals_merge_only_on_exact_names_or_a_confirmed_alias():
    assert names.key_of("Mr. Q. R. Testperson") == names.key_of("MR. Q.R. TESTPERSON")
    assert names.key_of("Mr. Q.R. Testperson") != names.key_of("Mr. Q.S. Testperson")
    aliases = names.load_aliases({"aliases": {"Q.R. Testperson": {"variants": ["Mr. Q.S. Testperson"],
                                                                  "type": "individual"}}})
    e = names.resolve("Mr. Q.S. Testperson", {}, aliases)
    assert (e.name, e.type, e.rule) == ("Q.R. Testperson", "individual", "alias")


def test_a_parent_link_needs_its_evidence():
    with pytest.raises(ValueError, match="needs 'quote'"):
        own.load_links({"parents": {"X Ltd": {"owner": "Y PLC", "source": "https://cdn.cse.lk/a.pdf"}}})
    with pytest.raises(ValueError, match="pct"):
        own.load_links({"parents": {"X Ltd": {"owner": "Y PLC", "source": "s", "quote": "q", "pct": 150}}})


def test_only_companies_funds_and_the_state_are_ever_named():
    market = own.Market("2026-10-01", {"SLP": "SAMPLE LISTED PLC"}, {}, {})
    assert m.public_name("LISTED:SLP", "listed", "SLP", market) == "SAMPLE LISTED PLC"
    assert m.public_name("Example Holdings (Private) Limited", "company", "", market) == "Example Holdings (Private) Limited"
    assert m.public_name("Employees Trust Fund", "institution", "", market) == "Employees Trust Fund"
    for name, typ in (("Mr. Q. Testperson", "individual"), ("Mr. Q. Testperson & Mrs. R. Testperson", "joint"),
                      ("Testperson Family Trust", "trust"), ("ESTATE OF LATE A. SAMPLE", "estate"),
                      ("Mr. Q. Testperson Holdings Ltd", "company"), ("QRS", "company"), ("Sample Nominee", "nominee")):
        assert m.public_name(name, typ, "", market) is None, name


# --- the model end to end -----------------------------------------------------------------------------------------

def _fetch(conn, store, endpoint, body, params=None):
    return db.record_fetch(conn, store, source_id="cse_api", method="POST", url=f"https://www.cse.lk/api/{endpoint}",
                           params=params or {}, http_status=200, body=body, content_type="application/json",
                           fetched_at=NOW)


def add_session(conn, store, day: dt.date, issued: float = 100e6, close: float = 50.0):
    fid, _ = _fetch(conn, store, "allSecurityCode", f"[{day}]".encode())
    cse.store(conn, "cse.security_list", [
        {"session_date": day, "symbol": "TESTCO.N0000", "stock_id": 1, "name": "TESTCO PLC", "active": 1},
        {"session_date": day, "symbol": "SLP.N0000", "stock_id": 2, "name": "SAMPLE LISTED PLC", "active": 1}],
        ["session_date", "symbol"], fid, NOW)
    cse.store(conn, "cse.company_info_daily", [{"session_date": day, "symbol": "TESTCO.N0000",
                                                "quantity_issued": issued, "market_cap": issued * close}],
              ["session_date", "symbol"], fid, NOW)
    cse.store_prices(conn, [
        {"session_date": day, "symbol": "TESTCO.N0000", "source": "daily", "close": close, "market_cap": issued * close},
        {"session_date": day, "symbol": "SLP.N0000", "source": "daily", "close": 10.0, "market_cap": 1e9}], fid, NOW)


def add_report(conn, store, report_id: int, text: str, uploaded: dt.datetime, period=dt.date(2026, 6, 30)):
    sha = store_text(conn, store, text.encode())
    fid, _ = _fetch(conn, store, "financials", f"{report_id}".encode(), {"symbol": "TESTCO.N0000"})
    store_report(conn, {"report_id": report_id, "code": "TESTCO", "symbol": "TESTCO.N0000", "kind": "quarterly",
                        "title": "Interim Financial Statements for the Quarter ended 30th June 2026",
                        "period_date": period, "uploaded_at": uploaded, "url": f"https://cdn.cse.lk/{report_id}.pdf",
                        "pages": 3, "words": len(text.split()), "status": "ok", "pdf_sha256": None,
                        "text_sha256": sha, "extracted_by": "test", "fetch_id": fid, "fetched_at": uploaded})


def seed(conn, store, private_aliases: dict | None = None):
    add_session(conn, store, D1)
    add_report(conn, store, 100, TEXT, dt.datetime(2026, 8, 1, 6, 0, tzinfo=dt.timezone.utc))
    reviews.store_ownership(conn, {"aliases": {}, "parents": {}}, "public",
                            {"aliases": private_aliases or {}, "parents": {}}, "private" if private_aliases else None,
                            "test", commit=False)
    conn.commit()


def published(conn):
    return {(r["session_date"], r["code"]): r for r in conn.execute("select * from models.cse_company_ownership")}


@pytest.mark.db
def test_the_company_view_names_no_individual_and_the_holdings_keep_every_row(conn, store):
    seed(conn, store)
    run_models(conn, ["cse_ownership"])
    rows = published(conn)
    t = rows[(D1, "TESTCO")]
    assert t["report_status"] == "ok" and t["table_status"] == "verified" and t["top20_pct"] == 83.5
    assert (t["pct_company"], t["pct_institution"], t["pct_listed"], t["pct_individual"], t["pct_joint"]) == \
        (60.0, 11.5, 7.0, 4.0, 1.0)              # 55 + 3 + 2 unlisted companies; 8 + 3.5 funds
    assert (t["controller_type"], t["controller_name"], t["control_level"]) == \
        ("company", "Example Holdings (Private) Limited", "controlled")
    assert t["group_head_name"] == "Example Holdings (Private) Limited" and t["group_id"] == "G:TESTCO"
    assert t["free_float_pct"] == 45.0          # 100 - the 55 % block; every other block is under 10 %
    assert rows[(D1, "SLP")]["report_status"] == "no_report" and rows[(D1, "SLP")]["top20_pct"] is None
    for r in rows.values():
        assert PERSON not in " ".join(str(v) for v in r.values())
    holdings = conn.execute("select * from models.cse_holding order by row_no").fetchall()
    assert len(holdings) == 8 and holdings[2]["owner_type"] == "listed" and holdings[2]["owner_symbol"] == "SLP"
    assert holdings[1]["owner_name"] == "Sample Growth Fund" and holdings[1]["via"] == "Bank of Ceylon"
    assert holdings[0]["fraction"] == pytest.approx(0.55)


@pytest.mark.db
def test_the_tables_that_name_people_are_closed_to_the_website(conn, store):
    for table in ("models.cse_holding", "models.cse_ownership_detail"):
        assert not conn.execute("select has_table_privilege('web_reader', %s, 'select') ok", (table,)).fetchone()["ok"]
    assert conn.execute("select has_table_privilege('web_reader', 'models.cse_company_ownership', 'select') ok"
                        ).fetchone()["ok"]


@pytest.mark.db
def test_a_private_alias_merges_one_persons_accounts(conn, store):
    seed(conn, store, {"Q. Testperson": {"variants": ["Mr. Q. Testperson & Mrs. R. Testperson"], "type": "individual"}})
    run_models(conn, ["cse_ownership"])
    owners = {r["owner_key"] for r in conn.execute("select owner_key from models.cse_holding where owner_type = 'individual'")}
    assert owners == {names.key_of("Q. Testperson")}
    assert published(conn)[(D1, "TESTCO")]["pct_individual"] == 5.0


@pytest.mark.db
def test_a_session_never_changes_when_later_sessions_and_reports_arrive(conn, store):
    """Point in time: the row for D1 is computed from what was known on D1. A new session with a new share count and
    a report uploaded after D1 change only D2's row."""
    seed(conn, store)
    run_models(conn, ["cse_ownership"])
    before = published(conn)
    add_session(conn, store, D2, issued=250e6)               # a share issue: the old table no longer checks out
    later = TEXT.replace("55,000,000      55.00", "55,000,000      22.00")
    add_report(conn, store, 101, later, dt.datetime(2026, 10, 2, 5, 0, tzinfo=dt.timezone.utc),
               period=dt.date(2026, 9, 30))
    conn.commit()
    run_models(conn, ["cse_ownership"])
    after = published(conn)
    for k, v in before.items():
        assert {c: x for c, x in after[k].items() if c != "run_id"} == {c: x for c, x in v.items() if c != "run_id"}
    assert after[(D2, "TESTCO")]["report_id"] == 101                 # the report uploaded on D2 counts from D2
    assert after[(D2, "TESTCO")]["table_status"] == "unverified" and after[(D2, "TESTCO")]["top20_pct"] is None
    assert conn.execute("select count(*) n from models.revisions where table_name = 'models.cse_company_ownership'"
                        ).fetchone()["n"] == 0


@pytest.mark.db
def test_an_as_of_look_equals_the_full_run_up_to_that_day(conn, store):
    from data_platform.migration.parity import run_chain

    seed(conn, store)
    add_session(conn, store, D2)
    conn.commit()
    full = run_chain(conn, ["cse_ownership"], pick=lambda mf: mf.current)["models.cse_company_ownership"]
    past = run_chain(conn, ["cse_ownership"], pick=lambda mf: mf.current, as_of=D1)["models.cse_company_ownership"]
    assert past == [r for r in full if r["session_date"] <= D1] and len(past) == 2
