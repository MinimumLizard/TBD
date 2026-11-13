"""Sign-ups (migration 0019): the website can only submit, through one checked function; it can never read an address."""
from __future__ import annotations

import pytest

from data_platform.jobs import signups

pytestmark = pytest.mark.db

KEY = "0123456789abcdef0123456789abcdef"
VERSION = "2026-11-13"


def submit(conn, email="Nimal@Example.com", type_="new", answer="deposits", weekly=True, version=VERSION, key=KEY):
    return conn.execute("select community.submit_signup(%s, %s, %s, %s, %s, %s) as r",
                        (email, type_, answer, weekly, version, key)).fetchone()["r"]


def test_the_website_can_sign_someone_up_but_never_read_or_change_the_list(conn):
    conn.execute("set role web_reader")
    try:
        assert submit(conn) == "ok"
        for forbidden in ("select * from community.signups", "select count(*) from community.signups",
                          "insert into community.signups (email, consent_version) values ('a@b.lk', '2026-11-13')",
                          "update community.signups set status = 'confirmed'", "delete from community.signups"):
            conn.execute("savepoint s")
            with pytest.raises(Exception, match="permission denied"):
                conn.execute(forbidden)
            conn.execute("rollback to savepoint s")
    finally:
        conn.execute("reset role")
    row = conn.execute("select email, starting_type, starting_answer, wants_weekly, consent_version, status, "
                       "confirmed_at from community.signups").fetchone()
    assert row == {"email": "nimal@example.com", "starting_type": "new", "starting_answer": "deposits",
                   "wants_weekly": True, "consent_version": VERSION, "status": "pending", "confirmed_at": None}


def test_a_second_sign_up_with_the_same_address_says_ok_and_keeps_one_row(conn):
    assert submit(conn) == "ok"
    assert submit(conn, email="  NIMAL@example.com ", type_=None, answer=None, weekly=False) == "ok"
    rows = signups.rows(conn)
    assert len(rows) == 1
    # the newer choice about the weekly summary is kept; the starting path is not wiped by a form without one
    assert (rows[0]["wants_weekly"], rows[0]["starting_type"], rows[0]["starting_answer"]) == (False, "new", "deposits")


def test_bad_fields_store_nothing(conn):
    for kwargs in ({"email": "not an address"}, {"email": "a@b"}, {"email": "a b@example.com"}, {"email": ""},
                   {"email": "x" * 250 + "@example.com"}, {"email": "<a@example.com>"},
                   {"type_": "new", "answer": None}, {"type_": "NEW"}, {"answer": "x" * 30},
                   {"weekly": None}, {"version": "yesterday"}, {"version": None}, {"key": "short"}, {"key": None}):
        assert submit(conn, **kwargs) == "invalid", kwargs
    assert signups.rows(conn) == []


def test_one_sender_is_limited_per_hour(conn):
    for i in range(5):
        assert submit(conn, email=f"person{i}@example.com") == "ok"
    assert submit(conn, email="person5@example.com") == "limited"
    assert submit(conn, email="person5@example.com", key="f" * 32) == "ok"
    assert len(signups.rows(conn)) == 6


def test_the_owner_can_summarise_unsubscribe_export_and_delete(conn, tmp_path):
    submit(conn)
    submit(conn, email="kamala@example.com", type_="confident", answer="bonds", weekly=False, key="a" * 32)
    out = signups.summary(conn)
    assert out["by_status"] == [{"status": "pending", "n": 2, "weekly": 1}]
    assert {(r["type"], r["answer"], r["n"]) for r in out["by_path"]} == {("new", "deposits", 1), ("confident", "bonds", 1)}

    assert signups.unsubscribe(conn, ["Nimal@example.com"]) == 1
    assert {r["email"]: r["status"] for r in signups.rows(conn)} == {"nimal@example.com": "unsubscribed",
                                                                      "kamala@example.com": "pending"}
    assert submit(conn) == "ok"                      # signing up again after unsubscribing: pending again
    assert [r["status"] for r in signups.rows(conn)] == ["pending", "pending"]

    target = tmp_path / "signups.csv"
    assert signups.export(conn, target) == 2
    assert "kamala@example.com" in target.read_text()
    with pytest.raises(ValueError, match="outside this repository"):
        signups.export(conn, signups.REPO / "signups.csv")

    assert signups.delete(conn, ["nimal@example.com"]) == 1
    assert [r["email"] for r in signups.rows(conn)] == ["kamala@example.com"]


def test_the_senders_key_is_forgotten_after_seven_days(conn):
    submit(conn)
    conn.execute("update community.signups set consented_at = now() - interval '8 days'")
    submit(conn, email="later@example.com")
    keys = conn.execute("select email, client_key from community.signups order by email").fetchall()
    assert keys == [{"email": "later@example.com", "client_key": KEY}, {"email": "nimal@example.com", "client_key": None}]
