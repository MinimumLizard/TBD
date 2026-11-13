"""The e-mail addresses visitors signed up with (migration 0019). For the owner; uses DATABASE_URL.

    python -m data_platform.jobs.signups summary                      # how many, by starting path and status
    python -m data_platform.jobs.signups list [--status pending]      # pending | confirmed | unsubscribed
    python -m data_platform.jobs.signups export --out <file.csv>      # a file OUTSIDE this repository
    python -m data_platform.jobs.signups unsubscribe someone@example.com
    python -m data_platform.jobs.signups delete someone@example.com   # on the person's request (PDPA)

These are personal data: never commit an export, and write it outside the repository. Nothing is to be e-mailed to a
'pending' address except the one confirmation message; the account system confirms addresses when sign-ins open.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ..core import db, settings as settings_mod

STATUSES = ("pending", "confirmed", "unsubscribed")
REPO = Path(__file__).resolve().parents[2]


def summary(conn) -> dict:
    by_status = conn.execute("select status, count(*) as n, count(*) filter (where wants_weekly) as weekly "
                             "from community.signups group by status order by status").fetchall()
    by_path = conn.execute("select coalesce(starting_type, '-') as type, coalesce(starting_answer, '-') as answer, "
                           "count(*) as n from community.signups where status <> 'unsubscribed' "
                           "group by 1, 2 order by n desc, 1, 2").fetchall()
    return {"by_status": by_status, "by_path": by_path}


def rows(conn, status: str | None = None) -> list[dict]:
    return conn.execute("""select signup_id, email, starting_type, starting_answer, wants_weekly, consent_version,
                                  consented_at, status, confirmed_at
                           from community.signups where (%s::text is null or status = %s)
                           order by signup_id""", (status, status)).fetchall()


def export(conn, out: Path, status: str | None = None) -> int:
    out = out.resolve()
    if out.is_relative_to(REPO):
        raise ValueError("write the export outside this repository: it holds personal data")
    data = rows(conn, status)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["email", "starting_type", "starting_answer", "wants_weekly", "consent_version", "consented_at",
                    "status"])
        for r in data:
            w.writerow([r["email"], r["starting_type"] or "", r["starting_answer"] or "", r["wants_weekly"],
                        r["consent_version"], r["consented_at"].isoformat(), r["status"]])
    return len(data)


def unsubscribe(conn, emails: list[str]) -> int:
    n = conn.execute("update community.signups set status = 'unsubscribed', wants_weekly = false "
                     "where email = any(%s)", ([e.lower() for e in emails],)).rowcount
    conn.commit()
    return n


def delete(conn, emails: list[str]) -> int:
    n = conn.execute("delete from community.signups where email = any(%s)", ([e.lower() for e in emails],)).rowcount
    conn.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_platform.jobs.signups", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary")
    li = sub.add_parser("list")
    li.add_argument("--status", choices=STATUSES)
    ex = sub.add_parser("export")
    ex.add_argument("--out", type=Path, required=True)
    ex.add_argument("--status", choices=STATUSES)
    for name in ("unsubscribe", "delete"):
        sub.add_parser(name).add_argument("emails", nargs="+")
    args = parser.parse_args(argv)

    conn = db.connect(settings_mod.load().database_url)
    db.migrate(conn)
    if args.command == "summary":
        out = summary(conn)
        print("Sign-ups by status  (asked for the weekly summary)")
        for r in out["by_status"]:
            print(f"  {r['status']:<13} {r['n']:>5}  ({r['weekly']})")
        print("By starting path")
        for r in out["by_path"]:
            print(f"  {r['type']:<10} {r['answer']:<10} {r['n']:>5}")
    elif args.command == "list":
        for r in rows(conn, args.status):
            path = f"{r['starting_type']}/{r['starting_answer']}" if r["starting_type"] else "-"
            print(f"#{r['signup_id']}  {r['consented_at']:%Y-%m-%d %H:%M}  {r['email']}  [{path}, "
                  f"{'weekly' if r['wants_weekly'] else 'no weekly'}, {r['status']}]")
    elif args.command == "export":
        print(f"{export(conn, args.out, args.status)} written to {args.out}")
    elif args.command == "unsubscribe":
        print(f"{unsubscribe(conn, args.emails)} unsubscribed")
    else:
        print(f"{delete(conn, args.emails)} deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
