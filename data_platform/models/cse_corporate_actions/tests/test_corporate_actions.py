"""cse_corporate_actions: the rules, ported from the old terminal's tests, and the model end to end on real
announcement records (tests/fixtures/cse/corporate_actions)."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from conftest import FIXTURES, run_models
from data_platform.collectors.cse import collector as cse, parse
from data_platform.core import db
from data_platform.jobs import reviews
from data_platform.models.cse_corporate_actions import compute as m

CA = FIXTURES / "cse" / "corporate_actions"
CLASSES = {"CIC": ["CIC.N0000", "CIC.X0000"], "COMB": ["COMB.N0000", "COMB.X0000"], "HAYL": ["HAYL.N0000"]}


def rec(endpoint, aid, symbol, category, date, source):
    j = json.loads((CA / endpoint / f"{aid}.json").read_text())
    return m.Record(aid, symbol, category, date, j["reqBaseAnnouncement"], j.get("reqAnnouncementDocs") or [], source)


SPLIT = ("getAnnouncementById", 32457, "CIC.N0000", "SUB-DIVISION OF SHARES", "2025-08-05", "typed")
SPLIT_DATES = ("getGeneralAnnouncementById", 33380, "CIC.N0000", "SUB-DIVISION OF SHARES (DATES)", "2025-09-19",
               "general")


def by(rows, symbol, typ):
    return [r for r in rows if r["symbol"] == symbol and r["type"] == typ]


def test_cash_dividend_one_row_per_share_class():
    rows = m.parse([rec("getAnnouncementById", 37168, "CIC.N0000", "CASH DIVIDEND", "2026-05-29", "typed")], CLASSES)
    n, x = by(rows, "CIC.N0000", "cash_dividend")[0], by(rows, "CIC.X0000", "cash_dividend")[0]
    assert (n["ex_date"], n["amount_per_share"], n["status"]) == ("2026-07-01", 0.5, "confirmed")
    assert (x["ex_date"], x["amount_per_share"]) == ("2026-07-01", 0.5)
    assert n["source_url"].startswith("https://cdn.cse.lk/")


def test_split_ratio_from_share_counts_and_ex_date_from_the_dates_record():
    rows = m.parse([rec(*SPLIT), rec(*SPLIT_DATES)], CLASSES)
    for sym in ("CIC.N0000", "CIC.X0000"):
        r = by(rows, sym, "subdivision")[0]
        assert r["factor"] == pytest.approx(5.0) and r["ratio_new"] == pytest.approx(4.0) and r["ratio_held"] == 1.0
        assert r["ex_date"] == "2025-10-22" and r["status"] == "confirmed" and r["id"] == f"32457+33380:{sym}"


def test_a_split_without_its_dates_needs_review_and_is_superseded_once_they_arrive():
    early = m.parse([rec(*SPLIT)], CLASSES)
    assert by(early, "CIC.N0000", "subdivision")[0]["status"] == "needs_review"
    rows = early + m.parse([rec(*SPLIT), rec(*SPLIT_DATES)], CLASSES)
    assert m.superseded(rows) == {"32457:CIC.N0000", "32457:CIC.X0000"}
    assert sorted(r["id"] for r in m.effective(rows, ({}, set()))) == ["32457+33380:CIC.N0000", "32457+33380:CIC.X0000"]


def test_scrip_proportion_is_existing_shares_per_new_share():
    rows = m.parse([rec("getAnnouncementById", 36113, "COMB.N0000", "SCRIP DIVIDEND (DATES)", "2026-03-09", "typed")],
                   CLASSES)
    n = by(rows, "COMB.N0000", "scrip")[0]
    assert n["ex_date"] == "2026-04-02" and n["ratio_held"] == pytest.approx(108.2352945432)
    assert n["factor"] == pytest.approx(109.2352945432 / 108.2352945432) and n["status"] == "confirmed"
    assert by(rows, "COMB.X0000", "scrip")[0]["ratio_held"] == pytest.approx(97.88235324)


def test_a_scrip_whose_share_count_check_fails_needs_review():
    r = rec("getAnnouncementById", 36113, "COMB.N0000", "SCRIP DIVIDEND (DATES)", "2026-03-09", "typed")
    rows = m.parse([r], CLASSES, {"COMB.N0000": 1.0})          # an absurd share count: the check fails
    n = by(rows, "COMB.N0000", "scrip")[0]
    assert n["status"] == "needs_review" and "share-count check FAILED" in n["note"]


def test_a_rights_issue_always_needs_review():
    rows = m.parse([rec("getGeneralAnnouncementById", 35920, "HAYL.N0000", "RIGHTS ISSUE (DATES)", "2026-02-26",
                        "general")], CLASSES)
    r = by(rows, "HAYL.N0000", "rights")[0]
    assert (r["ex_date"], r["ratio_new"], r["ratio_held"]) == ("2026-03-18", 3.0, 50.0)
    assert r["status"] == "needs_review" and "subscription price not found" in r["note"]


@pytest.mark.parametrize("text,expected", [
    ("Three (3) new Ordinary Voting Shares for every Fifty (50) existing Ordinary Voting Shares ", (3.0, 50.0)),
    ("One (01) new Ordinary Voting Share for every One (01) existing issued Ordinary voting shares", (1.0, 1.0)),
    ("1 new share for every 4 existing shares", (1.0, 4.0)),
    ("06 new ordinary shares for every 01 existing ordinary share", (6.0, 1.0)),
    ("03 Ordinary Voting share for every 14 existing Ordinary Voting shares", (3.0, 14.0)),
    ("Fourteen (14) New Ordinary Shares for every Forty-Five (45) existing Ordinary Shares", (14.0, 45.0)),
    ("Four new Preference Shares for existing 21 ordinary shares", None),
    ("1:5", None),                      # which side is new is ambiguous: never guessed
    (None, None),
])
def test_rights_ratio_text(text, expected):
    assert m.parse_rights_text(text) == expected


@pytest.mark.parametrize("value,expected", [
    (108.2352945432, (108.2352945432, "numeric")), ("1 for 136.0022997317", (136.0022997317, "text")),
    ("1 share for every 115.38 shares", (115.38, "text")), ("1for115.25", (115.25, "text")),
    ("1:5", (None, "unparsed")), ("5 for 1", (None, "unparsed")), (0, (None, "unparsed")),
])
def test_scrip_proportion_text(value, expected):
    assert m.parse_proportion(value) == expected


ROWS = [
    {"id": "1:A.N0000", "symbol": "A.N0000", "type": "cash_dividend", "ex_date": "2026-01-05", "amount_per_share": 2.0,
     "ratio_new": None, "ratio_held": None, "factor": None, "subscription_price": None, "status": "confirmed",
     "note": "", "source_url": ""},
    {"id": "2:A.N0000", "symbol": "A.N0000", "type": "rights", "ex_date": "2026-02-05", "amount_per_share": None,
     "ratio_new": 1.0, "ratio_held": 5.0, "factor": None, "subscription_price": None, "status": "needs_review",
     "note": "", "source_url": ""},
    {"id": "3:A.N0000", "symbol": "A.N0000", "type": "scrip", "ex_date": "2026-03-05", "amount_per_share": None,
     "ratio_new": None, "ratio_held": None, "factor": None, "subscription_price": None, "status": "needs_review",
     "note": "", "source_url": ""},
]


def test_unconfirmed_rows_are_never_used():
    assert [r["id"] for r in m.effective(ROWS, ({}, set()))] == ["1:A.N0000"]


def test_a_confirmation_with_a_correction_and_a_rejection():
    eff = m.effective(ROWS, ({"2:A.N0000": {"subscription_price": 10.0}}, {"1:A.N0000"}))
    assert [r["id"] for r in eff] == ["2:A.N0000"]
    assert eff[0]["subscription_price"] == 10.0 and eff[0]["status"] == "confirmed (reviewed)"


def test_a_repeated_announcement_for_the_same_event_counts_once():
    dup = dict(ROWS[0], id="9:A.N0000", amount_per_share=2.5)
    eff = m.effective([ROWS[0], dup], ({}, set()))
    assert len(eff) == 1 and eff[0]["id"] == "9:A.N0000" and eff[0]["amount_per_share"] == 2.5


def test_a_confirmation_must_be_complete_and_dated():
    with pytest.raises(ValueError, match="subscription_price"):
        m.effective(ROWS, ({"2:A.N0000": {}}, {"1:A.N0000"}))
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        m.effective(ROWS, ({"3:A.N0000": {"ex_date": "5 March", "ratio_new": 1, "ratio_held": 10}}, set()))
    eff = m.effective(ROWS, ({"3:A.N0000": {"ratio_new": 1, "ratio_held": 10}}, set()))
    assert next(r for r in eff if r["id"] == "3:A.N0000")["factor"] == pytest.approx(1.1)
    with pytest.raises(ValueError, match="unknown fields"):
        m.check_reviews({"2:A.N0000": {"price": 10}}, [])


def test_numbers_are_kept_as_the_old_csv_kept_them():
    assert m.as_stored(1.009239130434782) == 1.00923913 and m.as_stored(5.0) == 5.0 and m.as_stored("x") == "x"


def test_the_collector_and_the_model_agree_on_corporate_action_categories():
    categories = ["CASH DIVIDEND", "SCRIP DIVIDEND (DATES)", "SUB-DIVISION OF SHARES", "RIGHTS ISSUE (DATES)",
                  "CAPITALIZATION OF RESERVES", "CONSOLIDATION OF SHARES", "BONUS ISSUE", "DEBENTURE ISSUE",
                  "DEALINGS BY DIRECTORS", "ANNUAL GENERAL MEETING - APPROVED", "DIVIDEND (DEBENTURE INTEREST)"]
    assert [parse.is_ca_category(c) for c in categories] == [m.is_ca_category(c) for c in categories]
    assert parse.CA_KEYWORDS == m.CA_KEYWORDS


# --- end to end ---------------------------------------------------------------------------------------------------

NOW = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)


def fetch(conn, store, endpoint, body, params):
    return db.record_fetch(conn, store, source_id="cse_api", method="POST", url=cse.API + endpoint, params=params,
                           http_status=200, body=body, content_type="application/json", fetched_at=NOW)


def load_facts(conn, store):
    """CIC's real announcement list and detail records, HAYL's rights dates record as a daily-list announcement,
    and the 2026-10-02 security list."""
    body = (FIXTURES / "cse" / "2026-10-02" / "allSecurityCode.json").read_bytes()
    fid, _ = fetch(conn, store, "allSecurityCode", body, {})
    cse.store(conn, "cse.security_list", parse.security_list(body, dt.date(2026, 10, 2)), ["session_date", "symbol"],
              fid, NOW)
    body = (CA / "getAnnouncementByCompany" / "CIC.N0000.json").read_bytes()
    fid, _ = fetch(conn, store, "getAnnouncementByCompany", body, {"symbol": "CIC.N0000"})
    cse.store_company_announcements(conn, parse.company_announcements(body, "CIC.N0000"), fid, NOW)
    for endpoint in parse.DETAIL_ENDPOINTS:
        for p in sorted((CA / endpoint).glob("*.json")):
            fid, sha = fetch(conn, store, endpoint, p.read_bytes(), {"announcementId": int(p.stem)})
            cse.store_detail(conn, p.read_bytes(), endpoint, p.stem, sha, fid, NOW)
    conn.execute("""insert into cse.announcements (announcement_id, announced_date, symbol, company, title, category,
                    list_fetch_id, fetched_at) values ('35920', '2026-02-26', 'HAYL', 'HAYLEYS PLC', 'x',
                    'RIGHTS ISSUE (DATES)', %s, %s)""", (fid, NOW))
    conn.commit()


def outputs(conn):
    actions = {r["action_id"]: r for r in conn.execute("select * from models.cse_corporate_action")}
    used = {r["action_id"]: r for r in conn.execute("select * from models.cse_corporate_action_used")}
    return actions, used


@pytest.mark.db
def test_the_model_reads_the_stored_records_as_the_old_terminal_read_its_files(conn, store):
    load_facts(conn, store)
    run_models(conn, ["cse_corporate_actions"])
    actions, used = outputs(conn)
    assert set(actions) == {"37168:CIC.N0000", "37168:CIC.X0000", "32457+33380:CIC.N0000", "32457+33380:CIC.X0000",
                            "35920:HAYL.N0000"}
    split = actions["32457+33380:CIC.N0000"]
    assert (split["action_type"], split["ex_date"], split["factor"], split["use_status"]) == \
        ("subdivision", dt.date(2025, 10, 22), 5.0, "used")
    assert split["announcement_id"] == 32457 and split["announced_date"] == dt.date(2025, 8, 5)
    rights = actions["35920:HAYL.N0000"]
    assert rights["status"] == "needs_review" and rights["use_status"] == "awaiting_confirmation"
    assert set(used) == set(actions) - {"35920:HAYL.N0000"}


@pytest.mark.db
def test_a_confirmation_changes_the_outputs_and_taking_it_back_restores_them(conn, store, tmp_path):
    load_facts(conn, store)
    review = tmp_path / "review.yaml"
    review.write_text("confirm: {}\nreject: []\n")
    reviews.sync(conn, review, code_version="t")
    run_models(conn, ["cse_corporate_actions"])
    before = outputs(conn)

    review.write_text('confirm:\n  "35920:HAYL.N0000": {subscription_price: 200}\nreject: ["37168:CIC.X0000"]\n')
    reviews.sync(conn, review, code_version="t")
    run_models(conn, ["cse_corporate_actions"])
    actions, used = outputs(conn)
    assert used["35920:HAYL.N0000"]["subscription_price"] == 200.0
    assert used["35920:HAYL.N0000"]["status"] == "confirmed (reviewed)"
    assert actions["35920:HAYL.N0000"]["use_status"] == "used"
    assert "37168:CIC.X0000" not in used and actions["37168:CIC.X0000"]["use_status"] == "rejected"

    review.write_text("confirm: {}\nreject: []\n")
    reviews.sync(conn, review, code_version="t")
    run_models(conn, ["cse_corporate_actions"])
    strip = lambda o: [{k: {c: v for c, v in r.items() if c != "run_id"} for k, r in t.items()} for t in o]  # noqa: E731
    assert strip(outputs(conn)) == strip(before)
    assert conn.execute("select count(*) n from models.revisions where table_name = 'models.cse_corporate_action'"
                        ).fetchone()["n"] > 0           # every change on record


@pytest.mark.db
def test_an_as_of_run_sees_only_what_was_announced_by_then(conn, store):
    from data_platform.migration.parity import run_chain

    load_facts(conn, store)
    out = run_chain(conn, ["cse_corporate_actions"], as_of=dt.date(2025, 9, 1), pick=lambda mf: mf.current)
    ids = {r["action_id"] for r in out["models.cse_corporate_action"]}
    assert ids == {"32457:CIC.N0000", "32457:CIC.X0000"}           # the split, its dates not yet announced
    assert all(r["status"] == "needs_review" for r in out["models.cse_corporate_action"])
    conn.rollback()

