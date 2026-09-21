"""In-process image buffer store with Copy-on-Write semantics.

The DataStore owns the raw NumPy pixel data; Layer objects only carry
a buffer_id reference, keeping the domain layer free of NumPy.
"""
from __future__ import annotations

import threading
from uuid import uuid4

import numpy as np


class ImageDataStore:
    """Thread-safe registry of id → ndarray with Copy-on-Write support."""

    def __init__(self) -> None:
        self._buffers: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Allocation                                                           #
    # ------------------------------------------------------------------ #

    def allocate(self, array: np.ndarray) -> str:
        """Store *array* (by reference) and return its unique buffer_id."""
        buffer_id = str(uuid4())
        with self._lock:
            self._buffers[buffer_id] = array
        return buffer_id

    def allocate_mask(self, array: np.ndarray) -> str:
        """Store a float32 mask array (values 0.0–1.0) and return its buffer_id."""
        if array.dtype != np.float32:
            array = array.astype(np.float32)
        array = np.clip(array, 0.0, 1.0)
        return self.allocate(array)

    def get(self, buffer_id: str) -> np.ndarray:
        """Return the buffer for *buffer_id*; raises KeyError if unknown."""
        with self._lock:
            try:
                return self._buffers[buffer_id]
            except KeyError:
                raise KeyError(f"Buffer not found: {buffer_id}") from None

    def release(self, buffer_id: str) -> None:
        """Remove *buffer_id* from the store, freeing the array reference."""
        with self._lock:
            self._buffers.pop(buffer_id, None)

    def copy_on_write(self, buffer_id: str) -> str:
        """Return a new buffer_id holding a fresh copy of *buffer_id*'s data."""
        array = self.get(buffer_id)
        return self.allocate(array.copy())

    def has(self, buffer_id: str) -> bool:
        with self._lock:
            return buffer_id in self._buffers

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffers)

    def merge_buffers(
        self,
        lower_buffer_id: str,
        upper_buffer_id: str,
        upper_opacity: float = 1.0,
        upper_blend_mode: str = "normal",
    ) -> str:
        """Composite two layer buffers into a single buffer."""
        from dip_studio.rendering.compositor import _alpha_composite, _resize_array, _to_rgba

        upper_arr = _to_rgba(self.get(upper_buffer_id)).copy()
        lower_arr = _to_rgba(self.get(lower_buffer_id))
        if upper_arr.shape[:2] != lower_arr.shape[:2]:
            upper_arr = _resize_array(upper_arr, lower_arr.shape[1], lower_arr.shape[0])
        if upper_opacity < 1.0:
            upper_arr[:, :, 3] = (
                upper_arr[:, :, 3].astype(np.float32) * upper_opacity
            ).astype(np.uint8)
        merged_arr = (
            _alpha_composite(lower_arr, upper_arr, blend_mode=upper_blend_mode)
            .clip(0, 255)
            .astype(np.uint8)
        )
        return self.allocate(merged_arr)

    def extract_selection(
        self,
        buffer_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        doc_w: int,
        doc_h: int,
        cut: bool = False,
    ) -> tuple[str, str | None]:
        """Extract rectangular region from buffer.

        Returns (new_selection_buffer_id, updated_source_buffer_id_if_cut).
        """
        from dip_studio.rendering.compositor import _to_rgba

        if self.has(buffer_id):
            src_arr = _to_rgba(self.get(buffer_id))
            sh, sw = src_arr.shape[:2]
        else:
            sh, sw = max(1, doc_h), max(1, doc_w)
            src_arr = np.zeros((sh, sw, 4), dtype=np.uint8)

        x1 = max(0, min(x, doc_w - 1))
        y1 = max(0, min(y, doc_h - 1))
        x2 = max(x1 + 1, min(x + width, doc_w))
        y2 = max(y1 + 1, min(y + height, doc_h))

        scale_x = sw / max(1, doc_w)
        scale_y = sh / max(1, doc_h)
        sx1 = int(round(x1 * scale_x))
        sy1 = int(round(y1 * scale_y))
        sx2 = max(sx1 + 1, min(sw, int(round(x2 * scale_x))))
        sy2 = max(sy1 + 1, min(sh, int(round(y2 * scale_y))))

        new_arr = np.zeros((sh, sw, 4), dtype=np.uint8)
        new_arr[sy1:sy2, sx1:sx2] = src_arr[sy1:sy2, sx1:sx2].copy()
        new_buf_id = self.allocate(new_arr)

        cut_buf_id = None
        if cut:
            cut_arr = src_arr.copy()
            cut_arr[sy1:sy2, sx1:sx2] = 0
            cut_buf_id = self.allocate(cut_arr)

        return new_buf_id, cut_buf_id

    def crop_buffer(
        self,
        buffer_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        doc_w: int,
        doc_h: int,
    ) -> str:
        """Crop a buffer to relative region."""
        if self.has(buffer_id):
            arr = self.get(buffer_id)
        else:
            arr = np.zeros((max(1, doc_h), max(1, doc_w), 4), dtype=np.uint8)
        h_arr, w_arr = arr.shape[:2]
        x1 = max(0, min(x, doc_w - 1))
        y1 = max(0, min(y, doc_h - 1))
        x2 = max(x1 + 1, min(x + width, doc_w))
        y2 = max(y1 + 1, min(y + height, doc_h))

        scale_x = w_arr / max(1, doc_w)
        scale_y = h_arr / max(1, doc_h)
        lx1 = int(round(x1 * scale_x))
        ly1 = int(round(y1 * scale_y))
        lx2 = max(lx1 + 1, int(round(x2 * scale_x)))
        ly2 = max(ly1 + 1, int(round(y2 * scale_y)))
        cropped = np.ascontiguousarray(arr[ly1:ly2, lx1:lx2])
        return self.allocate(cropped)

    def resize_buffer_to_rect(
        self,
        buffer_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        doc_w: int,
        doc_h: int,
    ) -> str:
        """Fit a layer's non-transparent content into a document-space rect."""
        from dip_studio.rendering.compositor import _to_rgba

        source = _to_rgba(self.get(buffer_id))
        alpha = source[:, :, 3]
        ys, xs = np.nonzero(alpha)
        if len(xs) == 0:
            return self.allocate(np.zeros((doc_h, doc_w, 4), dtype=np.uint8))

        left, right = int(xs.min()), int(xs.max()) + 1
        top, bottom = int(ys.min()), int(ys.max()) + 1
        content = source[top:bottom, left:right]
        target_w = max(1, min(width, doc_w))
        target_h = max(1, min(height, doc_h))

        from PIL import Image as PilImage

        resized = np.array(
            PilImage.fromarray(content, "RGBA").resize(
                (target_w, target_h), PilImage.Resampling.LANCZOS
            ),
            dtype=np.uint8,
        )
        result = np.zeros((doc_h, doc_w, 4), dtype=np.uint8)
        x1 = max(0, min(x, doc_w - 1))
        y1 = max(0, min(y, doc_h - 1))
        x2 = min(doc_w, x1 + target_w)
        y2 = min(doc_h, y1 + target_h)
        result[y1:y2, x1:x2] = resized[: y2 - y1, : x2 - x1]
        return self.allocate(result)
