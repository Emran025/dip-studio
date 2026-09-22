"""LRU ProcessingCache — avoids re-executing identical processor runs.

Cache key is built from:
    (source_buffer_id, buffer_version, operation, sha256_of_sorted_params)

Entries are evicted LRU-style when the cache exceeds ``max_entries``.
The cache is thread-safe; all public methods acquire the same lock.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheKey:
    """Immutable key identifying a unique processor run."""

    buffer_id: str
    buffer_version: int     # from ImageDataStore.version(buffer_id)
    operation: str
    operation_version: str
    params_hash: str        # sha256 hex of canonicalised parameters
    mask_id: str | None = None
    mask_version: int | None = None
    selection_id: str | None = None
    selection_version: int | None = None
    preview_mode: bool = False

    @staticmethod
    def build(
        buffer_id: str,
        buffer_version: int,
        operation: str,
        parameters: tuple[tuple[str, str], ...],
        *,
        operation_version: str = "1",
        mask_id: str | None = None,
        mask_version: int | None = None,
        selection_id: str | None = None,
        selection_version: int | None = None,
        preview_mode: bool = False,
    ) -> "CacheKey":
        """Construct a CacheKey from raw request parameters."""
        canonical = json.dumps(
            sorted((str(name), str(value)) for name, value in parameters),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        params_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return CacheKey(
            buffer_id,
            buffer_version,
            operation,
            operation_version,
            params_hash,
            mask_id,
            mask_version,
            selection_id,
            selection_version,
            preview_mode,
        )


class ProcessingCache:
    """Bounded LRU cache mapping ``CacheKey → result_buffer_id``.

    Parameters
    ----------
    max_entries : int
        Maximum number of cached results (default 32).  When the cache is
        full, the least-recently-used entry is evicted first.
    """

    def __init__(self, max_entries: int | None = 32) -> None:
        self._max = max_entries if max_entries is None else max(1, max_entries)
        # OrderedDict used as an ordered LRU container:
        # most-recently-used entries are moved to the end.
        self._cache: OrderedDict[CacheKey, str] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: CacheKey) -> str | None:
        """Return the cached result ``buffer_id`` or ``None`` on cache miss.

        Accessing an entry promotes it to most-recently-used.
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            # Move to end (most recently used).
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

    def put(self, key: CacheKey, result_buffer_id: str) -> None:
        """Store *result_buffer_id* under *key*, evicting LRU entries if needed."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = result_buffer_id
                return
            self._cache[key] = result_buffer_id
            while self._max is not None and len(self._cache) > self._max:
                self._cache.popitem(last=False)  # remove oldest (front)

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    def statistics(self) -> tuple[int, int]:
        with self._lock:
            return self._hits, self._misses

    def invalidate_buffer(self, buffer_id: str) -> None:
        """Remove all entries whose *source* buffer_id matches *buffer_id*.

        Call this whenever a buffer is mutated (allocated or released) so
        stale results are not served.
        """
        with self._lock:
            stale = [
                key
                for key in self._cache
                if key.buffer_id == buffer_id
                or key.mask_id == buffer_id
                or key.selection_id == buffer_id
            ]
            for k in stale:
                del self._cache[k]

    def clear(self) -> None:
        """Evict all cached entries."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)
