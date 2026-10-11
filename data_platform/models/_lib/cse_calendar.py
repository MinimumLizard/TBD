"""Shared by the CSE models: the session calendar, and the parity-only option to leave sessions out."""
from __future__ import annotations

import datetime as dt

ASPI = "ASI"


def excluded_sessions(inputs) -> set[dt.date]:
    """Sessions whose prices and index values are left out. Used only by parity runs: the old terminal never had
    2026-10-05's prices or index values (its daily job missed them; Phase 2 restored them), so the comparison leaves
    them out on the new side too. (It did capture that day's market summary, which is therefore kept.)"""
    return {dt.date.fromisoformat(d) for d in inputs.params.get("exclude_sessions", [])}


def session_filter(as_of: dt.date | None, column: str = "session_date") -> tuple[str, tuple]:
    return (f"{column} <= %s", (as_of,)) if as_of else ("", ())
