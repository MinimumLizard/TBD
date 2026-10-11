"""The database's second line of defence for the website (migration 0006)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.db


def test_every_platform_table_has_row_level_security(conn):
    missing = conn.execute("""select n.nspname || '.' || c.relname as t from pg_class c
                              join pg_namespace n on n.oid = c.relnamespace
                              where c.relkind = 'r' and n.nspname in ('ops', 'bonds', 'cse', 'models')
                                and not c.relrowsecurity""").fetchall()
    assert missing == []           # a new table in a later migration must enable it too


def test_every_model_output_is_readable_by_the_website_role(conn):
    without = conn.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                              where n.nspname = 'models' and c.relkind = 'r'
                                and c.relname not in ('runs', 'revisions')
                                and not exists (select 1 from pg_policy p where p.polrelid = c.oid
                                                and p.polname = 'web_read')""").fetchall()
    assert without == []


def test_the_website_role_reads_outputs_only_and_writes_nothing(conn):
    conn.execute("set role web_reader")
    try:
        conn.execute("select count(*) from models.bond_curve_fit").fetchone()
        for forbidden in ("select * from bonds.quotes", "select * from ops.raw_fetches", "select * from models.runs",
                          "insert into models.model_stats values ('x', '1.0.0', 'k', 1, 1, 1)"):
            with pytest.raises(Exception, match="permission denied"):
                conn.execute("savepoint s")
                try:
                    conn.execute(forbidden)
                finally:
                    conn.execute("rollback to savepoint s")
    finally:
        conn.execute("reset role")


def test_any_other_role_sees_no_rows_even_if_granted(conn):
    run = conn.execute("insert into models.runs (model, method_version, code_version) values ('m', '1.0.0', 't') "
                       "returning run_id").fetchone()["run_id"]
    conn.execute("insert into models.model_stats values ('m', '1.0.0', 'k', 1.0, 1, %s)", (run,))
    conn.execute("""do $$ begin
                      if not exists (select 1 from pg_roles where rolname = 'tbd_test_browser') then
                        create role tbd_test_browser nologin;
                      end if; end $$""")
    conn.execute("grant usage on schema models to tbd_test_browser")
    conn.execute("grant select on models.model_stats to tbd_test_browser")
    conn.execute("set role tbd_test_browser")
    try:
        assert conn.execute("select count(*) n from models.model_stats").fetchone()["n"] == 0
    finally:
        conn.execute("reset role")
        conn.execute("revoke all on models.model_stats from tbd_test_browser")
        conn.execute("revoke all on schema models from tbd_test_browser")
