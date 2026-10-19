"""cse_dealings: the old terminal's rules (its tests, ported with made-up notices), the role categories, re-filings
and the point-in-time rule. Fixtures: tests/fixtures/cse/dealings (synthetic companies and people; the repository is
public, so no real person's name is used)."""
from __future__ import annotations

import copy
import datetime as dt
import json

import pytest

from conftest import FIXTURES
from data_platform.models.cse_dealings import compute as m

DEALINGS = FIXTURES / "cse" / "dealings" / "getAnnouncementById"


def load(aid) -> dict:
    return json.loads((DEALINGS / f"{aid}.json").read_text())


class Inputs:
    """Serves cse.announcement_details rows from memory, as the framework would (latest response last)."""

    def __init__(self, notices: dict[int, dict]):
        self.notices = notices
        self.params = {}

    def rows(self, dataset, columns="*", where="", params=(), order_by="", group_by=""):
        assert dataset == "cse.announcement_details" and params == (m.TYPED, m.DEALING_TYPE)
        return [{"announcement_id": aid, "base": d["reqBaseAnnouncement"], "docs": d.get("reqAnnouncementDocs")}
                for aid, d in self.notices.items()
                if (d.get("reqBaseAnnouncement") or {}).get("dType") == m.DEALING_TYPE]


ALL = (900001, 900012, 900002, 900003, 900010)


def outputs(ids=ALL, as_of=None):
    return m.compute(Inputs({aid: load(aid) for aid in ids}), as_of)


# --- the old terminal's rules --------------------------------------------------------------------------------------

def test_own_account_purchase():
    r = m.parse("900001", load(900001))[0]
    assert (r["symbol"], r["side"], r["account_type"], r["account"]) == ("AAA", "purchase", "own", "Mr. A. B. Example")
    assert r["quantity"] == 1000 and r["price"] == 10.5 and r["value"] == pytest.approx(10500)
    assert (r["trade_date"], r["announced"], r["lag_days"]) == ("2026-10-01", "2026-10-05", 2)   # Fri, Mon
    assert r["url"].startswith("https://cdn.cse.lk/") and " " not in r["url"]


def test_numbers_given_as_text_are_read():
    r = m.parse("900001", load(900001))[1]
    assert (r["quantity"], r["price"], r["value"]) == (500.0, 11.0, 5500.0)
    assert m._num("1,250,000") == 1250000.0 and m._num("") is None and m._num("n/a") is None


def test_related_account_keeps_the_account_name():
    (r,) = m.parse("900002", load(900002))
    assert r["account_type"] == "related" and r["account"].startswith("Example Holdings (Pvt) Ltd")
    assert r["side"] == "disposal" and r["value"] == 12_000_000


@pytest.mark.parametrize("raw, side", [
    ("Purchase of Shares", "purchase"), ("PURCHASE", "purchase"), ("Acquisition of shares", "purchase"),
    ("purchased", "purchase"), ("Sale", "disposal"), ("Sale of Shares ", "disposal"),
    ("Disposal of Shares (Voting)", "disposal"), ("disposal", "disposal"), ("Gift Transfer", "other"),
    ("Transfer", "other"), ("", "other"), ("Purchase and sale", "other"), ("Aquisition", "purchase"),
    ("Puchase", "purchase"), ("Share Allotment - Rights Issue", "purchase"), ("Share Allotment", "other"),
    ("Transmission", "other"), ("Ordinary Voting Shares", "other"), ("Sold", "disposal"), ("Gift", "other"),
])
def test_side_from_free_text(raw, side):              # wordings seen in the API's transType field
    assert m.side_of(raw) == side


def test_weekday_lag_skips_weekends():
    fri, mon = dt.date(2026, 10, 2), dt.date(2026, 10, 5)
    assert m.weekdays_between(fri, mon) == 1 and m.weekdays_between(fri, fri) == 0
    assert m.weekdays_between(mon, fri) == -1


def test_dates_in_every_format_the_notices_use():
    for text in ("02 Oct 2026", "2 October 2026", "2026-10-02", "02/10/2026", "02-10-2026", "02.10.2026"):
        assert m.parse_date(text) == dt.date(2026, 10, 2), text
    assert m.parse_date("sometime") is None and m.parse_date(None) is None


def test_non_dealing_announcements_are_ignored():
    assert m.parse("1", {"reqBaseAnnouncement": {"dType": "AppointmentOfDirectors"}}) == []
    assert m.parse("1", {}) == []
    assert m.parse("1", {"reqBaseAnnouncement": {"dType": m.DEALING_TYPE, "directorTransactions": []}}) == []


