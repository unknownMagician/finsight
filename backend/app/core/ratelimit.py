"""In-process sliding-window rate limiter.

Scope: one limiter per API process. With several replicas each enforces its own window, so
the effective limit is ``limit x replicas``; move to a shared store (e.g. Redis) before
scaling out. Documented in SYSTEM_FLOW.md section 13.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

Clock = Callable[[], float]


class RateLimiter:
    def __init__(self, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Record a request. Returns None if allowed, else seconds until a slot frees up."""
        now = self._clock()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] <= now - window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return max(bucket[0] + window_seconds - now, 0.0)
            bucket.append(now)
            if len(self._hits) > 50_000:  # bound memory: drop idle keys
                for stale in [k for k, v in self._hits.items() if not v]:
                    del self._hits[stale]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def retry_after_header(seconds: float) -> str:
    return str(max(1, math.ceil(seconds)))
