"""Shared test fixtures, for tests/ and for the tests inside each model plug-in folder (data_platform/models/*/tests).

Database tests need a Postgres server. Point TEST_DATABASE_URL at a database the tests may use to CREATE and DROP
throwaway databases (e.g. postgresql://postgres@127.0.0.1:54321/postgres). Without it, database tests are skipped,
never silently passed.
"""
from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from data_platform.core import db as dbmod
from data_platform.core.rawstore import LocalRawStore

FIXTURES = Path(__file__).parent / "tests" / "fixtures"


@pytest.fixture
def store(tmp_path) -> LocalRawStore:
    return LocalRawStore(tmp_path / "raw")


@pytest.fixture
def conn():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_URL not set")
    name = f"tbd_t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    url = psycopg.conninfo.make_conninfo(admin_url, dbname=name)
    connection = psycopg.connect(url, row_factory=dict_row)
    dbmod.migrate(connection)
    try:
        yield connection
    finally:
        connection.close()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'drop database "{name}" with (force)')


# The five real PDMO files in tests/fixtures/pdmo, stored exactly as the live collector stores them.
PDMO_FIXTURE_FILES = [
    ("bond_issuance", "announcement_2026-08-25.pdf", dt.date(2026, 8, 25)),
    ("bond_auction", "auction_2026-01-12_wrapped.pdf", dt.date(2026, 1, 12)),
    ("volumes", "volumes_2025-12-19_typo_title.xls", dt.date(2025, 12, 19)),
    ("trade_summary", "trade_summary_2026-08-28.pdf", dt.date(2026, 8, 28)),
    ("daily_summary", "daily_summary_2026-08-31.xls", dt.date(2026, 8, 31)),
]


@pytest.fixture
def bond_facts(conn, store):
    from data_platform.collectors.pdmo import index
    from data_platform.collectors.pdmo.collector import store_file

    now = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.timezone.utc)
    for kind, name, label in PDMO_FIXTURE_FILES:
        body = (FIXTURES / "pdmo" / name).read_bytes()
        url = f"https://www.treasury.gov.lk/api/file/{name}"
        fetch_id, sha = dbmod.record_fetch(conn, store, source_id="pdmo", method="GET", url=url, params={},
                                           http_status=200, body=body, content_type=None, fetched_at=now)
        store_file(conn, entry=index.IndexEntry(url, kind, label, label), index_year=label.year, fetch_id=fetch_id,
                   sha256=sha, fetched_at=now, body=body)
    conn.commit()
    return conn


def run_models(conn, names, parameters: dict | None = None):
    """Run models (every active version) in dependency order, with optional parameter overrides per model.
    Returns {model: RunResult}."""
    from data_platform.models import registry
    from data_platform.models.framework import output_owners, run_version

    manifests = registry.load_all()
    owners = output_owners()
    results = {}
    for name in registry.order(manifests):
        if name not in names:
            continue
        for v in manifests[name].active_versions:
            v = v.model_copy(update={"parameters": {**v.parameters, **(parameters or {}).get(name, {})}})
            results[name] = run_version(conn, manifests[name], v, code_version="test", owners=owners)
    return results


# Bond models on the fixture files. bond_identity version 1 normally starts from the old tool's bond list, which a
# test database does not have, so tests run it from the files alone.
BOND_MODELS = ["bond_identity", "bond_ns_curve", "bond_rv_zscores", "bond_liquidity", "bond_execution_gap",
               "bond_carry"]
NO_LEGACY_SEED = {"bond_identity": {"legacy_reference_sha256": None}}


@pytest.fixture
def bond_models(bond_facts):
    run_models(bond_facts, BOND_MODELS, NO_LEGACY_SEED)
    return bond_facts