def test_a_refiled_notice_replaces_the_original_and_both_stay_on_record():
    rows = m.parse("900002", load(900002)) + m.parse("900003", load(900003))
    assert m.refiled(rows) == {"900002": "900003"}
    out = outputs()["models.cse_dealing"]
    sup = {r["transaction_id"]: r["superseded_by"] for r in out}
    assert sup["900002:1"] == 900003 and sup["900003:1"] is None


def test_a_notice_is_refiled_only_by_a_later_one_for_the_same_account():
    later = copy.deepcopy(load(900003))
    later["reqBaseAnnouncement"]["relInterestAccountName"] = "Another Example Ltd"
    rows = m.parse("900002", load(900002)) + m.parse("900003", later)
    assert m.refiled(rows) == {}


def test_identical_lines_in_one_notice_all_stay():
    twice = copy.deepcopy(load(900012))
    t = twice["reqBaseAnnouncement"]["directorTransactions"]
    t.append(dict(t[0]))
    rows = m.parse("900012", twice)
    assert len(rows) == 2 and m.refiled(rows) == {}


# --- the role, without free text -----------------------------------------------------------------------------------

@pytest.mark.parametrize("text, role", [
    ("Executive Director", "executive"), ("Executive", "executive"), ("Director - Finance", "executive"),
    ("Exaecutive", "executive"), ("Non-Executive Director", "non_executive"),
    ("Non - Independent / Non - Executive Director", "non_executive"), ("NON EXECUTIVE NON INDEPENDENT", "non_executive"),
    ("Independent Non-Executive Director", "independent_non_executive"),
    ("Non Executive Independent", "independent_non_executive"), ("Senior Independent Director", "independent_non_executive"),
    ("Managing Director", "chief_executive"), ("Executive Director/Chief Executive Officer", "chief_executive"),
    ("Chairman (Non-Executive Director)", "chair"), ("Executive Director and Chairman of the Board of Directors", "chair"),
    ("Executive Director/ Non Executive Director", "several"), ("Non-Executive Directors", "several"),
    ("Same directors for both companies", "several"), ("Mr. A. Example (Chairman) and Mr. B. Sample (Director)", "several"),
    ("(Executive Chairman) and (Executive Deputy Chairperson)", "several"),
    ("Please refer attachment", "not_stated"), ("Director", "not_stated"), ("", "not_stated"), (None, "not_stated"),
])
def test_role_categories(text, role):
    assert m.role_of(text) == role


def test_the_published_table_has_no_names_and_the_names_table_has_them():
    out = outputs()
    published = json.dumps(out["models.cse_dealing"], default=str)
    for name in ("A. B. Example", "C. Sample", "E. Sample", "F. Example", "Example Holdings", "notice"):
        assert name not in published
    filed = {r["transaction_id"]: r for r in out["models.cse_dealing_as_filed"]}
    assert filed["900001:1"]["director"] == "Mr. A. B. Example" and filed["900010:1"]["source_url"] == ""
    assert filed["900001:1"]["source_url"].endswith("notice%20900001.pdf")


def test_rows_in_the_old_order_with_neutral_sides():
    out = outputs()["models.cse_dealing"]
    assert [r["transaction_id"] for r in out] == ["900001:1", "900001:2", "900012:1", "900002:1", "900003:1",
                                                    "900010:1"]
    assert {r["side"] for r in out} == {"purchase", "disposal", "other"}
    gift = out[-1]
    assert (gift["side"], gift["role"], gift["deal_date"], gift["lag_days"]) == ("other", "chair", "2026-10-08", 1)


def test_numbers_are_stored_as_the_old_file_stored_them():
    assert m.as_stored(5200 * 10.2) == 53040.0 and m.as_stored(0.1 + 0.2) == 0.3 and m.as_stored(7.0) == 7.0


# --- point in time ---------------------------------------------------------------------------------------------------

def test_a_row_does_not_change_when_later_notices_arrive_except_by_a_refiling():
    early = outputs(as_of=dt.date(2026, 10, 7))
    late = outputs()
    for table, key in (("models.cse_dealing", "transaction_id"), ("models.cse_dealing_as_filed", "transaction_id")):
        before = {r[key]: r for r in early[table]}
        after = {r[key]: r for r in late[table]}
        assert set(before) == {"900001:1", "900001:2", "900012:1", "900002:1"}
        for k, row in before.items():
            changed = {c for c in row if row[c] != after[k][c]}
            # the only change a later notice can make: the re-filing of 900002, announced on 8 October
            refiled = k == "900002:1" and table == "models.cse_dealing"
            assert changed == ({"superseded_by"} if refiled else set()), (table, k, changed)
