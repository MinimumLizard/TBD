"""Migration reconciliation against the real old data. Slow, and needs local inputs, so it only runs when pointed
at them (it is run before every cut-over decision, and its report is committed under docs/migration/):

    LEGACY_NS_DB=<Nelson-Siegel clone>/data/sgcp.sqlite  LEGACY_PDMO_ARCHIVE=<archive>/pdmo  pytest -m legacy
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
