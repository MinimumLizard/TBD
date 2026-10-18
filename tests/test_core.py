"""Tests for the platform core: raw archive, source register, database guard rails, HTTP client."""
from __future__ import annotations

import datetime as dt

import boto3
import psycopg
import pytest
import requests
from moto import mock_aws

from data_platform.core import db, sources
from data_platform.core.http import FetchError, PoliteClient
from data_platform.core.rawstore import IntegrityError, S3RawStore, key_for, sha256_of, sniff_ext


# --- raw archive ------------------------------------------------------------------------------------------------

def test_local_store_is_content_addressed_and_write_once(store):
    a = store.put(b"hello", "txt")
    again = store.put(b"hello", "txt")
    assert a == again and a.key == key_for(sha256_of(b"hello"), "txt")
    assert store.get(a.sha256, "txt") == b"hello"


def test_local_store_detects_tampering(store):
    obj = store.put(b"original", "txt")
    (store.root / obj.key).write_bytes(b"tampered")
    with pytest.raises(IntegrityError):
        store.get(obj.sha256, "txt")


@mock_aws
def test_s3_store_against_simulator():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="raw")
    s3 = S3RawStore("raw", client)
    obj = s3.put(b'{"a":1}', "json")
    assert s3.exists(obj.sha256, "json")
    assert s3.get(obj.sha256, "json") == b'{"a":1}'
    s3.put(b'{"a":1}', "json")                       # second put of same content: no error, no rewrite
    assert len(client.list_objects_v2(Bucket="raw")["Contents"]) == 1


@pytest.mark.parametrize("data,ctype,ext", [
    (b"%PDF-1.4 ...", None, "pdf"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1", "application/pdf", "xls"),      # the PDMO's "PDF" links that are really .xls
    (b'{"x": 1}', "application/json", "json"),
    (b"<!doctype html>", "text/html", "html"),
])
def test_sniff_ext_trusts_bytes_over_labels(data, ctype, ext):
    assert sniff_ext(data, ctype) == ext


# --- source register --------------------------------------------------------------------------------------------

def test_real_source_register_is_valid():
    loaded = sources.load()
    assert loaded["pdmo"].enabled and loaded["cse_api"].enabled
    for sid, src in loaded.items():
        assert not (src.enabled and src.rights.status == "prohibited"), sid


def test_prohibited_source_cannot_be_enabled(tmp_path):
    bad = tmp_path / "sources.yaml"
    bad.write_text("""
x:
  name: X
  homepage: https://example.com/
  enabled: true
  rights: {status: prohibited, evidence: NC licence, url: https://example.com/terms, checked: 2026-10-11}
  datasets: []
""")
    with pytest.raises(Exception, match="cannot be enabled"):
        sources.load(bad)


def test_a_source_needing_permission_runs_but_blocks_launch():
    """The CSE's terms (found 2026-10-18) need its written permission for commercial use: the collector may run
    for development, but the source is listed as a launch blocker until the permission is on file."""
    assert "cse_api" in sources.launch_blockers()
    assert sources.require_runnable("cse_api").rights.status == "permission_required"


def test_disabled_source_is_not_runnable():
    with pytest.raises(sources.SourceNotRunnable):
        sources.require_runnable("coinmetrics_community")


# --- database -----------------------------------------------------------------------------------------------------

@pytest.mark.db
def test_migrations_are_idempotent(conn):
    assert db.migrate(conn) == []


@pytest.mark.db
def test_fact_tables_refuse_update_and_delete(conn, store):
    fetch_id, digest = db.record_fetch(conn, store, source_id="t", method="GET", url="https://x/", params={},
                                       http_status=200, body=b"{}", content_type="application/json",
                                       fetched_at=dt.datetime.now(dt.timezone.utc))
    conn.commit()
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("update ops.raw_fetches set url = 'https://y/' where fetch_id = %s", (fetch_id,))
    conn.rollback()
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("delete from ops.raw_objects where sha256 = %s", (digest,))
    conn.rollback()


@pytest.mark.db
def test_insert_facts_never_overwrites_and_records_conflicts(conn, store):
    now = dt.datetime.now(dt.timezone.utc)
    fetch_id, _ = db.record_fetch(conn, store, source_id="t", method="GET", url="https://x/", params={},
                                  http_status=200, body=b"[]", content_type=None, fetched_at=now)
    row = {"session_date": dt.date(2026, 10, 9), "source": "daily", "turnover": 1.0, "fetch_id": fetch_id,
           "fetched_at": now}
    assert db.insert_facts(conn, "cse.market_daily", [row], key=["session_date", "source"]) == (1, 0)
    assert db.insert_facts(conn, "cse.market_daily", [row], key=["session_date", "source"]) == (0, 0)
    changed = dict(row, turnover=2.0)
    assert db.insert_facts(conn, "cse.market_daily", [changed], key=["session_date", "source"]) == (0, 1)
    stored = conn.execute("select turnover from cse.market_daily").fetchone()["turnover"]
    assert stored == 1.0                                          # history kept
    conflict = conn.execute("select stored, incoming from ops.value_conflicts").fetchone()
    assert conflict["stored"] == {"turnover": 1.0} and conflict["incoming"] == {"turnover": 2.0}


# --- HTTP client --------------------------------------------------------------------------------------------------

class FakeSession(requests.Session):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)

    def get(self, url, **kw):
        return self.responses.pop(0)

    post = get


