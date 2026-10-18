"""Visitors' feedback (migration 0012): the website can only submit, through one checked function; it cannot read."""
from __future__ import annotations

import pytest

from data_platform.jobs import feedback

pytestmark = pytest.mark.db

KEY = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"


def submit(conn, page="/bonds", kind="page_vote", useful=True, topic=None, message=None, tier="free", key=KEY):
    return conn.execute("select community.submit_feedback(%s, %s, %s, %s, %s, %s, %s) as r",
                        (page, kind, useful, topic, message, tier, key)).fetchone()["r"]


def as_website(conn):
    conn.execute("set role web_reader")


def test_the_website_can_submit_but_never_read_or_write_directly(conn):
    as_website(conn)
    try:
        assert submit(conn) == "ok"
        assert submit(conn, kind="message", useful=None, topic="idea", message="  A chart of the bill yields.  ") == "ok"
        for forbidden in ("select * from community.feedback",
                          "insert into community.feedback (page, kind, useful) values ('/', 'page_vote', true)",
                          "update community.feedback set status = 'read'",
                          "delete from community.feedback"):
            conn.execute("savepoint s")
            with pytest.raises(Exception, match="permission denied"):
                conn.execute(forbidden)
            conn.execute("rollback to savepoint s")
    finally:
        conn.execute("reset role")
    rows = conn.execute("select kind, useful, topic, message, viewer_tier, status from community.feedback "
                        "order by feedback_id").fetchall()
    assert rows == [
        {"kind": "page_vote", "useful": True, "topic": None, "message": None, "viewer_tier": "free", "status": "new"},
        {"kind": "message", "useful": None, "topic": "idea", "message": "A chart of the bill yields.",
         "viewer_tier": "free", "status": "new"},
    ]


@pytest.mark.parametrize("fields", [
    {"page": "https://evil.example/"},                    # a path on this site only
    {"page": "/a b"},
    {"page": "/" + "x" * 201},
    {"kind": "comment"},
    {"useful": None},                                     # a vote needs its answer
    {"message": "and a message"},                         # ... and nothing else
    {"kind": "message", "useful": None, "topic": "idea", "message": "  "},
    {"kind": "message", "useful": None, "topic": "idea", "message": "x" * 2001},
    {"kind": "message", "useful": None, "topic": "tips", "message": "hello there"},
    {"kind": "message", "useful": None, "topic": None, "message": "hello there"},
    {"tier": "gold"},
    {"key": "not-a-hash"},
    {"key": None},
])
def test_every_field_is_checked_and_nothing_is_stored_when_one_fails(conn, fields):
    assert submit(conn, **fields) == "invalid"
    assert conn.execute("select count(*) n from community.feedback").fetchone()["n"] == 0


def test_one_sender_is_limited_per_hour_without_affecting_others(conn):
    for _ in range(5):
        assert submit(conn, kind="message", useful=None, topic="other", message="hello there") == "ok"
    assert submit(conn, kind="message", useful=None, topic="other", message="hello there") == "limited"
    for _ in range(25):
        assert submit(conn) == "ok"
    assert submit(conn) == "limited"                                   # 30 of anything per hour
    assert submit(conn, key=OTHER) == "ok"
    conn.execute("update community.feedback set received_at = now() - interval '2 hours'")
    assert submit(conn) == "ok"                                        # the limit is per hour


def test_the_senders_key_is_forgotten_after_seven_days(conn):
    assert submit(conn) == "ok"
    conn.execute("update community.feedback set received_at = now() - interval '8 days'")
    assert submit(conn, key=OTHER) == "ok"
    keys = [r["client_key"] for r in conn.execute("select client_key from community.feedback order by feedback_id")]
    assert keys == [None, OTHER]


def test_the_owners_job_summarises_marks_and_deletes(conn):
    submit(conn, useful=True)
    submit(conn, useful=False, key=OTHER)
    submit(conn, page="/cse", kind="message", useful=None, topic="data_error", message="JKH price looks stale")
    out = feedback.summary(conn)
    assert [(r["page"], r["yes"], r["no"]) for r in out["votes"]] == [("/bonds", 1, 1)]
    assert [(r["topic"], r["n"], r["unread"]) for r in out["messages"]] == [("data_error", 1, 1)]
    [msg] = feedback.messages(conn, status="new")
    assert msg["message"] == "JKH price looks stale"
    assert feedback.mark(conn, [msg["feedback_id"]], "read") == 1
    assert feedback.messages(conn, status="new") == []
    assert feedback.delete(conn, [msg["feedback_id"]]) == 1
    assert feedback.messages(conn) == []
    with pytest.raises(ValueError):
        feedback.mark(conn, [1], "published")
