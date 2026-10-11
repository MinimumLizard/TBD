"""Re-download every PDMO file the bond database says it parsed, and prove each one is unchanged.

Why this exists: the Nelson-Siegel pipeline parses each PDMO report and then throws the file away, so the database is
the only record of what the files said (docs/audit.md, F2). But its `files` table kept each file's URL and SHA-256
fingerprint at download time. Downloading the files again and comparing fingerprints gives back bit-for-bit copies
of the originals, provided the PDMO still serves them, and proves they were not changed since.

Read-only towards the bond repo: it only reads the database file you point it at.

    python scripts/archive_pdmo_files.py --db path/to/sgcp.sqlite --out path/to/archive

Output:
    <out>/files/<sha256>.<ext>   each file, named by its fingerprint (identical files are stored once)
    <out>/manifest.csv           one row per URL: what the database expected, what we got, and whether they match

Safe to re-run: files already in <out>/files with the right fingerprint are not downloaded again.
Polite like the original pipeline: one request at a time, 1.5 s apart, honest User-Agent, retries with backoff.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import sqlite3
import sys
import time
from pathlib import Path

import requests

USER_AGENT = "tbd-archive/0.1 (one-off provenance check of previously downloaded PDMO reports)"
DELAY_SECONDS = 1.5
RETRIES = 4
CHALLENGE_MARKERS = (b"sucuri_cloudproxy", b"You are being redirected", b"Javascript is required")
MANIFEST_COLS = ["url", "file_type", "report_date", "posted_date", "expected_sha256", "got_sha256", "bytes",
                 "content_type", "status", "fetched_at_utc"]


def extension(body: bytes, content_type: str) -> str:
    """Name files by what they are, not by what the link claims (the PDMO's "PDFs" are often .xls)."""
    if body.startswith(b"%PDF"):
        return "pdf"
    if body.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if body.startswith(b"PK\x03\x04"):
        return "zip"
    return "bin" if "html" not in content_type else "html"


def fetch(session: requests.Session, url: str) -> requests.Response:
    last: Exception | None = None
    for attempt in range(RETRIES):
        time.sleep(DELAY_SECONDS if attempt == 0 else 2 ** attempt)
        try:
            r = session.get(url, timeout=60, allow_redirects=True)
            if r.status_code >= 300:
                raise requests.RequestException(f"HTTP {r.status_code}")
            if len(r.content) <= 8192 and any(m in r.content for m in CHALLENGE_MARKERS):
                raise requests.RequestException("bot-challenge page served instead of the file")
            return r
        except requests.RequestException as exc:
            last = exc
    raise RuntimeError(f"{url}: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, type=Path, help="the bond repo's data/sgcp.sqlite (read only)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rows = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True).execute(
        "SELECT url, file_type, report_date, posted_date, sha256 FROM files ORDER BY report_date, url").fetchall()
    (args.out / "files").mkdir(parents=True, exist_ok=True)
    have = {p.stem: p for p in (args.out / "files").iterdir()}
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    out_rows, counts = [], {}
    for i, (url, file_type, report_date, posted_date, expected) in enumerate(rows, 1):
        row = {"url": url, "file_type": file_type, "report_date": report_date, "posted_date": posted_date,
               "expected_sha256": expected, "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if expected and expected in have:
            row.update(got_sha256=expected, bytes=have[expected].stat().st_size, content_type="",
                       status="match (already archived)")
        else:
            try:
                r = fetch(session, url)
                got = hashlib.sha256(r.content).hexdigest()
                ctype = r.headers.get("content-type", "")
                path = args.out / "files" / f"{got}.{extension(r.content, ctype)}"
                tmp = path.with_suffix(path.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.rename(path)
                have[got] = path
                status = "match" if got == expected else ("no expected hash" if not expected else "MISMATCH")
                row.update(got_sha256=got, bytes=len(r.content), content_type=ctype, status=status)
            except Exception as exc:  # noqa: BLE001 - recorded in the manifest, the run continues
                row.update(got_sha256="", bytes="", content_type="", status=f"FAILED: {exc}"[:200])
        counts[row["status"].split(":")[0]] = counts.get(row["status"].split(":")[0], 0) + 1
        out_rows.append(row)
        if i % 50 == 0:
            print(f"{i}/{len(rows)} {counts}", file=sys.stderr, flush=True)

    with (args.out / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    print(f"done: {len(rows)} urls, {counts}")
    return 0 if not any(k.startswith(("MISMATCH", "FAILED")) for k in counts) else 1


if __name__ == "__main__":
    sys.exit(main())
