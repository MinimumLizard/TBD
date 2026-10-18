"""DCS CCPI collector: Monthly CCPI page → one page per base year → its PDF → archive → facts.

    python -m data_platform.jobs.collect dcs_cpi

Each run (weekly; the CCPI for a month is published on its last working day):
  1. reads the Monthly CCPI page and follows every "Movements of the CCPI" link (one per base year) to the PDF it
     shows. The PDFs keep their names when the DCS updates them, so every run fetches them again (four files of
     about 300 KB); the archive stores a file once however often it is fetched, and an unchanged file adds nothing;
  2. parses each PDF whose content it has not yet parsed with the current parser, checking every index number
     against the changes printed beside it, and stores the rows as published;
  3. fails loudly if the page lists no table for a base year the platform relies on, or a PDF cannot be read.

Base 1952 (1953 to 2008) is listed too and is skipped without being fetched: the comparison starts in 2003.
"""
from __future__ import annotations

import logging

from ...core.collector import Collector, Result
from .. import rates_store
from . import parse

log = logging.getLogger(__name__)

REQUIRED = {parse.dataset_for(b) for b in parse.BASES}
SKIP_MARKERS = ("1952",)


class DcsCpiCollector(Collector):
    source_id = "dcs_cpi"

    def collect(self) -> Result:
        conn = self.ctx.conn
        index = self.fetch("GET", parse.INDEX_URL, note="Monthly CCPI page")
        pages = parse.parse_index(index.body)
        if not pages:
            raise RuntimeError("the Monthly CCPI page lists no 'Movements of the CCPI' table; its layout has changed")
        done = {r["raw_sha256"] for r in conn.execute(
            """select distinct raw_sha256 from rates.source_files
               where source_id = 'dcs_cpi' and parser_version = %s and parse_status = 'ok'""", (parse.PARSER_VERSION,))}
        added, new_files, failures, seen, skipped = 0, 0, [], set(), []
        for page_url in pages:
            if any(m in page_url for m in SKIP_MARKERS):
                skipped.append(page_url)
                continue
            wrapper = self.fetch("GET", page_url, note="Movements of the CCPI page")
            pdf_url = parse.parse_wrapper(wrapper.body, page_url)
            if any(m in pdf_url for m in SKIP_MARKERS):
                skipped.append(pdf_url)
                continue
            got = self.fetch("GET", pdf_url, note="Movements of the CCPI table")
            if got.sha256 in done:
                dataset = conn.execute("""select dataset from rates.source_files where raw_sha256 = %s
                                          and parse_status = 'ok' limit 1""", (got.sha256,)).fetchone()["dataset"]
                seen.add(dataset)
                continue
            status, n, dataset = rates_store.store_file(
                conn, source_id=self.source_id, dataset="dcs_ccpi_", url=pdf_url, label="Movements of the CCPI",
                file_date=None, fetch_id=got.fetch_id, sha256=got.sha256, fetched_at=got.response.fetched_at,
                body=got.body, parse=parse.parse_ccpi, parser_version=parse.PARSER_VERSION,
                parse_errors=(parse.ParseError,))
            conn.commit()
            done.add(got.sha256)
            new_files += 1
            added += n
            if status == "ok":
                seen.add(dataset)
            else:
                failures.append(pdf_url)
        missing = sorted(REQUIRED - seen)
        message = (f"{len(pages)} tables listed, {len(skipped)} skipped (base 1952), {new_files} new or changed, "
                   f"{len(failures)} failed; {added} rows added; bases {sorted(seen)}")
        if failures or missing:
            raise RuntimeError(message + "".join([
                f". Parse failed: {'; '.join(failures)}" if failures else "",
                f". No table found for {', '.join(missing)}" if missing else ""]))
        return Result(rows_added=added, message=message, new_data=bool(new_files))
