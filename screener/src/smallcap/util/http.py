"""A small, polite HTTP client for public financial data endpoints.

Three things matter when pulling thousands of filings from SEC EDGAR:

* **Identify yourself.** EDGAR blocks anonymous bulk traffic; a descriptive
  ``User-Agent`` with a contact address is required by their access policy.
* **Stay under the rate limit.** EDGAR's published ceiling is 10 requests per
  second. The limiter below is process-wide and shared across worker threads.
* **Cache.** A companyfacts document is several megabytes and changes only
  when a new filing lands, so re-fetching it during a screening run is pure
  waste -- and rude.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class HTTPError(RuntimeError):
    """A request failed after exhausting retries."""

    def __init__(self, url: str, status: Optional[int], message: str):
        super().__init__(f"{url}: {message}")
        self.url = url
        self.status = status


class RateLimiter:
    """Process-wide minimum spacing between requests."""

    def __init__(self, min_interval: float):
        self.min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                delay = self._next_allowed - now
            else:
                delay = 0.0
            self._next_allowed = max(now, self._next_allowed) + self.min_interval
        if delay > 0:
            time.sleep(delay)


class DiskCache:
    """Content-addressed response cache with a TTL.

    Keyed on the URL so a run can be replayed offline, and so a failed run can
    be resumed without re-downloading what already succeeded.
    """

    def __init__(self, directory: str, ttl_hours: float):
        self.directory = directory
        self.ttl_seconds = ttl_hours * 3600.0
        self._lock = threading.Lock()

    def _path(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.directory, digest[:2], digest + ".json.gz")

    def get(self, key: str) -> Optional[bytes]:
        path = self._path(key)
        try:
            stat = os.stat(path)
        except OSError:
            return None
        if self.ttl_seconds > 0 and time.time() - stat.st_mtime > self.ttl_seconds:
            return None
        try:
            with gzip.open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

    def put(self, key: str, payload: bytes) -> None:
        path = self._path(key)
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # Write-then-rename so a crash never leaves a truncated entry that
            # a later run would happily read back as real data.
            tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                with gzip.open(tmp, "wb") as handle:
                    handle.write(payload)
                os.replace(tmp, path)
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass


class HttpClient:
    """Cached, rate-limited, retrying GET client."""

    def __init__(
        self,
        user_agent: str,
        cache_dir: str = ".cache/smallcap",
        cache_ttl_hours: float = 24.0,
        min_interval: float = 0.12,
        max_retries: int = 4,
        timeout: float = 30.0,
        offline: bool = False,
    ):
        self.user_agent = user_agent
        self.cache = DiskCache(cache_dir, cache_ttl_hours)
        self.limiter = RateLimiter(min_interval)
        self.max_retries = max_retries
        self.timeout = timeout
        # In offline mode only the cache is consulted; a miss is an error
        # rather than a silent network call.
        self.offline = offline

    def get(self, url: str, accept: str = "application/json") -> bytes:
        cached = self.cache.get(url)
        if cached is not None:
            return cached
        if self.offline:
            raise HTTPError(url, None, "offline mode and no cached response")

        last_error: Optional[BaseException] = None
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": accept,
                    "Accept-Encoding": "gzip",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        payload = gzip.decompress(payload)
                self.cache.put(url, payload)
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                # 404 means the concept or company genuinely is not there;
                # retrying cannot change that.
                if exc.code in (400, 401, 403, 404):
                    raise HTTPError(url, exc.code, f"HTTP {exc.code} {exc.reason}") from exc
                self._backoff(attempt)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                self._backoff(attempt)

        raise HTTPError(url, None, f"failed after {self.max_retries + 1} attempts: {last_error}")

    def get_json(self, url: str) -> Any:
        payload = self.get(url)
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPError(url, None, f"response was not valid JSON: {exc}") from exc

    def get_text(self, url: str, accept: str = "text/plain") -> str:
        return self.get(url, accept=accept).decode("utf-8", errors="replace")

    def _backoff(self, attempt: int) -> None:
        if attempt >= self.max_retries:
            return
        # Exponential with jitter, so parallel workers that all trip a 503 do
        # not retry in lockstep.
        delay = min(16.0, 2.0 ** attempt) * (0.5 + random.random())
        time.sleep(delay)


def default_headers(user_agent: str) -> Dict[str, str]:
    return {"User-Agent": user_agent, "Accept": "application/json"}
