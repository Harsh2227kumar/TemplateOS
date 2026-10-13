"""
Small, swappable rate limiting.

`RateLimiter` is the interface the endpoints depend on; `InMemoryRateLimiter`
is a sliding-window implementation kept in process memory. It is per process:
with several workers/replicas each one counts separately, and counts reset on
restart. A Redis-backed class implementing the same `hit`/`reset` methods can
replace it without touching the endpoints.
"""

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

from app.core.config import settings


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0  # whole seconds until a slot frees up (when blocked)


class RateLimiter(Protocol):
    def hit(self, key: str) -> RateLimitResult: ...

    def reset(self, key: str | None = None) -> None: ...


class InMemoryRateLimiter:
    """Allow at most `limit` hits per `window_seconds` for each key."""

    # Sweep idle keys once the table grows past this, bounding memory.
    _SWEEP_THRESHOLD = 10_000

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, hits: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        for key in list(self._hits):
            hits = self._hits[key]
            self._prune(hits, now)
            if not hits:
                del self._hits[key]

    def hit(self, key: str) -> RateLimitResult:
        with self._lock:
            now = self._clock()
            if len(self._hits) > self._SWEEP_THRESHOLD:
                self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            self._prune(hits, now)
            if len(hits) >= self.limit:
                retry_after = hits[0] + self.window_seconds - now
                return RateLimitResult(False, max(1, math.ceil(retry_after)))
            hits.append(now)
            return RateLimitResult(True)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


class LoginRateLimiter:
    """
    Throttles POST /auth/login per client IP and per (lower-cased) email.
    Every attempt counts, successful or not. Both keys are recorded on each
    attempt; the request is blocked if either is over the limit.
    """

    def __init__(self, backend: RateLimiter, enabled: bool = True) -> None:
        self.backend = backend
        self.enabled = enabled

    def check(self, client_ip: str | None, email: str) -> RateLimitResult:
        if not self.enabled:
            return RateLimitResult(True)
        results = [
            self.backend.hit(f"login:ip:{client_ip or 'unknown'}"),
            self.backend.hit(f"login:email:{email.strip().lower()}"),
        ]
        blocked = [result for result in results if not result.allowed]
        if blocked:
            return RateLimitResult(False, max(r.retry_after for r in blocked))
        return RateLimitResult(True)

    def reset(self) -> None:
        self.backend.reset()


login_rate_limiter = LoginRateLimiter(
    InMemoryRateLimiter(
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    ),
    enabled=settings.login_rate_limit_enabled,
)
