"""Histogram-based processors: equalization, CLAHE.

Histogram equalization is implemented educationally in NumPy.
CLAHE uses OpenCV when available.
"""

from __future__ import annotations

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param

_CV2_AVAILABLE = False
try:
    import cv2  # type: ignore[import-untyped]

    _CV2_AVAILABLE = True
except ImportError:
    pass


def _equalize_channel(channel: np.ndarray) -> np.ndarray:
    """NumPy educational histogram equalization for a single uint8 channel."""
    hist, _ = np.histogram(channel.flatten(), bins=256, range=(0, 256))
    cdf = hist.cumsum()
    nonzero = cdf[cdf > 0]
    if len(nonzero) == 0:
        return channel  # already flat
    cdf_min = int(nonzero.min())
    n = channel.size
    denominator = n - cdf_min
    if denominator == 0:
        return channel  # uniform image — no equalization possible
    lut = np.round((cdf - cdf_min) / denominator * 255).clip(0, 255).astype(np.uint8)
    return lut[channel]


class HistogramEqualizationProcessor(BaseProcessor):
    """NumPy educational global histogram equalization."""

    operation = "histogram_equalization"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        if arr.ndim == 2:
            return _equalize_channel(arr)
        channels = arr.shape[2]
        result = arr.copy()
        for c in range(min(channels, 3)):
            result[:, :, c] = _equalize_channel(arr[:, :, c])
        return result


class CLAHEProcessor(BaseProcessor):
    """Contrast Limited Adaptive Histogram Equalization via OpenCV."""

    operation = "clahe"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        clip_limit = float(_param(request, "clip_limit", "2.0"))
        tile_size = int(_param(request, "tile_size", "8"))
        if _CV2_AVAILABLE:
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
            if arr.ndim == 2:
                return clahe.apply(arr)
            # Apply per channel
            result = arr.copy()
            for c in range(min(arr.shape[2], 3)):
                result[:, :, c] = clahe.apply(arr[:, :, c])
            return result
        # Fallback: basic equalization
        return HistogramEqualizationProcessor(self._store)._apply(arr, request)
