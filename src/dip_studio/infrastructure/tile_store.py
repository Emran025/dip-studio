"""Bounded ndarray-backed tile cache for large-image workloads."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np


class TileStore:
    """Store image tiles keyed by (x, y) coordinates.

    The tile store is intentionally small and bounded: it keeps track of the
    number of tiles and total in-memory bytes, and raises clear errors when the
    configured limits are exceeded.
    """

    def __init__(
        self,
        tile_size: int = 256,
        *,
        max_tiles: int | None = None,
        max_bytes: int | None = None,
    ) -> None:
        if tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if max_tiles is not None and max_tiles < 0:
            raise ValueError("max_tiles must be >= 0")
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes must be >= 0")

        self.tile_size = int(tile_size)
        self.max_tiles = max_tiles
        self.max_bytes = max_bytes
        self._tiles: dict[tuple[int, int], np.ndarray] = {}
        self._metadata: dict[tuple[int, int], dict[str, Any]] = {}
        self._bytes_used = 0

    @staticmethod
    def normalize_key(key: tuple[int, int] | str) -> tuple[int, int]:
        if isinstance(key, tuple):
            if len(key) != 2:
                raise ValueError("Tile key tuples must contain exactly (x, y)")
            x, y = key
        elif isinstance(key, str):
            text = key.strip().lower()
            if text.startswith("tile:"):
                text = text[5:]
            parts = text.replace("(", "").replace(")", "").split(",")
            if len(parts) == 1:
                parts = text.replace("/", ":").split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid tile key: {key!r}")
            x_text, y_text = parts
            x = int(x_text)
            y = int(y_text)
        else:
            raise TypeError("Tile key must be a tuple or string")

        if x < 0 or y < 0:
            raise ValueError(f"Tile coordinates must be non-negative: {(x, y)}")
        return (int(x), int(y))

    def tile_key(self, x: int, y: int) -> tuple[int, int]:
        return self.normalize_key((x, y))

    def __len__(self) -> int:
        return len(self._tiles)

    def __contains__(self, key: tuple[int, int] | str) -> bool:
        try:
            return self.normalize_key(key) in self._tiles
        except (TypeError, ValueError):
            return False

    def keys(self) -> Iterator[tuple[int, int]]:
        return iter(self._tiles)

    def total_bytes(self) -> int:
        return self._bytes_used

    def bytes_used(self) -> int:
        return self.total_bytes()

    def _tile_size_bytes(self, array: np.ndarray) -> int:
        if not isinstance(array, np.ndarray):
            raise TypeError("Tile values must be NumPy arrays")
        return int(array.nbytes)

    def put(self, key: tuple[int, int] | str, array: np.ndarray) -> tuple[int, int]:
        normalized = self.normalize_key(key)
        if not isinstance(array, np.ndarray):
            raise TypeError("Tile values must be NumPy arrays")

        if self.max_tiles is not None and len(self._tiles) >= self.max_tiles and normalized not in self._tiles:
            raise MemoryError(f"TileStore reached its configured tile limit ({self.max_tiles})")

        required = self._tile_size_bytes(array)
        if self.max_bytes is not None and self._bytes_used + required > self.max_bytes:
            raise MemoryError(
                f"Tile allocation exceeds configured memory limit: "
                f"{self._bytes_used + required} > {self.max_bytes} bytes"
            )

        tile = np.ascontiguousarray(array)
        existing = self._tiles.get(normalized)
        if existing is not None:
            self._bytes_used -= existing.nbytes
        self._tiles[normalized] = tile
        self._metadata[normalized] = {
            "shape": tuple(int(v) for v in tile.shape),
            "dtype": str(tile.dtype),
            "bytes": int(tile.nbytes),
            "tile_size": self.tile_size,
        }
        self._bytes_used += tile.nbytes
        return normalized

    def get(self, key: tuple[int, int] | str) -> np.ndarray:
        normalized = self.normalize_key(key)
        if normalized not in self._tiles:
            raise KeyError(f"Tile not found: {normalized}")
        return self._tiles[normalized]

    def get_tile(self, key: tuple[int, int] | str) -> np.ndarray:
        return self.get(key)

    def remove(self, key: tuple[int, int] | str) -> None:
        normalized = self.normalize_key(key)
        tile = self._tiles.pop(normalized, None)
        if tile is None:
            return
        self._bytes_used -= int(tile.nbytes)
        self._metadata.pop(normalized, None)

    def clear(self) -> None:
        self._tiles.clear()
        self._metadata.clear()
        self._bytes_used = 0

    def has(self, key: tuple[int, int] | str) -> bool:
        try:
            return self.normalize_key(key) in self._tiles
        except (TypeError, ValueError):
            return False

    def metadata(self, key: tuple[int, int] | str) -> dict[str, Any]:
        normalized = self.normalize_key(key)
        if normalized not in self._metadata:
            raise KeyError(f"Tile not found: {normalized}")
        return dict(self._metadata[normalized])

    def bounds_check(self, x: int, y: int, width: int, height: int) -> None:
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ValueError(f"Invalid tile bounds: x={x}, y={y}, width={width}, height={height}")
        if width > self.tile_size or height > self.tile_size:
            raise ValueError(
                f"Tile bounds exceed tile_size={self.tile_size}: "
                f"width={width}, height={height}"
            )

    def __repr__(self) -> str:
        return (
            f"TileStore(tile_size={self.tile_size}, tiles={len(self._tiles)}, "
            f"bytes_used={self._bytes_used})"
        )
