"""The crypto section against independent public reference points (data_platform/jobs/crosscheck_crypto.py).

Needs Bitstamp's full history, which is never committed (the repository is public and the data is licensed), so it
runs only when CROSSCHECK_DATABASE_URL points at a database with the history collected and the crypto models
computed. Otherwise it is skipped, never silently passed:

    CROSSCHECK_DATABASE_URL=postgresql://... uv run pytest tests/test_crypto_crosscheck.py
"""
from __future__ import annotations

import os

import pytest

from data_platform.jobs import crosscheck_crypto


@pytest.fixture(scope="module")
def checks():
    url = os.environ.get("CROSSCHECK_DATABASE_URL")
    if not url:
        pytest.skip("CROSSCHECK_DATABASE_URL not set (needs the full Bitstamp history)")
    from data_platform.core import db

    with db.connect(url) as conn:
        return crosscheck_crypto.run(conn)


def test_every_reference_point_is_met(checks):
    failed = [f"{c.group}: {c.name}: measured {c.measured}, reference {c.reference}" for c in checks if not c.passed]
    assert not failed, "\n".join(failed)


def test_the_checks_cover_what_the_review_lists(checks):
    groups = {c.group for c in checks}
    assert {"Pi cycle", "200-week average", "Cycle table", "Halvings", "BTC closes"} <= groups
    assert sum(c.group == "Cycle table" for c in checks) == 7


def test_the_halving_dates_are_the_explorers():
    assert all(c.passed for c in crosscheck_crypto.halvings())
