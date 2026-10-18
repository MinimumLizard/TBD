"""CSE corporate-action facts: parsers, the cse_api:corporate_actions collector, the migration step from the old
terminal's caches, and the owner's confirmations job. Fixtures are real responses from the old terminal's caches
(tests/fixtures/cse/corporate_actions, byte-identical to its data/raw/announcements files); no network."""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from data_platform.collectors.cse import collector as cse
from data_platform.collectors.cse import parse
from data_platform.core.collector import Context
from data_platform.core.http import Response
from data_platform.jobs import reviews
from data_platform.migration import cse_corporate_actions as ca

FIX = Path(__file__).parent / "fixtures" / "cse"
CA = FIX / "corporate_actions"
SECURITIES = FIX / "2026-10-02" / "allSecurityCode.json"


# --- parsers ----------------------------------------------------------------------------------------------------

def test_a_company_list_keeps_every_row_with_its_date_and_category():
    rows = parse.company_announcements((CA / "getAnnouncementByCompany" / "CIC.N0000.json").read_bytes(), "CIC.N0000")
    assert len(rows) == 17 and all(r["symbol"] == "CIC.N0000" for r in rows)
    split = next(r for r in rows if r["announcement_id"] == 32457)
    assert split["announced_date"] == dt.date(2025, 8, 5) and split["category"] == "SUB-DIVISION OF SHARES"
    assert {r["announcement_id"] for r in rows if parse.is_ca_category(r["category"])} == {37168, 33380, 32457}


def test_an_empty_list_is_no_announcements_but_a_changed_shape_fails():
    assert parse.company_announcements(b"", "X.N0000") == [] and parse.company_announcements(b"{}", "X.N0000") == []
    with pytest.raises(ValueError, match="getAnnouncementByCompany"):
        parse.company_announcements(b'{"reqCompanyAnnouncement": "nothing"}', "X.N0000")


def test_announcement_dates_as_the_old_tool_read_them():
    assert parse.announcement_date("05 Aug 2025") == dt.date(2025, 8, 5)
    assert parse.announcement_date("2025-08-05") == dt.date(2025, 8, 5)
    assert parse.announcement_date(1782824461000) == dt.date(2026, 6, 30)       # epoch ms, Sri Lanka time
    assert parse.announcement_date("sometime") is None and parse.announcement_date(None) is None


def test_a_detail_keeps_every_typed_field_and_a_204_is_no_detail():
    body = (CA / "getAnnouncementById" / "37168.json").read_bytes()
    fact = parse.detail_fact(body, "getAnnouncementById", "37168")
    assert fact["has_detail"] and fact["d_type"] == "CashDividendWithDates"
    assert fact["base"] == json.loads(body)["reqBaseAnnouncement"]                # as served, nothing dropped
    assert not parse.detail_fact(b"", "getAnnouncementById", "1")["has_detail"]
    assert not parse.detail_fact(b"{}", "getGeneralAnnouncementById", "1")["has_detail"]
    with pytest.raises(ValueError):
        parse.detail_fact(b'{"reqBaseAnnouncement": {"dType": "X"}}', "getAnnouncementById", "1")   # no id


def test_one_symbol_per_company_the_voting_line_first():
    secs = parse.security_list(SECURITIES.read_bytes(), dt.date(2026, 10, 2))
    symbols = parse.company_symbols(secs)
    assert "CIC.N0000" in symbols and "CIC.X0000" not in symbols and "HAYL.R0000" not in symbols
    assert len(symbols) == len({s.split(".")[0] for s in symbols})


# --- the collector against a fake CSE API ------------------------------------------------------------------------

