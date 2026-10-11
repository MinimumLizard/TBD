"""bond_identity: how a quote row is tied to a bond, on hand-made cases and on the real fixture files."""
from __future__ import annotations

import datetime as dt

import pytest

from data_platform.models._lib import bond_workspace as ws


def _quote(label, maturity, coupon, bid=10.2, offer=10.0, printed=None):
    return {"series_label": label, "printed_label": printed or label, "maturity_date": dt.date.fromisoformat(maturity),
            "coupon_pct": coupon, "bid_yield": bid, "offer_yield": offer}


@pytest.fixture
def lookup():
    conn = ws.open_workspace()
    ws.upsert_bond(conn, "LKB00530H016", 10.0, "2030-08-15", 5, "2026-01-01", series_label="10.00%2030A")
    ws.upsert_bond(conn, "LKB01533A154", 11.2, "2033-01-15", 15, "2026-01-01", series_label="11.20%2033")
    ws.upsert_bond(conn, "LKB00529L150", 11.0, "2029-12-15", 5, "2026-01-01", series_label="11.00%2029B")
    ws.upsert_bond(conn, "LKB00629I154", 11.0, "2029-12-15", 6, "2026-01-01", series_label="11.00%2029A")
    ws.upsert_bond(conn, "LKB00731E153", None, "2031-05-15", 7, "2026-01-01")      # known only from a volume file
    return ws.bond_lookup(conn)


def test_series_label_decides_first(lookup):
    assert ws.resolve_isin(lookup, _quote("10.00%2030A", "2030-08-15", 10.0)) == ("LKB00530H016", "label")


def test_a_missing_series_letter_is_tolerated_only_when_unambiguous(lookup):
    assert ws.resolve_isin(lookup, _quote("11.20%2033A", "2033-01-15", 11.2)) == ("LKB01533A154", "label-no-letter")
    # two 11.00%2029 bonds: the letter-free label is ambiguous, and so is the maturity -> left unresolved
    assert ws.resolve_isin(lookup, _quote("11.00%2029C", "2029-12-15", 11.0)) == (None, "unresolved")


def test_maturity_needs_an_agreeing_coupon(lookup):
    assert ws.resolve_isin(lookup, _quote("9.00%2031A", "2031-05-15", 9.0)) == ("LKB00731E153", "maturity+coupon")
    assert ws.resolve_isin(lookup, _quote(None, "2030-08-15", 12.0)) == (None, "unresolved")


def test_only_real_two_way_single_coupon_quotes_get_a_synthetic_key():
    assert ws.admissible_without_isin(_quote("11.25%2026A", "2026-12-15", 11.25, 9.3, 9.1))
    assert not ws.admissible_without_isin(_quote("12.00%9.00%2027A", "2027-12-15", 12.0, 13.0, 12.0))  # step coupon
    assert not ws.admissible_without_isin(_quote("11.25%2026A", "2026-12-15", 11.25, 13.0, 12.0))      # 100 bp wide
    assert not ws.admissible_without_isin(_quote("11.25%2026A", "2026-12-15", 11.25, 9.3, None))        # one-way
    assert not ws.admissible_without_isin(_quote("11.25%2026A", "2026-12-15", 11.25, 9.1, 9.3))         # crossed


@pytest.mark.db
def test_fixture_files_resolve_and_trace_back_to_their_file(bond_models):
    conn = bond_models
    quotes = conn.execute("select * from models.bond_quotes").fetchall()
    daily_sha = conn.execute("select raw_sha256 from bonds.source_files where kind = 'daily_summary'").fetchone()
    assert len(quotes) == 53                                     # of 92 rows: step-coupon and administered left out
    assert {q["raw_sha256"] for q in quotes} == {daily_sha["raw_sha256"]}
    assert {q["resolved_by"] for q in quotes} <= {"label", "label-no-letter", "maturity+coupon", "synthetic"}
    by_label = {q["isin"] for q in quotes if q["resolved_by"] == "label"}
    assert "LKB00530H016" in by_label                           # 10.00%2030A, named in the 2026-01-12 auction
    for q in quotes:
        assert q["mid_yield"] == pytest.approx((q["bid_yield"] + q["offer_yield"]) / 2)
    synthetic = conn.execute("select isin, series_label from models.bond_reference where isin like 'SYN:%'").fetchall()
    assert synthetic and all("%" in s["series_label"] and s["series_label"].count("%") == 1 for s in synthetic)


@pytest.mark.db
def test_nothing_after_as_of_is_used(bond_facts):
    from conftest import NO_LEGACY_SEED
    from data_platform.models.framework import Inputs, load_manifest
    from data_platform.models.bond_identity.compute import compute

    m = load_manifest("bond_identity")
    v = m.current.model_copy(update={"parameters": NO_LEGACY_SEED["bond_identity"]})
    out = compute(Inputs(bond_facts, m, v, owners={}), dt.date(2026, 8, 30))
    assert out["models.bond_quotes"] == []                       # the only daily summary is for 2026-08-31


@pytest.mark.db
def test_version_1_refuses_to_run_without_the_old_bond_list(bond_facts):
    from conftest import run_models
    with pytest.raises(RuntimeError, match="legacy_reference"):
        run_models(bond_facts, ["bond_identity"])
