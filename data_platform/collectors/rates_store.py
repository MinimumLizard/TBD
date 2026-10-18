"""Storing a parsed rates file (CBSL tables, DCS CPI tables) in the `rates` schema. Shared by both collectors.

Every file is recorded in rates.source_files, parsed or not; its facts go to the table for its dataset, append-only,
keyed by the archived file and the parser version (db/migrations/0011_rates_and_savings.sql).
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

from ..core import db

# dataset (or dataset prefix) -> (fact table, the columns that identify a row within one file)
TABLES = {
    "cbsl_4.04": ("rates.cbsl_monthly", ["series", "month"]),
    "cbsl_4.03": ("rates.cbsl_annual", ["series", "year"]),
    "cbsl_tbill_auctions": ("rates.tbill_auctions", ["issue_date", "tenor_days"]),
    "dcs_ccpi_": ("rates.cpi_monthly", ["index_code", "base", "month"]),
}


def table_for(dataset: str) -> tuple[str, list[str]]:
    for prefix, spec in TABLES.items():
        if dataset == prefix or (prefix.endswith("_") and dataset.startswith(prefix)):
            return spec
    raise KeyError(f"no fact table for dataset {dataset!r}")


def store_file(conn, *, source_id: str, dataset: str, url: str, label: str | None, file_date: dt.date | None,
               fetch_id: int, sha256: str, fetched_at: dt.datetime, body: bytes, parse: Callable,
               parser_version: int, parse_errors: tuple[type[Exception], ...]) -> tuple[str, int, str]:
    """Parse one archived file and append its facts. Returns (parse_status, rows added, dataset).

    `dataset` is what the index page said the file is; a parser may name it more exactly (a DCS file's base year is
    read from its own title). A parse failure is recorded against the file, not raised."""
    try:
        parsed = parse(body)
        status, note = "ok", parsed.note
        if parsed.dataset != dataset and not (dataset.endswith("_") and parsed.dataset.startswith(dataset)):
            raise ValueError(f"the page lists this file as {dataset}, but it reads as {parsed.dataset}")
        dataset = parsed.dataset
    except parse_errors as exc:
        parsed, status, note = None, "failed", str(exc)
    except Exception as exc:  # noqa: BLE001 - an unexpected parser crash is recorded the same way, with its type
        parsed, status, note = None, "failed", f"{type(exc).__name__}: {exc}"

    added = 0
    if parsed is not None:
        table, key = table_for(dataset)
        rows = [dict(r, raw_sha256=sha256, parser_version=parser_version, fetched_at=fetched_at) for r in parsed.rows]
        added, _ = db.insert_facts(conn, table, rows, key=["raw_sha256", "parser_version", *key], fetch_id=fetch_id)
    db.insert_facts(conn, "rates.source_files", [{
        "url": url, "raw_sha256": sha256, "fetch_id": fetch_id, "parser_version": parser_version,
        "source_id": source_id, "dataset": dataset.rstrip("_") if parsed is None else dataset,
        "file_date": file_date, "label": label, "parse_status": status, "parse_note": note[:1000],
        "rows_parsed": len(parsed.rows) if parsed else 0,
    }], key=["url", "raw_sha256", "parser_version"], fetch_id=fetch_id)
    return status, added, dataset