def fake_response(status: int, body: bytes, ctype="text/html") -> requests.Response:
    r = requests.Response()
    r.status_code, r._content, r.headers["content-type"] = status, body, ctype
    return r


def test_firewall_challenge_is_an_error_not_content():
    client = PoliteClient(session=FakeSession([fake_response(200, b"<html>sucuri_cloudproxy ...</html>")]),
                          sleep=lambda s: None)
    with pytest.raises(FetchError, match="bot-challenge"):
        client.get("https://www.treasury.gov.lk/web/x")


def test_redirect_left_unfollowed_is_an_error():
    client = PoliteClient(session=FakeSession([fake_response(307, b"")]), sleep=lambda s: None)
    with pytest.raises(FetchError, match="redirect"):
        client.get("https://www.treasury.gov.lk/web/x")


def test_retries_on_server_errors_then_succeeds():
    client = PoliteClient(session=FakeSession([fake_response(503, b""), fake_response(200, b"ok", "text/plain")]),
                          sleep=lambda s: None)
    assert client.get("https://example.com/").body == b"ok"


def test_204_is_an_empty_body():
    client = PoliteClient(session=FakeSession([fake_response(204, b"")]), sleep=lambda s: None)
    assert client.post("https://www.cse.lk/api/getAnnouncementById", {"announcementId": 1}).status == 204


@pytest.mark.db
def test_a_blank_incoming_value_is_not_a_conflict(conn, store):
    now = dt.datetime.now(dt.timezone.utc)
    fetch_id, _ = db.record_fetch(conn, store, source_id="t", method="GET", url="https://x/", params={},
                                  http_status=200, body=b"[1]", content_type=None, fetched_at=now)
    row = {"session_date": dt.date(2026, 10, 9), "source": "daily", "turnover": 1.0, "fetch_id": fetch_id,
           "fetched_at": now}
    db.insert_facts(conn, "cse.market_daily", [row], key=["session_date", "source"])
    assert db.insert_facts(conn, "cse.market_daily", [dict(row, turnover=None)], key=["session_date", "source"]) == (0, 0)


# --- backups ------------------------------------------------------------------------------------------------------

@pytest.mark.db
def test_replicate_copies_every_object_once_and_verify_detects_damage(conn, store, tmp_path):
    from data_platform.core.rawstore import AlreadyExists, LocalRawStore
    from data_platform.jobs import backup

    second = LocalRawStore(tmp_path / "second")
    for i in range(3):
        db.record_fetch(conn, store, source_id="t", method="GET", url=f"https://x/{i}", params={}, http_status=200,
                        body=f"payload {i}".encode(), content_type="text/plain",
                        fetched_at=dt.datetime.now(dt.timezone.utc))
    conn.commit()
    assert backup.replicate(conn, store, second) == {"copied": 3, "already_present": 0}
    assert backup.replicate(conn, store, second) == {"copied": 0, "already_present": 3}
    today = dt.date(2026, 10, 11)
    with pytest.raises(IntegrityError, match="no database export"):
        backup.verify(conn, [store, second], today, seed=1)            # no recent export: a failure, not a pass
    backup.export("unused", [store, second], today - dt.timedelta(days=1), dump_fn=lambda url: b"PGDMP dump")
    assert backup.verify(conn, [store, second], today, seed=1)["checked"] == 3
    victim = next((tmp_path / "second" / "raw").rglob("*.txt"))
    victim.write_bytes(b"bit rot")
    with pytest.raises(IntegrityError):
        backup.verify(conn, [store, second], today, seed=1)
    second.put_named("exports/db/2026-10-11.dump", b"dump")
    with pytest.raises(AlreadyExists):
        second.put_named("exports/db/2026-10-11.dump", b"other")       # write-once


@pytest.mark.db
def test_export_produces_a_restorable_dump(conn, tmp_path):
    import shutil

    from data_platform.core.rawstore import LocalRawStore
    from data_platform.jobs import backup

    if not shutil.which("pg_dump"):
        pytest.skip("pg_dump not installed")
    import os

    url = psycopg.conninfo.make_conninfo(os.environ["TEST_DATABASE_URL"], dbname=conn.info.dbname)
    out = backup.export(url, [LocalRawStore(tmp_path / "a"), LocalRawStore(tmp_path / "b")], dt.date(2026, 10, 11))
    dump = (tmp_path / "a" / out["key"]).read_bytes()
    assert dump.startswith(b"PGDMP") and dump == (tmp_path / "b" / out["key"]).read_bytes()


def test_a_same_day_rerun_completes_the_export_without_dumping_again(tmp_path):
    from data_platform.core.rawstore import LocalRawStore
    from data_platform.jobs import backup

    a, b = LocalRawStore(tmp_path / "a"), LocalRawStore(tmp_path / "b")
    day = dt.date(2026, 10, 11)
    a.put_named(backup.export_key(day), b"PGDMP first")               # first run wrote one store, then failed
    out = backup.export("unused", [a, b], day, dump_fn=lambda url: pytest.fail("must not dump again"))
    assert out["reused"] and b.get_named(backup.export_key(day)) == b"PGDMP first"


@pytest.mark.db
def test_an_empty_archive_never_verifies(conn, tmp_path):
    from data_platform.core.rawstore import LocalRawStore
    from data_platform.jobs import backup

    with pytest.raises(IntegrityError, match="empty"):
        backup.verify(conn, [LocalRawStore(tmp_path / "a")], dt.date(2026, 10, 11))
