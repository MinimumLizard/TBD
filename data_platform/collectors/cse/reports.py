"""CSE interim and annual reports, as text:  python -m data_platform.jobs.collect cse_api:reports   (weekly)

The old terminal's cse/ownership/collect.py, on the platform's rails:
  * for each company (its voting line where it has one), `financials` lists its filed reports. The newest quarterly
    report is taken (by period, then upload time); a company with no quarterly filing gets its newest annual report;
  * a report already collected is never fetched again; a failed download is retried by the next run;
  * the PDF is fetched politely (one request a second per host, through the shared client) and ARCHIVED (the old
    terminal kept only the text), then converted with `pdftotext -layout`. The text is archived too, under its own
    SHA-256, and stored in cse.report_texts; the index row goes to cse.financial_reports;
  * a text of 200 words or fewer is `no_text` (a scanned image without a text layer; not OCR'd), as before.

One company failing never stops the others: each is committed on its own, and the run fails at the end, naming them.
"""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import tempfile
from pathlib import Path

from ...core import db
from ...core.collector import Result
from ...core.http import FetchError
from . import parse
from .collector import CseCollector

MIN_WORDS = 200              # old collect: more than 200 words is a text; fewer is a scanned image


def pdftotext_version() -> str:
    out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True, timeout=30)
    first = (out.stderr or out.stdout).splitlines()
    return f"pdftotext -layout ({first[0].strip()})" if first else "pdftotext -layout"


def pdf_to_text(content: bytes) -> tuple[str, int]:
    """(text, pages), exactly as the old collector converted a PDF."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "r.pdf"
        pdf.write_bytes(content)
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=300)
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=60).stdout
    pages = next((int(ln.split()[-1]) for ln in info.splitlines() if ln.startswith("Pages:")), 0)
    return txt.stdout, pages


def text_status(text: str) -> tuple[str, int]:
    words = len(text.split())
    return ("ok" if words > MIN_WORDS else "no_text"), words


def store_text(conn, store, body: bytes) -> str:
    """Archive a report's text (content-addressed, write-once) and keep it in cse.report_texts. Returns its SHA-256.
    Shared with the migration, whose text files are already archived."""
    obj = store.put(body, "txt")
    conn.execute("""insert into ops.raw_objects (sha256, bytes, content_type, ext, storage_key)
                    values (%s, %s, %s, %s, %s) on conflict (sha256) do nothing""",
                 (obj.sha256, obj.bytes, "text/plain; charset=utf-8", obj.ext, obj.key))
    add_text(conn, obj.sha256, body)
    return obj.sha256


def add_text(conn, sha256: str, body: bytes) -> None:
    text = body.decode("utf-8", errors="replace").replace("\x00", "�")   # Postgres text cannot hold NUL
    conn.execute("""insert into cse.report_texts (sha256, body, words) values (%s, %s, %s)
                    on conflict (sha256) do nothing""", (sha256, text, len(text.split())))


def store_report(conn, row: dict) -> int:
    """One index row (append-only; the same attempt stored twice adds nothing)."""
    added, _ = db.insert_facts(conn, "cse.financial_reports", [row], key=["report_id", "fetched_at"])
    return added


class CseReportsCollector(CseCollector):
    job = "reports"

    def collect(self) -> Result:
        if not shutil.which("pdftotext") or not shutil.which("pdfinfo"):
            raise RuntimeError("pdftotext / pdfinfo not found: install poppler-utils")
        conn = self.ctx.conn
        extractor = pdftotext_version()
        secs_f = self.api("allSecurityCode")
        symbols = parse.company_symbols(self.companies(parse.security_list(secs_f.body, self.ctx.today_slt)))
        known = {r["report_id"] for r in conn.execute(
            "select distinct report_id from cse.financial_reports where status <> 'download_failed'")}
        new = failed_downloads = 0
        failed: list[str] = []
        for symbol in symbols:
            try:
                f = self.api("financials", symbol=symbol)
                picked = parse.pick_report(parse.financials(f.body, symbol))
                if picked and int(picked[1]["id"]) not in known:
                    entry = parse.report_entry(symbol.split(".")[0], symbol, picked[0], picked[1])
                    ok = self.download(entry, f, extractor)
                    new += 1
                    if ok:
                        known.add(entry["report_id"])
                    else:
                        failed_downloads += 1
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - recorded and raised at the end of the run
                conn.rollback()
                failed.append(f"{symbol} ({type(exc).__name__}: {exc})"[:200])
        message = (f"{len(symbols)} companies: {new} new reports ({failed_downloads} download failures, retried next "
                   f"run; {self.fetches} requests)")
        if failed:
            raise RuntimeError(f"{message}; {len(failed)} companies failed: " + "; ".join(failed[:20]))
        return Result(rows_added=new, new_data=bool(new), message=message)

    def download(self, entry: dict, listing, extractor: str) -> bool:
        """Fetch, archive and convert one report. False: the download failed (recorded, retried next run)."""
        try:
            pdf = self.fetch("GET", entry["url"], note="report PDF")
            content = pdf.body if pdf.body[:4] == b"%PDF" else None
        except FetchError:
            pdf, content = None, None
        if content is None:
            store_report(self.ctx.conn, dict(entry, pages=None, words=None, status="download_failed", pdf_sha256=None,
                                             text_sha256=None, extracted_by=None, fetch_id=listing.fetch_id,
                                             fetched_at=dt.datetime.now(dt.timezone.utc)))
            return False
        text, pages = pdf_to_text(content)
        status, words = text_status(text)
        sha = store_text(self.ctx.conn, self.ctx.store, text.encode())
        store_report(self.ctx.conn, dict(entry, pages=pages, words=words, status=status, pdf_sha256=pdf.sha256,
                                         text_sha256=sha, extracted_by=extractor, fetch_id=pdf.fetch_id,
                                         fetched_at=pdf.response.fetched_at))
        return True