class FakeCse:
    def __init__(self, broken: str | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.broken = broken

    def request(self, method, url, params=None):
        ep, params = url.rsplit("/", 1)[-1], dict(params or {})
        self.calls.append((ep, params))
        now = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)
        if ep == "allSecurityCode":
            return Response(method, url, params, 200, SECURITIES.read_bytes(), "application/json", now)
        if ep == "getAnnouncementByCompany":
            if params["symbol"] == self.broken:
                raise ConnectionError("reset by peer")
            p = CA / ep / f"{params['symbol']}.json"
            return Response(method, url, params, 200, p.read_bytes() if p.exists() else b"{}", "application/json", now)
        p = CA / ep / f"{params['announcementId']}.json"
        if p.exists():
            return Response(method, url, params, 200, p.read_bytes(), "application/json", now)
        # what the API really does: 204 from the typed endpoint, {} from the general one
        return Response(method, url, params, 204 if ep == "getAnnouncementById" else 200,
                        b"" if ep == "getAnnouncementById" else b"{}", None, now)


def make(conn, store, http, symbols=("CIC.N0000", "CIC.X0000", "COMB.N0000")):
    c = cse.CseCorporateActionsCollector(Context(conn, store, http, None,
                                                 dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)))
    c.only_symbols = set(symbols)
    return c


@pytest.mark.db
def test_lists_and_corporate_action_details_are_stored_once(conn, store):
    http = FakeCse()
    result = make(conn, store, http).collect()
    conn.commit()
    lists = [p for ep, p in http.calls if ep == "getAnnouncementByCompany"]
    assert [p["symbol"] for p in lists] == ["CIC.N0000", "COMB.N0000"]              # one per company, voting line
    assert lists[0]["fromDate"] == "2026-07-18" and lists[0]["toDate"] == "2026-10-18"   # the rolling window
    n = lambda t: conn.execute(f"select count(*) n from {t}").fetchone()["n"]  # noqa: E731
    assert n("cse.company_announcements") == 17 and result.rows_added == 17
    details = {(r["announcement_id"], r["endpoint"]): r["has_detail"] for r in conn.execute(
        "select * from cse.announcement_details")}
    assert details == {(37168, "getAnnouncementById"): True, (32457, "getAnnouncementById"): True,
                       (33380, "getAnnouncementById"): False, (33380, "getGeneralAnnouncementById"): True}
    # the next run lists the same announcements again: nothing new, and no detail is asked for twice
    http2 = FakeCse()
    again = make(conn, store, http2).collect()
    assert again.rows_added == 0 and not again.new_data
    assert not [ep for ep, _ in http2.calls if ep in parse.DETAIL_ENDPOINTS]


@pytest.mark.db
def test_one_company_failing_never_loses_the_others(conn, store):
    with pytest.raises(RuntimeError, match="1 companies failed: CIC.N0000"):
        make(conn, store, FakeCse(broken="CIC.N0000"), symbols=("CIC.N0000", "COMB.N0000")).collect()
    conn.rollback()
    assert conn.execute("select count(*) n from ops.raw_fetches").fetchone()["n"] >= 2   # raw kept
    make(conn, store, FakeCse(), symbols=("CIC.N0000", "COMB.N0000")).collect()      # the next run completes it
    conn.commit()
    assert conn.execute("select count(*) n from cse.company_announcements").fetchone()["n"] == 17


@pytest.mark.db
def test_the_announcements_job_also_keeps_each_detail_as_a_fact(conn, store):
    from tests.test_cse import FakeCse as FakeDaily, make as make_daily

    make_daily(cse.CseAnnouncementsCollector, conn, store, FakeDaily()).collect()
    conn.commit()
    stored = conn.execute("select count(*) n, count(*) filter (where has_detail) d from cse.announcement_details").fetchone()
    assert stored["d"] == 2 and stored["n"] > stored["d"]       # the 204s are kept too: "asked, none there"


# --- the migration step: the old caches, read back from the archive ----------------------------------------------

