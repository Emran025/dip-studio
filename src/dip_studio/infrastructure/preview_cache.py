"""Preview result cache with version-aware invalidation."""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewKey:
    """Stable key for a preview render based on source data and viewport."""

    buffer_id: str
    buffer_version: int
    width: int
    height: int
    zoom: float
    preview_mode: bool = False
    document_id: str | None = None

    @staticmethod
    def build(
        buffer_id: str,
        buffer_version: int,
        width: int,
        height: int,
        zoom: float,
        *,
        preview_mode: bool = False,
        document_id: str | None = None,
    ) -> "PreviewKey":
        params = {
            "buffer_id": buffer_id,
            "buffer_version": buffer_version,
            "width": int(width),
            "height": int(height),
            "zoom": float(zoom),
            "preview_mode": bool(preview_mode),
            "document_id": document_id,
        }
        digest = hashlib.sha256(
            json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return PreviewKey(
            buffer_id=buffer_id,
            buffer_version=buffer_version,
            width=int(width),
            height=int(height),
            zoom=float(zoom),
            preview_mode=bool(preview_mode),
            document_id=document_id,
        )

    def cache_token(self) -> str:
        return self.buffer_id + ":" + str(self.buffer_version)


class PreviewCache:
    """LRU cache for preview bytes keyed by viewport and source buffer version."""

    def __init__(self, max_entries: int | None = 32) -> None:
        self._max = max_entries if max_entries is None else max(1, max_entries)
        self._cache: OrderedDict[PreviewKey, bytes] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: PreviewKey) -> bytes | None:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

    def put(self, key: PreviewKey, value: bytes) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while self._max is not None and len(self._cache) > self._max:
                self._cache.popitem(last=False)

    def invalidate_buffer(self, buffer_id: str) -> None:
        with self._lock:
            stale = [key for key in self._cache if key.buffer_id == buffer_id]
            for key in stale:
                del self._cache[key]

    def invalidate_ids(self, buffer_ids: object) -> None:
        """Invalidate every cache entry that matches any buffer id in *buffer_ids*."""
        ids = {str(item) for item in buffer_ids}
        if not ids:
            return
        with self._lock:
            stale = [key for key in self._cache if key.buffer_id in ids]
            for key in stale:
                del self._cache[key]

    def invalidate_subtree(self, buffer_ids: object) -> None:
        """Compatibility alias for subtree-scoped cache invalidation."""
        self.invalidate_ids(buffer_ids)

    def invalidate_document(self, document_id: str | None) -> None:
        if document_id is None:
            return
        with self._lock:
            stale = [key for key in self._cache if key.document_id == document_id]
            for key in stale:
                del self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses
