"""Migration reconciliation against the real old data. Slow, and needs local inputs, so it only runs when pointed
at them (it is run before every cut-over decision, and its report is committed under docs/migration/):

    LEGACY_NS_DB=<Nelson-Siegel clone>/data/sgcp.sqlite  LEGACY_PDMO_ARCHIVE=<archive>/pdmo \
    LEGACY_CSE_REPO=<CSE clone>  LEGACY_CSE_CHART_ARCHIVE=<archive>/cse_chart_2026-10-11 \
    LEGACY_NS_CODE=<Nelson-Siegel clone at 1c33084>  pytest -m legacy
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from data_platform.migration import bonds

pytestmark = pytest.mark.legacy


@pytest.mark.db
def test_bond_history_migrates_and_reconciles_exactly(conn, store):
    old_db, archive = os.environ.get("LEGACY_NS_DB"), os.environ.get("LEGACY_PDMO_ARCHIVE")
    if not (old_db and archive):
        pytest.skip("LEGACY_NS_DB / LEGACY_PDMO_ARCHIVE not set")
    first = bonds.load(conn, store, Path(old_db), Path(archive), None, dt.date.today())
    assert first.get("parse_failed", 0) == 0 and first.get("missing_original", 0) == 0
    report = bonds.reconcile(conn, Path(old_db))
    assert report["ok"], report
    again = bonds.load(conn, store, Path(old_db), Path(archive), None, dt.date.today())
    assert again["rows_added"] == 0                       # repeatable


@pytest.mark.db
def test_cse_history_migrates_and_reconciles_exactly(conn, store):
    from data_platform.migration import cse

    repo, chart = os.environ.get("LEGACY_CSE_REPO"), os.environ.get("LEGACY_CSE_CHART_ARCHIVE")
    if not (repo and chart):
        pytest.skip("LEGACY_CSE_REPO / LEGACY_CSE_CHART_ARCHIVE not set")
    cse.load(conn, store, Path(repo), Path(chart))
    report = cse.reconcile(conn, Path(repo))
    assert report["ok"], report
    assert report["gap_2026_10_05_filled_rows"] > 250          # the session the old daily job missed
    before = conn.execute("select count(*) n from ops.raw_fetches").fetchone()["n"]
    cse.load(conn, store, Path(repo), Path(chart))
    assert conn.execute("select count(*) n from ops.raw_fetches").fetchone()["n"] == before   # repeatable


@pytest.mark.db
def test_bond_models_version_1_reproduce_the_old_tool(conn, store):
    """Phase 3 parity: every bond model's version 1 against the old database, and against the old code for the
    calculations the old tool never stored. Set LEGACY_NS_CODE to a clone of Nelson-Siegel at 1c33084."""
    from data_platform.migration import parity

    old_db, archive = os.environ.get("LEGACY_NS_DB"), os.environ.get("LEGACY_PDMO_ARCHIVE")
    old_code = os.environ.get("LEGACY_NS_CODE")
    if not (old_db and archive and old_code):
        pytest.skip("LEGACY_NS_DB / LEGACY_PDMO_ARCHIVE / LEGACY_NS_CODE not set")
    bonds.load(conn, store, Path(old_db), Path(archive), None, dt.date.today())
    sha = bonds.archive_legacy_file(conn, store, Path(old_db), "data/sgcp.sqlite")
    assert bonds.load_legacy_reference(conn, Path(old_db), sha)["ok"]
    report = parity.bonds_parity(conn, Path(old_db), Path(old_code))
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]


@pytest.mark.db
def test_cse_models_version_1_reproduce_the_old_terminal(conn, store):
    """Phase 3 parity for the CSE market summary and per-share metrics, against the old terminal's own code."""
    from data_platform.migration import cse, parity_cse

    repo, chart = os.environ.get("LEGACY_CSE_REPO"), os.environ.get("LEGACY_CSE_CHART_ARCHIVE")
    if not (repo and chart):
        pytest.skip("LEGACY_CSE_REPO / LEGACY_CSE_CHART_ARCHIVE not set")
    cse.load(conn, store, Path(repo), Path(chart))
    report = parity_cse.cse_parity(conn, Path(repo))
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]


@pytest.mark.db
def test_cse_corporate_action_facts_reconcile_and_the_models_reproduce_the_old_terminal(conn, store):
    """Phase 3b: the corporate-action caches load from the archive and reconcile with the old folders (repeatably);
    cse_corporate_actions reproduces corporate_actions.csv and the old code; cse_total_returns reproduces the old
    build_tris. Set LEGACY_CA_REPORT to a path to also write the counts-only parity report there."""
    import json

    from data_platform.migration import cse, cse_corporate_actions as ca, parity_cse_corporate_actions as pca

    repo, chart = os.environ.get("LEGACY_CSE_REPO"), os.environ.get("LEGACY_CSE_CHART_ARCHIVE")
    if not (repo and chart):
        pytest.skip("LEGACY_CSE_REPO / LEGACY_CSE_CHART_ARCHIVE not set")
    cse.load(conn, store, Path(repo), Path(chart))
    ca.archive_cache(conn, store, Path(repo))
    first = ca.load_from_archive(conn, store)
    assert first["detail_rows_added"] > 0
    rec = ca.reconcile(conn, Path(repo))
    assert rec["ok"], rec
    again = ca.load_from_archive(conn, store)
    assert again["list_rows_added"] == 0 and again["detail_rows_added"] == 0      # repeatable
    report = pca.ca_parity(conn, Path(repo))
    conn.rollback()
    if os.environ.get("LEGACY_CA_REPORT"):
        Path(os.environ["LEGACY_CA_REPORT"]).write_text(json.dumps(
            {"reconciliation": rec, "parity": report}, indent=2, default=str) + "\n")
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]
