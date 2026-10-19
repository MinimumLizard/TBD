"""Directors' dealing facts: the daily sweep fetches the dealing notices' details, the migration step loads the old
terminal's backfill from the archive and reconciles it, and both models run end to end on the stored facts.
Fixtures: tests/fixtures/cse/dealings, synthetic notices of made-up companies and people (no network)."""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from conftest import run_models
from data_platform.collectors.cse import collector as cse
from data_platform.collectors.cse import parse
from data_platform.core.collector import Context
from data_platform.core.http import Response
from data_platform.migration import cse_dealings as mig

FIX = Path(__file__).parent / "fixtures" / "cse" / "dealings"
NOW = dt.datetime(2026, 10, 9, 12, 0, tzinfo=dt.timezone.utc)


def securities() -> bytes:
    """A made-up security list (the CSE's has over 100 rows; the parser refuses fewer)."""
    rows = [{"id": 1, "name": "ALPHA EXAMPLE PLC", "symbol": "AAA.N0000", "active": 1},
            {"id": 2, "name": "BETA SAMPLE HOLDINGS PLC", "symbol": "BBB.N0000", "active": 1}]
    rows += [{"id": 10 + i, "name": f"FILLER COMPANY {i} PLC", "symbol": f"F{i:03d}.N0000", "active": 1}
             for i in range(110)]
    return json.dumps(rows).encode()


def test_dealing_categories_need_their_details():
    assert parse.is_dealing_category("DEALINGS BY DIRECTORS ")
    assert parse.is_dealing_category("RELEVANT INTEREST IN SHARES OTHER CLASS OF SHARES HELD BY THE DIRECTOR/S")
    assert not parse.is_dealing_category("ANNUAL GENERAL MEETING - APPROVED")
    assert parse.needs_detail("CASH DIVIDEND") and parse.needs_detail("Dealings by Directors")
    assert not parse.needs_detail("CHANGES TO THE BOARD") and not parse.needs_detail(None)


class FakeCse:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def request(self, method, url, params=None):
        ep, params = url.rsplit("/", 1)[-1], dict(params or {})
        self.calls.append((ep, params))
        if ep == "allSecurityCode":
            return Response(method, url, params, 200, securities(), "application/json", NOW)
        if ep == "getAnnouncementByCompany":
            p = FIX / ep / f"{params['symbol']}.json"
            return Response(method, url, params, 200, p.read_bytes() if p.exists() else b"{}", "application/json", NOW)
        p = FIX / ep / f"{params['announcementId']}.json"
        if p.exists():
            return Response(method, url, params, 200, p.read_bytes(), "application/json", NOW)
        return Response(method, url, params, 204 if ep == "getAnnouncementById" else 200,
                        b"" if ep == "getAnnouncementById" else b"{}", None, NOW)


def collect(conn, store, http=None):
    c = cse.CseCorporateActionsCollector(Context(conn, store, http or FakeCse(), None, NOW))
    c.only_symbols = {"AAA.N0000", "BBB.N0000"}
    result = c.collect()
    conn.commit()
    return result


@pytest.mark.db
def test_the_daily_sweep_fetches_each_dealing_notice_once(conn, store):
    http = FakeCse()
    collect(conn, store, http)
    asked = {(ep, p["announcementId"]) for ep, p in http.calls if ep in parse.DETAIL_ENDPOINTS}
    typed = {aid for ep, aid in asked if ep == "getAnnouncementById"}
    assert typed == {900001, 900012, 900002, 900003, 900005, 900010}       # not the AGM (900004)
    assert asked - {("getAnnouncementById", a) for a in typed} == {("getGeneralAnnouncementById", 900005)}  # no typed
    stored = {r["announcement_id"]: r["d_type"] for r in conn.execute(
        "select announcement_id, d_type from cse.announcement_details where has_detail")}
    assert stored == {a: "DealingsByDirectors" for a in (900001, 900012, 900002, 900003, 900010)}
    http2 = FakeCse()
    collect(conn, store, http2)
    assert not [ep for ep, _ in http2.calls if ep in parse.DETAIL_ENDPOINTS]          # never asked twice


