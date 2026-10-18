"""Read what visitors sent through the site's feedback forms (migration 0012). For the owner; uses DATABASE_URL.

    python -m data_platform.jobs.feedback summary                     # page votes and messages, last 30 days
    python -m data_platform.jobs.feedback list [--status new] [--days 30]
    python -m data_platform.jobs.feedback mark 12 13 --status read     # read | actioned | spam
    python -m data_platform.jobs.feedback delete 12                    # on the sender's request (PDPA)

Nothing visitors write is ever shown on the site, so nothing here needs moderating before it is published.
"""
from __future__ import annotations

import argparse
import sys

from ..core import db, settings as settings_mod

STATUSES = ("new", "read", "actioned", "spam")


def summary(conn, days: int = 30) -> dict:
    votes = conn.execute("""select page, count(*) filter (where useful) as yes, count(*) filter (where not useful) as no
                            from community.feedback
                            where kind = 'page_vote' and received_at > now() - make_interval(days => %s)
                            group by page order by count(*) desc, page""", (days,)).fetchall()
    messages = conn.execute("""select topic, count(*) as n, count(*) filter (where status = 'new') as unread
                               from community.feedback
                               where kind = 'message' and received_at > now() - make_interval(days => %s)
                               group by topic order by topic""", (days,)).fetchall()
    return {"days": days, "votes": votes, "messages": messages}


def messages(conn, status: str | None = None, days: int = 30) -> list[dict]:
    return conn.execute("""select feedback_id, received_at, page, topic, viewer_tier, status, message
                           from community.feedback
                           where kind = 'message' and received_at > now() - make_interval(days => %s)
                             and (%s::text is null or status = %s)
                           order by received_at""", (days, status, status)).fetchall()


def mark(conn, ids: list[int], status: str) -> int:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    n = conn.execute("update community.feedback set status = %s, reviewed_at = now() where feedback_id = any(%s)",
                     (status, ids)).rowcount
    conn.commit()
    return n


def delete(conn, ids: list[int]) -> int:
    n = conn.execute("delete from community.feedback where feedback_id = any(%s)", (ids,)).rowcount
    conn.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_platform.jobs.feedback", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--days", type=int, default=30)
    li = sub.add_parser("list")
    li.add_argument("--status", choices=STATUSES)
    li.add_argument("--days", type=int, default=30)
    m = sub.add_parser("mark")
    m.add_argument("ids", type=int, nargs="+")
    m.add_argument("--status", choices=STATUSES, required=True)
    d = sub.add_parser("delete")
    d.add_argument("ids", type=int, nargs="+")
    args = parser.parse_args(argv)

    conn = db.connect(settings_mod.load().database_url)
    db.migrate(conn)
    if args.command == "summary":
        out = summary(conn, args.days)
        print(f"Last {out['days']} days")
        print("Was this page useful?  (yes / no)")
        for r in out["votes"]:
            print(f"  {r['page']:<50} {r['yes']:>4} / {r['no']:<4}")
        print("Messages by topic  (unread)")
        for r in out["messages"]:
            print(f"  {r['topic']:<12} {r['n']:>4}  ({r['unread']})")
    elif args.command == "list":
        for r in messages(conn, args.status, args.days):
            print(f"#{r['feedback_id']}  {r['received_at']:%Y-%m-%d %H:%M}  {r['page']}  [{r['topic']}, "
                  f"{r['viewer_tier'] or '?'}, {r['status']}]")
            print("    " + r["message"].replace("\n", "\n    "))
    elif args.command == "mark":
        print(f"{mark(conn, args.ids, args.status)} marked {args.status}")
    else:
        print(f"{delete(conn, args.ids)} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
