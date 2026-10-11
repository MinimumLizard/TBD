"""Rebuild the change history of the bond database from git, so no overwritten value is lost.

Why this exists: the Nelson-Siegel pipeline updates rows in place (docs/audit.md, section 3.2). For example, 724 quote
rows that existed on 2026-09-01 now hold different yields after an ISIN-matching fix. The database keeps only the
latest value. But the GitHub Action committed the whole database after every run, so every earlier state is still in
git history. This script walks those commits and writes one SQLite file that records, for every row of every table,
each distinct value it has had and when:

    <table>__history   the table's own columns, plus
                       valid_from_commit, valid_from_at   first commit in which this exact row appeared
                       valid_to_commit,   valid_to_at     first commit in which it no longer appeared (NULL = current)
    versions           every database version read: commit, commit time, message, SHA-256, row counts

"What did the database say about bond X on date D, as of commit C?" is then a plain query. Read-only towards the
source repo: it only runs `git log` and `git show`.

    python scripts/bond_db_history.py --repo path/to/Nelson-Siegel --out bond_db_history.sqlite
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

DB_PATH_IN_REPO = "data/sgcp.sqlite"


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def commits(repo: Path) -> list[tuple[str, str, str]]:
    out = git(repo, "log", "--reverse", "--format=%H%x1f%cI%x1f%s", "--", DB_PATH_IN_REPO).decode()
    return [tuple(line.split("\x1f")) for line in out.splitlines() if line]


def read_tables(db_file: Path) -> dict[str, tuple[list[str], dict[tuple, dict]]]:
    """table -> (columns, {key: row as {column: value}}). Key = declared primary key, else the whole row.

    Rows are dicts because the schema changed over time (columns were added by migrations): a column that does not
    exist yet reads as NULL, so adding an empty column does not count as a change to every row."""
    con = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    tables = {}
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        info = con.execute(f'PRAGMA table_info("{name}")').fetchall()
        cols = [r[1] for r in info]
        pk = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5] > 0] or cols
        rows = {}
        for values in con.execute(f'SELECT * FROM "{name}"'):
            row = {c: v for c, v in zip(cols, values) if v is not None}
            rows[tuple(row.get(c) for c in pk)] = row
        tables[name] = (cols, rows)
    con.close()
    return tables


def verify(repo: Path, out_path: Path, skip: list[str]) -> int:
    """Rebuild every version from the history file and compare it, row by row, with the real database at that commit.
    Returns the number of versions that did not match (0 = the history is a faithful record)."""
    out = sqlite3.connect(out_path)
    seq_of = {sha: seq for seq, sha in out.execute("SELECT seq, commit_sha FROM versions")}
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for seq, sha in sorted((v, k) for k, v in seq_of.items()):
            f = Path(tmp) / "v.sqlite"
            f.write_bytes(git(repo, "show", f"{sha}:{DB_PATH_IN_REPO}"))
            real = {t: v for t, v in read_tables(f).items() if t not in skip}
            for name, (cols, rows) in real.items():
                meta = ("valid_from_commit", "valid_from_at", "valid_to_commit", "valid_to_at")
                hcols = [r[1] for r in out.execute(f'PRAGMA table_info("{name}__history")') if r[1] not in meta]
                names = ", ".join(f'"{c}"' for c in hcols)
                rebuilt = []
                for r in out.execute(f'SELECT {names}, valid_from_commit, valid_to_commit FROM "{name}__history"'):
                    vf, vt = seq_of[r[-2]], (seq_of[r[-1]] if r[-1] else None)
                    if vf <= seq and (vt is None or seq < vt):
                        rebuilt.append({c: v for c, v in zip(hcols, r[:-2]) if v is not None})
                key = lambda d: repr(sorted(d.items()))  # noqa: E731
                if sorted(map(key, rebuilt)) != sorted(map(key, rows.values())):
                    print(f"MISMATCH v{seq} {sha[:7]} {name}: rebuilt {len(rebuilt)} rows, real {len(rows)}",
                          file=sys.stderr)
                    bad += 1
    print(f"verify: {len(seq_of)} versions checked, {bad} table mismatches")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--skip", nargs="*", default=["switch_signals"],
                    help="tables to leave out (default: switch_signals, which is derived, rebuilt wholesale on every "
                         "run and reproducible from curve_residuals + auctions; including it adds ~2M row versions)")
    args = ap.parse_args()
    if args.out.exists():
        sys.exit(f"{args.out} exists; remove it first (this script builds the history from scratch)")

    out = sqlite3.connect(args.out)
    out.execute("""CREATE TABLE versions (seq INTEGER PRIMARY KEY, commit_sha TEXT, committed_at TEXT, message TEXT,
                   db_sha256 TEXT, tables_json TEXT)""")
    open_rows: dict[str, dict[tuple, tuple]] = {}   # table -> key -> (row, valid_from_commit, valid_from_at)
    hist_cols: dict[str, list[str]] = {}               # table -> columns of its history table so far

    def close(name: str, row: dict, fsha: str, fat: str, tsha, tat) -> None:
        cols = [c for c in hist_cols[name]]
        values = [row.get(c) for c in cols]
        names = ", ".join(f'"{c}"' for c in cols)
        out.execute(f'INSERT INTO "{name}__history" ({names}, valid_from_commit, valid_from_at, valid_to_commit, '
                    f'valid_to_at) VALUES ({",".join("?" * (len(cols) + 4))})', (*values, fsha, fat, tsha, tat))

    prev_sha = None
    seq = 0
    with tempfile.TemporaryDirectory() as tmp:
        for sha, at, msg in commits(args.repo):
            blob = git(args.repo, "show", f"{sha}:{DB_PATH_IN_REPO}")
            digest = hashlib.sha256(blob).hexdigest()
            if digest == prev_sha:
                continue                      # same bytes as the previous version: nothing changed
            prev_sha = digest
            seq += 1
            f = Path(tmp) / "v.sqlite"
            f.write_bytes(blob)
            tables = {t: v for t, v in read_tables(f).items() if t not in args.skip}
            counts = {t: len(v[1]) for t, v in tables.items()}
            out.execute("INSERT INTO versions VALUES (?,?,?,?,?,?)",
                        (seq, sha, at, msg, digest, repr(sorted(counts.items()))))
            for name, (cols, rows) in tables.items():
                if name not in hist_cols:
                    coldefs = ", ".join(f'"{c}"' for c in cols)
                    out.execute(f'CREATE TABLE "{name}__history" ({coldefs}, valid_from_commit TEXT, '
                                f'valid_from_at TEXT, valid_to_commit TEXT, valid_to_at TEXT)')
                    hist_cols[name] = list(cols)
                    open_rows[name] = {}
                for c in cols:
                    if c not in hist_cols[name]:   # a migration added a column
                        out.execute(f'ALTER TABLE "{name}__history" ADD COLUMN "{c}"')
                        hist_cols[name].append(c)
                current = open_rows[name]
                for k, (row, fsha, fat) in list(current.items()):
                    if rows.get(k) != row:     # changed or deleted: close the old version
                        close(name, row, fsha, fat, sha, at)
                        del current[k]
                for k, row in rows.items():
                    if k not in current:       # new or changed: open a version
                        current[k] = (row, sha, at)
            for name in set(open_rows) - set(tables):   # a table that vanished closes all its rows
                for row, fsha, fat in open_rows[name].values():
                    close(name, row, fsha, fat, sha, at)
                open_rows[name] = {}
            print(f"v{seq} {sha[:7]} {at} {sum(counts.values())} rows", file=sys.stderr, flush=True)
    for name, current in open_rows.items():           # still open at the end = current values
        for row, fsha, fat in current.values():
            close(name, row, fsha, fat, None, None)
    out.commit()
    out.close()
    print(f"done: {seq} distinct database versions -> {args.out}")
    return 1 if verify(args.repo, args.out, args.skip) else 0


if __name__ == "__main__":
    sys.exit(main())