@pytest.mark.db
def test_both_models_run_on_the_stored_facts_and_names_stay_unpublished(conn, store):
    collect(conn, store)
    run_models(conn, ["cse_dealings", "cse_flows"])
    n = lambda sql: conn.execute(sql).fetchone()["n"]  # noqa: E731
    assert n("select count(*) n from models.cse_dealing") == 6
    assert n("select count(*) n from models.cse_dealing where superseded_by = 900003") == 1
    assert n("select count(*) n from models.cse_flow_company where cluster") > 0
    assert n("select count(*) n from models.cse_flow_actor where actor = 'Mr. A. B. Example'") > 0
    conn.execute("set role web_reader")
    try:
        assert n("select count(*) n from models.cse_flow_dealing") == 5
        for table in ("models.cse_dealing_as_filed", "models.cse_flow_actor"):
            with pytest.raises(Exception, match="permission denied"):
                conn.execute("savepoint s")
                try:
                    conn.execute(f"select * from {table}")
                finally:
                    conn.execute("rollback to savepoint s")
    finally:
        conn.execute("reset role")
    again = run_models(conn, ["cse_dealings", "cse_flows"])                # nothing changes on a second run
    assert all(r.counts.inserted == r.counts.updated == r.counts.deleted == 0 for r in again.values())


# --- the migration step: the old backfill, read back from the archive ----------------------------------------------

def old_repo(tmp_path: Path) -> Path:
    """A miniature old terminal: its dealing backfill (one notice answered 204, saved as {}), one session folder and
    its dealings.csv (the notices only matter here)."""
    repo = tmp_path / "CSE"
    backfill = repo / "data" / "raw" / "dealings"
    backfill.mkdir(parents=True)
    for aid in (900001, 900012, 900002, 900003):
        shutil.copy(FIX / "getAnnouncementById" / f"{aid}.json", backfill / f"{aid}.json")
    (backfill / "900005.json").write_bytes(b"{}")
    session = repo / "data" / "raw" / "2026-10-09" / "getAnnouncementById"
    session.mkdir(parents=True)
    shutil.copy(FIX / "getAnnouncementById" / "900010.json", session / "900010.json")
    (repo / "data" / "dealings").mkdir(parents=True)
    (repo / "data" / "dealings" / "dealings.csv").write_text(
        "announcement_id,announced\n900001,2026-10-05\n900003,2026-10-08\n900010,2026-10-09\n")
    return repo


def catalogue_session_folder(conn, store, repo: Path) -> None:
    """The session folder's files, as the history migration and the corporate-action step make them facts."""
    from data_platform.core import db

    for p in sorted((repo / "data" / "raw" / "2026-10-09").rglob("*.json")):
        fetch_id, sha = db.record_fetch(
            conn, store, source_id="cse_api", method="POST", url=cse.API + "getAnnouncementById",
            params={"announcementId": int(p.stem)}, http_status=200, body=p.read_bytes(),
            content_type="application/json", fetched_at=NOW, origin="migration", note="test")
        cse.store_detail(conn, p.read_bytes(), "getAnnouncementById", p.stem, sha, fetch_id, NOW)
    conn.commit()


@pytest.mark.db
def test_the_old_backfill_loads_from_the_archive_reconciles_and_loads_once(conn, store, tmp_path):
    repo = old_repo(tmp_path)
    assert mig.archive_backfill(conn, store, repo) == 5
    assert mig.archive_backfill(conn, store, repo) == 0                 # the same catalogue entries are reused
    catalogue_session_folder(conn, store, repo)
    first = mig.load_from_archive(conn, store)
    assert first["detail_rows_added"] == 5 and first["with_dealing_record"] == 4
    report = mig.reconcile(conn, repo)
    assert report["ok"], report
    assert report["backfill"]["old_with_dealing_record"] == 4 and report["session_folders"]["old_files"] == 1
    assert report["dealings_csv"]["notices_with_a_fact"] == 3
    again = mig.load_from_archive(conn, store)
    assert again["detail_rows_added"] == 0                               # repeatable


@pytest.mark.db
def test_reconciliation_notices_an_old_file_that_is_not_a_fact(conn, store, tmp_path):
    repo = old_repo(tmp_path)
    mig.archive_backfill(conn, store, repo)
    catalogue_session_folder(conn, store, repo)
    mig.load_from_archive(conn, store)
    shutil.copy(FIX / "getAnnouncementById" / "900010.json", repo / "data" / "raw" / "dealings" / "900099.json")
    report = mig.reconcile(conn, repo)
    assert not report["ok"] and report["backfill"]["missing_in_new"] == 1
