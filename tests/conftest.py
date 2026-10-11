"""Shared test fixtures.

Database tests need a Postgres server. Point TEST_DATABASE_URL at a database the tests may use to CREATE and DROP
throwaway databases (e.g. postgresql://postgres@127.0.0.1:54321/postgres). Without it, database tests are skipped,
never silently passed.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from data_platform.core import db as dbmod
from data_platform.core.rawstore import LocalRawStore

FIXTURES = Path(__file__).parent / "fixtures"


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
