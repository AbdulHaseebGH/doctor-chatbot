# --------------------------------------------------------------------------
# conversation/app/cache.py
#
# Simple LRU cache with TTL for conversation service responses.
# Used to cache identical queries within a short window.
# --------------------------------------------------------------------------

import time
from collections import OrderedDict


class LRUCache:
    """
    Thread-safe LRU cache with per-entry TTL.
    - max_size: maximum number of entries
    - ttl_seconds: entries expire after this many seconds
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, tuple[any, float]] = OrderedDict()

    def get(self, key: str):
        """Return cached value or None if missing/expired."""
        if key not in self._cache:
            return None
        value, ts = self._cache[key]
        if time.time() - ts > self.ttl:
            del self._cache[key]
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value) -> None:
        """Store a value with current timestamp."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.time())
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)  # evict oldest

    def invalidate(self, key: str) -> None:
        """Remove a specific key."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# Global response cache — shared across all requests
response_cache = LRUCache(max_size=100, ttl_seconds=300)
