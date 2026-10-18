"""CBSL collector: statistical-tables pages → current file links → archive → facts.

    python -m data_platform.jobs.collect cbsl

Each run (weekly; the monthly table is updated around the 10th of each month):
  1. reads the monetary-sector and fiscal-sector statistical-tables pages and finds the current links for table 4.04
     (monthly interest rates), table 4.03 (annual) and the weekly treasury bill auction file. The file names carry
     the date of the update, so a new name means a new version;
  2. fetches each file whose address it has not yet parsed with the current parser, archives it, parses it and
     stores its rows as published. Each file holds the table's whole history, so its rows are stored in full;
  3. fails loudly when a page no longer lists a wanted file exactly once, or a newly fetched file cannot be read.

The treasury bill auction file has not been updated since 24 December 2025 (its last auction is 28 November 2025);
current bill yields come from table 4.04 and from our own PDMO data.
"""
from __future__ import annotations

import logging

from ...core.collector import Collector, Result
from .. import rates_store
from . import index, parse

log = logging.getLogger(__name__)


class CbslCollector(Collector):
    source_id = "cbsl"

    def read_indexes(self) -> list[index.FileLink]:
        links = []
        for page, url in index.PAGES.items():
            got = self.fetch("GET", url, note=f"{page} index")
            links.extend(index.parse_index(got.body, page))
        return links

    def collect(self) -> Result:
        conn = self.ctx.conn
        links = self.read_indexes()
        known = {r["url"] for r in conn.execute(
            """select distinct url from rates.source_files
               where source_id = 'cbsl' and parser_version = %s and parse_status = 'ok'""", (parse.PARSER_VERSION,))}
        todo = [link for link in links if link.url not in known]
        added, failures = 0, []
        for link in todo:
            got = self.fetch("GET", link.url, note=link.dataset)
            status, n, _ = rates_store.store_file(
                conn, source_id=self.source_id, dataset=link.dataset, url=link.url, label=link.label,
                file_date=link.file_date, fetch_id=got.fetch_id, sha256=got.sha256,
                fetched_at=got.response.fetched_at, body=got.body, parse=parse.PARSERS[link.dataset],
                parser_version=parse.PARSER_VERSION, parse_errors=(parse.ParseError,))
            conn.commit()
            added += n
            if status != "ok":
                failures.append(link.url)
        message = (f"{len(links)} files listed ({', '.join(f'{x.dataset} {x.file_date}' for x in links)}), "
                   f"{len(todo)} new, {len(failures)} failed; {added} rows added")
        if failures:
            raise RuntimeError(message + ". Parse failed: " + "; ".join(failures))
        return Result(rows_added=added, message=message, new_data=bool(todo))
