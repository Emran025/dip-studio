"""Morphological operation processors: Erode, Dilate, Open, Close.

Uses OpenCV for GPU-accelerated implementations; pure-NumPy sliding-window
fallbacks require only NumPy (no scipy dependency).
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


def _get_kernel(request: ProcessingRequest) -> np.ndarray:
    ksize = max(1, int(float(_param(request, "kernel_size", "3"))))
    shape_name = _param(request, "kernel_shape", "rect")
    if _CV2_AVAILABLE:
        shapes = {
            "rect": cv2.MORPH_RECT,
            "ellipse": cv2.MORPH_ELLIPSE,
            "cross": cv2.MORPH_CROSS,
        }
        shape_code = shapes.get(shape_name, cv2.MORPH_RECT)
        return cv2.getStructuringElement(shape_code, (ksize, ksize))
    return np.ones((ksize, ksize), dtype=np.uint8)


def _numpy_erode(arr: np.ndarray, ksize: int) -> np.ndarray:
    """Pure-NumPy morphological erosion (sliding minimum over rectangular SE)."""
    pad = ksize // 2
    if arr.ndim == 3:
        result = np.empty_like(arr)
        for c in range(arr.shape[2]):
            ch = arr[:, :, c]
            padded = np.pad(ch, pad, mode="edge")
            for i in range(arr.shape[0]):
                for j in range(arr.shape[1]):
                    result[i, j, c] = padded[i:i + ksize, j:j + ksize].min()
        return result
    padded = np.pad(arr, pad, mode="edge")
    result = np.empty_like(arr)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            result[i, j] = padded[i:i + ksize, j:j + ksize].min()
    return result


def _numpy_dilate(arr: np.ndarray, ksize: int) -> np.ndarray:
    """Pure-NumPy morphological dilation (sliding maximum over rectangular SE)."""
    pad = ksize // 2
    if arr.ndim == 3:
        result = np.empty_like(arr)
        for c in range(arr.shape[2]):
            ch = arr[:, :, c]
            padded = np.pad(ch, pad, mode="edge")
            for i in range(arr.shape[0]):
                for j in range(arr.shape[1]):
                    result[i, j, c] = padded[i:i + ksize, j:j + ksize].max()
        return result
    padded = np.pad(arr, pad, mode="edge")
    result = np.empty_like(arr)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            result[i, j] = padded[i:i + ksize, j:j + ksize].max()
    return result


class ErodeProcessor(BaseProcessor):
    """Morphological erosion."""

    operation = "erode"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ksize = max(1, int(float(_param(request, "kernel_size", "3"))))
        if _CV2_AVAILABLE:
            kernel = _get_kernel(request)
            return cv2.erode(arr, kernel)
        return _numpy_erode(arr, ksize)


class DilateProcessor(BaseProcessor):
    """Morphological dilation."""

    operation = "dilate"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ksize = max(1, int(float(_param(request, "kernel_size", "3"))))
        if _CV2_AVAILABLE:
            kernel = _get_kernel(request)
            return cv2.dilate(arr, kernel)
        return _numpy_dilate(arr, ksize)


class MorphOpenProcessor(BaseProcessor):
    """Morphological opening: erode then dilate (removes small bright noise)."""

    operation = "morph_open"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ksize = max(1, int(float(_param(request, "kernel_size", "3"))))
        if _CV2_AVAILABLE:
            kernel = _get_kernel(request)
            return cv2.morphologyEx(arr, cv2.MORPH_OPEN, kernel)
        eroded = _numpy_erode(arr, ksize)
        return _numpy_dilate(eroded, ksize)


class MorphCloseProcessor(BaseProcessor):
    """Morphological closing: dilate then erode (fills small dark holes)."""

    operation = "morph_close"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ksize = max(1, int(float(_param(request, "kernel_size", "3"))))
        if _CV2_AVAILABLE:
            kernel = _get_kernel(request)
            return cv2.morphologyEx(arr, cv2.MORPH_CLOSE, kernel)
        dilated = _numpy_dilate(arr, ksize)
        return _numpy_erode(dilated, ksize)
