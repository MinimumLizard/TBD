"""The one HTTP client every collector uses, so politeness and error handling can't be forgotten.

Rules (carried over from all three old projects, where each was learned the hard way):
  * one request at a time per host, with a minimum gap between them;
  * an honest User-Agent that says who we are;
  * retries with exponential backoff on network errors, 429 and 5xx; other errors fail immediately;
  * a firewall challenge page is an ERROR, not content. treasury.gov.lk's Sucuri firewall answers bots with
    HTTP 307 and a JavaScript page, which would otherwise look like a successful, empty response;
  * 204 No Content is returned as an empty body (the CSE uses it for "no detail for this announcement").
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests

USER_AGENT = "tbd-market-data/0.1 (Sri Lankan market information service; contact via github.com/MinimumLizard)"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
CHALLENGE_MARKERS = (b"sucuri_cloudproxy", b"You are being redirected", b"Javascript is required",
                     b"cf-browser-verification", b"Just a moment...")


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    method: str
    url: str
    params: dict
    status: int
    body: bytes
    content_type: str | None
    fetched_at: dt.datetime


@dataclass
class PoliteClient:
    min_interval: float = 1.0                 # seconds between requests to the same host
    retries: int = 3
    timeout: float = 60.0
    session: requests.Session = field(default_factory=requests.Session)
    sleep: callable = time.sleep
    _last: dict = field(default_factory=dict)

    def __post_init__(self):
        self.session.headers["User-Agent"] = USER_AGENT
        self.calls = 0

    def _wait(self, host: str) -> None:
        gap = time.monotonic() - self._last.get(host, 0.0)
        if gap < self.min_interval:
            self.sleep(self.min_interval - gap)
        self._last[host] = time.monotonic()

    def request(self, method: str, url: str, params: dict | None = None) -> Response:
        params = dict(params or {})
        host = urlsplit(url).netloc
        last_error = None
        for attempt in range(self.retries + 1):
            if attempt:
                self.sleep(2 ** attempt)
            self._wait(host)
            self.calls += 1
            try:
                if method == "GET":
                    r = self.session.get(url, params=params or None, timeout=self.timeout, allow_redirects=True)
                else:
                    r = self.session.post(url, data=params, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                last_error = exc
                continue
            if r.status_code in RETRY_STATUSES:
                last_error = FetchError(f"HTTP {r.status_code}")
                continue
            if 300 <= r.status_code < 400:
                raise FetchError(f"{method} {url}: HTTP {r.status_code} redirect not followed (likely a bot challenge)")
            if r.status_code not in (200, 204):
                raise FetchError(f"{method} {url} {params}: HTTP {r.status_code}: {r.text[:200]}")
            body = r.content if r.status_code == 200 else b""
            if len(body) <= 8192 and any(m in body for m in CHALLENGE_MARKERS):
                raise FetchError(f"{method} {url}: a bot-challenge page was served instead of the content")
            return Response(method, url, params, r.status_code, body, r.headers.get("content-type"),
                            dt.datetime.now(dt.timezone.utc))
        raise FetchError(f"{method} {url} {params}: failed after {self.retries} retries: {last_error}")

    def get(self, url: str, params: dict | None = None) -> Response:
        return self.request("GET", url, params)

    def post(self, url: str, params: dict | None = None) -> Response:
        return self.request("POST", url, params)
