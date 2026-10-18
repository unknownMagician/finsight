"""Small thread-safe in-process TTL cache for provider responses.

Keeps repeated requests for the same end-of-day data from reaching free-tier providers. It is
per process: with several replicas each keeps its own copy (a shared cache such as Redis would
be needed to coordinate them).
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int = 2048,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._data: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_load(self, key: Hashable, loader: Callable[[], T]) -> tuple[T, bool]:
        """Return ``(value, cached)``. Loader exceptions propagate and are not cached."""
        now = self._clock()
        if self._ttl > 0:
            with self._lock:
                hit = self._data.get(key)
                if hit is not None and hit[0] > now:
                    self._data.move_to_end(key)
                    return hit[1], True
        value = loader()
        if self._ttl > 0:
            with self._lock:
                self._data[key] = (now + self._ttl, value)
                self._data.move_to_end(key)
                while len(self._data) > self._max:
                    self._data.popitem(last=False)
        return value, False

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
