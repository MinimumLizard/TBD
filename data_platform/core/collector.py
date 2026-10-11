"""Layer 3's common shape: every collector is a subclass of Collector, run by run_collector().

What a collector writes (by convention, enforced by review and tests):
    collect()       orchestrates one run: decide what's missing, fetch it, parse it, store it
    self.fetch()    the ONLY way to make a request. It archives the response (layer 1) and catalogues it
                    (ops.raw_fetches) and commits that immediately, before anything is parsed
    parse_*()       pure module-level functions: bytes in, rows out. No network, no database. That is what lets
                    migration replay the old repos' raw files through the very same code
    validate        inside parse_* (pydantic models / explicit checks): raise with a clear message, never guess
    store           core.db.insert_facts: append-only, idempotent, conflicts recorded

What run_collector() does for every collector, so none can forget it:
    rights gate (config/sources.yaml) → run log row → collect() → commit facts, or roll them back on error
    (raw fetches are already committed) → close the run log → Healthchecks.io ping
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import subprocess
import traceback
from dataclasses import dataclass, field

import psycopg
import requests

from . import db, rawstore, sources
from .http import PoliteClient, Response
from .settings import REPO_ROOT, Settings

log = logging.getLogger(__name__)
SLT = dt.timezone(dt.timedelta(hours=5, minutes=30), "Asia/Colombo")


@dataclass
class Fetched:
    response: Response
    fetch_id: int
    sha256: str

    @property
    def body(self) -> bytes:
        return self.response.body


@dataclass
class Result:
    rows_added: int = 0
    message: str = ""
    new_data: bool = True
    conflicts: int = 0


@dataclass
class Context:
    conn: psycopg.Connection
    store: rawstore.RawStore
    http: PoliteClient
    run_id: int | None = None
    now: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def today_slt(self) -> dt.date:
        return self.now.astimezone(SLT).date()


class Collector:
    source_id: str = ""
    job: str = "collect"

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.fetches = 0

    def fetch(self, method: str, url: str, params: dict | None = None, *, note: str | None = None) -> Fetched:
        response = self.ctx.http.request(method, url, params)
        fetch_id, digest = db.record_fetch(
            self.ctx.conn, self.ctx.store, source_id=self.source_id, method=method, url=url, params=params,
            http_status=response.status, body=response.body, content_type=response.content_type,
            fetched_at=response.fetched_at, run_id=self.ctx.run_id, note=note)
        self.ctx.conn.commit()          # raw first: a later failure can never lose what was fetched
        self.fetches += 1
        return Fetched(response, fetch_id, digest)

    def collect(self) -> Result:
        raise NotImplementedError


def code_version() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - outside git (e.g. a packaged install) the version is unknown, not fatal
        return "unknown"


def ping(settings: Settings, slug: str, signal: str = "") -> None:
    """Healthchecks.io dead-man's switch: start / success / fail. Silently skipped when not configured."""
    if not settings.healthchecks_base_url:
        return
    url = f"{settings.healthchecks_base_url.rstrip('/')}/{slug}" + (f"/{signal}" if signal else "")
    try:
        requests.get(url, timeout=10)
    except requests.RequestException as exc:  # monitoring must never break collection
        log.warning("healthchecks ping %s failed: %s", url, exc)


def run_collector(cls: type[Collector], settings: Settings, *, conn: psycopg.Connection | None = None,
                  store: rawstore.RawStore | None = None, http: PoliteClient | None = None,
                  now: dt.datetime | None = None) -> Result:
    slug = f"{cls.source_id}-{cls.job}".replace("_", "-")
    try:
        sources.require_runnable(cls.source_id)
    except sources.SourceNotRunnable as exc:
        log.warning("skipped: %s", exc)
        return Result(new_data=False, message=f"skipped: {exc}")

    conn = conn or db.connect(settings.database_url)
    store = store or rawstore.from_settings(settings)
    http = http or PoliteClient()
    run_id = conn.execute(
        "insert into ops.collector_runs (source_id, job, code_version) values (%s, %s, %s) returning run_id",
        (cls.source_id, cls.job, code_version())).fetchone()["run_id"]
    conn.commit()
    ping(settings, slug, "start")
    ctx = Context(conn, store, http, run_id, now or dt.datetime.now(dt.timezone.utc))
    collector = cls(ctx)
    try:
        result = collector.collect()
        conn.commit()
        status = "ok" if result.new_data else "no_new_data"
        conn.execute("""update ops.collector_runs set finished_at = now(), status = %s, fetches = %s,
                        rows_added = %s, message = %s where run_id = %s""",
                     (status, collector.fetches, result.rows_added, result.message[:2000], run_id))
        conn.commit()
        ping(settings, slug)
        return result
    except BaseException as exc:
        conn.rollback()                 # facts from this run are discarded; raw fetches were already committed
        conn.execute("""update ops.collector_runs set finished_at = now(), status = 'failed', fetches = %s,
                        message = %s where run_id = %s""",
                     (collector.fetches, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"[:4000], run_id))
        conn.commit()
        ping(settings, slug, "fail")
        raise
