"""Undoable paint/draw commands: PaintStroke, EraserStroke, FloodFill.

All commands follow the Command Protocol (execute / undo) and live in the
application layer.  No Qt / PySide6 imports are allowed here.
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import Layer, LayerId

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore


# ---------------------------------------------------------------------------
# Brush stamp helpers
# ---------------------------------------------------------------------------

def _make_stamp(size: int, hardness: float) -> np.ndarray:
    """Create a (size × size) float32 circular brush stamp in [0, 1].

    *hardness* controls fall-off: 1.0 produces a crisp circle, 0.0 a very
    soft Gaussian dot.
    """
    size = max(1, size)
    radius = size / 2.0
    half = size / 2.0
    ax = np.arange(size, dtype=np.float32) - half + 0.5
    yy, xx = np.meshgrid(ax, ax, indexing="ij")
    dist = np.sqrt(yy ** 2 + xx ** 2)
    # Gaussian sigma scaled by (1 - hardness)
    sigma = radius * max(1e-3, 1.0 - hardness)
    stamp = np.exp(-0.5 * (dist / sigma) ** 2)
    # Hard edge: clip anything outside the radius to 0.
    stamp[dist > radius] = 0.0
    return stamp.astype(np.float32)


def _paint_stamp(
    arr: np.ndarray,
    cx: int,
    cy: int,
    stamp: np.ndarray,
    color: tuple[int, int, int, int],
    opacity: float,
) -> None:
    """Stamp *stamp* centred at (cx, cy) into *arr* (mutates in place).

    *arr* must be RGBA uint8 (H, W, 4).
    """
    h, w = arr.shape[:2]
    sh, sw = stamp.shape
    hs, ws = sh // 2, sw // 2
    # Source region (within stamp)
    sy0 = max(0, cy - hs)
    sy1 = min(h, cy + sh - hs)
    sx0 = max(0, cx - ws)
    sx1 = min(w, cx + sw - ws)
    if sy0 >= sy1 or sx0 >= sx1:
        return
    # Corresponding stamp region
    ty0 = sy0 - (cy - hs)
    ty1 = ty0 + (sy1 - sy0)
    tx0 = sx0 - (cx - ws)
    tx1 = tx0 + (sx1 - sx0)
    alpha_mask = stamp[ty0:ty1, tx0:tx1] * opacity  # (pH, pW) float32 in [0,1]
    region = arr[sy0:sy1, sx0:sx1].astype(np.float32)
    cr, cg, cb, ca = color
    # Normal blend: out = src_alpha * src_color + (1 - src_alpha) * dst_color
    for ch_idx, val in enumerate((cr, cg, cb)):
        region[:, :, ch_idx] = (
            alpha_mask * val + (1.0 - alpha_mask) * region[:, :, ch_idx]
        )
    # Combine alpha channels (max of existing and brush)
    region[:, :, 3] = np.maximum(region[:, :, 3], alpha_mask * ca)
    arr[sy0:sy1, sx0:sx1] = np.clip(region, 0, 255).astype(np.uint8)


def _erase_stamp(
    arr: np.ndarray,
    cx: int,
    cy: int,
    stamp: np.ndarray,
    opacity: float,
) -> None:
    """Reduce alpha in *arr* at the stamp position (mutates in place)."""
    h, w = arr.shape[:2]
    sh, sw = stamp.shape
    hs, ws = sh // 2, sw // 2
    sy0 = max(0, cy - hs)
    sy1 = min(h, cy + sh - hs)
    sx0 = max(0, cx - ws)
    sx1 = min(w, cx + sw - ws)
    if sy0 >= sy1 or sx0 >= sx1:
        return
    ty0 = sy0 - (cy - hs)
    ty1 = ty0 + (sy1 - sy0)
    tx0 = sx0 - (cx - ws)
    tx1 = tx0 + (sx1 - sx0)
    alpha_mask = stamp[ty0:ty1, tx0:tx1] * opacity
    arr[sy0:sy1, sx0:sx1, 3] = np.clip(
        arr[sy0:sy1, sx0:sx1, 3].astype(np.float32) * (1.0 - alpha_mask),
        0, 255,
    ).astype(np.uint8)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

class PaintStroke:
    """Paint a brush stroke into the active layer buffer.

    Parameters
    ----------
    data_store : ImageDataStore
    layer_id   : LayerId  target layer
    points     : list of (x, y) image-space coordinates
    color      : RGBA tuple 0-255
    size       : brush diameter in pixels (default 10)
    hardness   : edge sharpness 0.0-1.0 (default 0.8)
    opacity    : stroke opacity 0.0-1.0 (default 1.0)
    """

    label = "Paint stroke"

    def __init__(
        self,
        data_store: "ImageDataStore",
        layer_id: LayerId,
        points: list[tuple[int, int]],
        color: tuple[int, int, int, int],
        size: int = 10,
        hardness: float = 0.8,
        opacity: float = 1.0,
    ) -> None:
        self._store = data_store
        self._layer_id = layer_id
        self._points = points
        self._color = color
        self._size = size
        self._hardness = hardness
        self._opacity = opacity
        self._snapshot_buffer_id: str | None = None
        self._original_buffer_id: str | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        layer = next((la for la in document.layers if la.id == self._layer_id), None)
        if layer is None or layer.buffer_id is None:
            return

        self._original_buffer_id = layer.buffer_id
        # Clone the buffer for undo snapshoting.
        original = self._store.get(layer.buffer_id)
        snapshot = original.copy()

        # Work on a mutable copy.
        arr = original.copy()
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
        elif arr.shape[2] == 3:
            arr = np.concatenate([arr, np.full((*arr.shape[:2], 1), 255, dtype=arr.dtype)], axis=-1)

        stamp = _make_stamp(self._size, self._hardness)
        for x, y in self._points:
            _paint_stamp(arr, x, y, stamp, self._color, self._opacity)

        new_buf_id = self._store.allocate(arr)
        self._snapshot_buffer_id = self._store.allocate(snapshot)

        new_layer = layer.changed(buffer_id=new_buf_id)
        new_layers = tuple(new_layer if la.id == layer.id else la for la in document.layers)
        session.replace(document.changed(layers=new_layers))

    def undo(self, session: DocumentSession) -> None:
        if self._snapshot_buffer_id is None:
            return
        document = session.document
        layer = next((la for la in document.layers if la.id == self._layer_id), None)
        if layer is None:
            return
        # Release the painted buffer, restore the snapshot.
        if layer.buffer_id is not None and layer.buffer_id != self._snapshot_buffer_id:
            try:
                self._store.release(layer.buffer_id)
            except Exception:
                pass
        new_layer = layer.changed(buffer_id=self._snapshot_buffer_id)
        new_layers = tuple(new_layer if la.id == layer.id else la for la in document.layers)
        session.replace(document.changed(layers=new_layers))
        self._snapshot_buffer_id = None


class EraserStroke:
    """Erase pixels from the active layer (reduce alpha channel).

    Parameters match ``PaintStroke`` minus *color*.
    """

    label = "Eraser stroke"

    def __init__(
        self,
        data_store: "ImageDataStore",
        layer_id: LayerId,
        points: list[tuple[int, int]],
        size: int = 20,
        hardness: float = 0.8,
        opacity: float = 1.0,
    ) -> None:
        self._store = data_store
        self._layer_id = layer_id
        self._points = points
        self._size = size
        self._hardness = hardness
        self._opacity = opacity
        self._snapshot_buffer_id: str | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        layer = next((la for la in document.layers if la.id == self._layer_id), None)
        if layer is None or layer.buffer_id is None:
            return

        original = self._store.get(layer.buffer_id)
        snapshot = original.copy()
        arr = original.copy()

        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
        elif arr.shape[2] == 3:
            arr = np.concatenate([arr, np.full((*arr.shape[:2], 1), 255, dtype=arr.dtype)], axis=-1)

        stamp = _make_stamp(self._size, self._hardness)
        for x, y in self._points:
            _erase_stamp(arr, x, y, stamp, self._opacity)

        new_buf_id = self._store.allocate(arr)
        self._snapshot_buffer_id = self._store.allocate(snapshot)

        new_layer = layer.changed(buffer_id=new_buf_id)
        new_layers = tuple(new_layer if la.id == layer.id else la for la in document.layers)
        session.replace(document.changed(layers=new_layers))

    def undo(self, session: DocumentSession) -> None:
        if self._snapshot_buffer_id is None:
            return
        document = session.document
        layer = next((la for la in document.layers if la.id == self._layer_id), None)
        if layer is None:
            return
        if layer.buffer_id is not None and layer.buffer_id != self._snapshot_buffer_id:
            try:
                self._store.release(layer.buffer_id)
            except Exception:
                pass
        new_layer = layer.changed(buffer_id=self._snapshot_buffer_id)
        new_layers = tuple(new_layer if la.id == layer.id else la for la in document.layers)
        session.replace(document.changed(layers=new_layers))
        self._snapshot_buffer_id = None


class FloodFill:
    """BFS flood-fill at a seed pixel with given colour and tolerance.

    Parameters
    ----------
    data_store : ImageDataStore
    layer_id   : LayerId
    x, y       : seed pixel in image coordinates
    color      : RGBA fill colour 0-255
    tolerance  : maximum per-channel difference from seed (default 15)
    """

    label = "Flood fill"

    def __init__(
        self,
        data_store: "ImageDataStore",
        layer_id: LayerId,
        x: int,
        y: int,
        color: tuple[int, int, int, int],
        tolerance: int = 15,
    ) -> None:
        self._store = data_store
        self._layer_id = layer_id
        self._x = x
        self._y = y
        self._color = color
        self._tolerance = tolerance
        self._snapshot_buffer_id: str | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        layer = next((la for la in document.layers if la.id == self._layer_id), None)
        if layer is None or layer.buffer_id is None:
            return

        original = self._store.get(layer.buffer_id)
        snapshot = original.copy()
        arr = original.copy()

        # Ensure RGBA for consistent channel access.
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
        elif arr.shape[2] == 3:
            arr = np.concatenate([arr, np.full((*arr.shape[:2], 1), 255, dtype=arr.dtype)], axis=-1)

        h, w = arr.shape[:2]
        x0 = max(0, min(self._x, w - 1))
        y0 = max(0, min(self._y, h - 1))
        seed_color = arr[y0, x0].astype(np.int32)
        tol = self._tolerance
        fill = np.array(self._color, dtype=np.uint8)

        # BFS flood fill.
        visited = np.zeros((h, w), dtype=bool)
        q: deque[tuple[int, int]] = deque([(y0, x0)])
        visited[y0, x0] = True

        while q:
            y, x = q.popleft()
            arr[y, x] = fill
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    pixel = arr[ny, nx].astype(np.int32)
                    if np.max(np.abs(pixel - seed_color)) <= tol:
                        visited[ny, nx] = True
                        q.append((ny, nx))

        new_buf_id = self._store.allocate(arr)
        self._snapshot_buffer_id = self._store.allocate(snapshot)

        new_layer = layer.changed(buffer_id=new_buf_id)
        new_layers = tuple(new_layer if la.id == layer.id else la for la in document.layers)
        session.replace(document.changed(layers=new_layers))

    def undo(self, session: DocumentSession) -> None:
        if self._snapshot_buffer_id is None:
            return
        document = session.document
        layer = next((la for la in document.layers if la.id == self._layer_id), None)
        if layer is None:
            return
        if layer.buffer_id is not None and layer.buffer_id != self._snapshot_buffer_id:
            try:
                self._store.release(layer.buffer_id)
            except Exception:
                pass
        new_layer = layer.changed(buffer_id=self._snapshot_buffer_id)
        new_layers = tuple(new_layer if la.id == layer.id else la for la in document.layers)
        session.replace(document.changed(layers=new_layers))
        self._snapshot_buffer_id = None