def old_repo(tmp_path: Path) -> Path:
    """A miniature old terminal: its corporate-action caches and one session folder, from the fixtures."""
    repo = tmp_path / "CSE"
    cache = repo / "data" / "raw" / "announcements"
    (cache / "byCompany").mkdir(parents=True)
    shutil.copy(CA / "getAnnouncementByCompany" / "CIC.N0000.json", cache / "byCompany" / "CIC.N0000_2025-06-01_2026-10-04.json")
    for ep in parse.DETAIL_ENDPOINTS:
        shutil.copytree(CA / ep, cache / ep)
    (cache / "getAnnouncementById" / "33380.json").write_bytes(b"")              # the old cache's 204
    session = repo / "data" / "raw" / "2026-10-02" / "getAnnouncementById"
    shutil.copytree(FIX / "2026-10-02" / "getAnnouncementById", session)
    return repo


@pytest.mark.db
def test_the_old_caches_load_from_the_archive_reconcile_and_load_once(conn, store, tmp_path):
    repo = old_repo(tmp_path)
    assert ca.archive_cache(conn, store, repo) == 7
    assert ca.archive_cache(conn, store, repo) == 0                 # the same catalogue entries are reused
    # the session folder's files, as the history migration catalogues those it does not replay
    for p in sorted((repo / "data" / "raw" / "2026-10-02").rglob("*.json")):
        from data_platform.core import db
        db.record_fetch(conn, store, source_id="legacy_cse", method="GIT",
                        url=f"git://github.com/MinimumLizard/CSE@abc1234/{p.relative_to(repo)}", params={},
                        http_status=200, body=p.read_bytes(), content_type=None,
                        fetched_at=dt.datetime.now(dt.timezone.utc), origin="migration", note="test")
    conn.commit()
    first = ca.load_from_archive(conn, store)
    assert first["list_rows_added"] == 17 and first["detail_rows_added"] == 6 + 2
    report = ca.reconcile(conn, repo)
    assert report["ok"], report
    assert report["company_lists"]["old_corporate_action_rows"] == 3
    assert report["details_cache_getAnnouncementById"]["old_with_detail"] == 3
    again = ca.load_from_archive(conn, store)
    assert again["list_rows_added"] == 0 and again["detail_rows_added"] == 0


@pytest.mark.db
def test_reconciliation_notices_a_cache_file_that_is_not_a_fact(conn, store, tmp_path):
    repo = old_repo(tmp_path)
    ca.archive_cache(conn, store, repo)
    ca.load_from_archive(conn, store)
    (repo / "data" / "raw" / "announcements" / "getAnnouncementById" / "99999.json").write_bytes(b"")
    report = ca.reconcile(conn, repo)
    assert not report["ok"] and report["details_cache_getAnnouncementById"]["missing_in_new"] == 1


# --- the owner's confirmations ------------------------------------------------------------------------------------

def test_the_repositorys_review_file_is_valid():
    confirm, reject, _ = reviews.read()
    assert isinstance(confirm, dict) and isinstance(reject, list)


def test_a_review_file_with_an_unknown_field_is_refused_and_dates_stay_as_written(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text('confirm:\n  "2:A.N0000": {price: 10}\n')
    with pytest.raises(ValueError, match="unknown fields"):
        reviews.read(p)
    p.write_text('confirm:\n  "3:A.N0000": {ex_date: 2026-03-05, ratio_new: 1}\nreject: ["1:A.N0000"]\n')
    confirm, reject, _ = reviews.read(p)
    assert confirm == {"3:A.N0000": {"ex_date": "2026-03-05", "ratio_new": 1}} and reject == ["1:A.N0000"]


@pytest.mark.db
def test_each_new_version_of_the_review_file_is_stored_once(conn, tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("confirm: {}\nreject: []\n")
    assert reviews.sync(conn, p, code_version="t") == 1
    assert reviews.sync(conn, p, code_version="t") is None              # unchanged: nothing stored
    p.write_text('confirm: {}\nreject: ["1:A.N0000"]\n')
    assert reviews.sync(conn, p, code_version="t") == 2
    p.write_text("confirm: {}\nreject: []\n")
    assert reviews.sync(conn, p, code_version="t") == 3                 # going back is a new version too
    assert conn.execute("select count(*) n from cse.corporate_action_reviews").fetchone()["n"] == 3
