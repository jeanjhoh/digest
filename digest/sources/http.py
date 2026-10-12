"""Shared HTTP session: polite User-Agent, retries with backoff, per-host rate limiting."""
from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}
        self.intervals: dict[str, float] = {}

    def set_rate(self, host: str, rps: float) -> None:
        self.intervals[host] = 1.0 / rps if rps > 0 else 0.0

    def wait(self, host: str) -> None:
        interval = self.intervals.get(host, 1.0)
        with self._lock:
            now = time.monotonic()
            t = max(now, self._next.get(host, now))
            self._next[host] = t + interval
        delay = t - now
        if delay > 0:
            time.sleep(delay)


class Http:
    def __init__(self, user_agent: str, mailto: str, rates: dict[str, float] | None = None, timeout: int = 60) -> None:
        self.session = requests.Session()
        retry = Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "POST"], respect_retry_after_header=True)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = f"{user_agent} (mailto:{mailto})"
        self.session.headers["Accept"] = "application/json, application/xml;q=0.9, */*;q=0.8"
        self.mailto = mailto
        self.timeout = timeout
        self.limiter = RateLimiter()
        for host, rps in (rates or {}).items():
            self.limiter.set_rate(host, rps)

    def get(self, url: str, params: dict[str, Any] | None = None, **kw: Any) -> requests.Response:
        self.limiter.wait(urlparse(url).netloc)
        r = self.session.get(url, params=params, timeout=kw.pop("timeout", self.timeout), **kw)
        r.raise_for_status()
        return r

    def get_json(self, url: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return self.get(url, params=params, **kw).json()

    def post_json(self, url: str, json: Any, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        self.limiter.wait(urlparse(url).netloc)
        r = self.session.post(url, params=params, json=json, timeout=kw.pop("timeout", self.timeout), **kw)
        r.raise_for_status()
        return r.json()


def build_http(settings: Any) -> Http:
    h = settings.http or {}
    rates = {
        "api.crossref.org": float(h.get("crossref_rps", 4)),
        "api.openalex.org": float(h.get("openalex_rps", 5)),
        "api.semanticscholar.org": float(h.get("s2_rps", 1)),
        "export.arxiv.org": 1.0 / float(h.get("arxiv_sleep", 3)),
        "nep.repec.org": 1.0,
        "docs.google.com": 1.0,
    }
    return Http(user_agent=h.get("user_agent", "research-digest/1.0"), mailto=settings.crossref_mailto, rates=rates)
