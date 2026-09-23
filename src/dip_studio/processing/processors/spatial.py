"""Spatial filtering processors: Gaussian, Median, Bilateral.

Uses OpenCV for optimized implementations; pure-NumPy educational
fallbacks require no extra dependencies beyond NumPy.
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


def _ensure_odd(k: int) -> int:
    return k if k % 2 == 1 else k + 1


def _numpy_gaussian_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Pure-NumPy Gaussian blur using a 1-D separable kernel (no scipy)."""
    # Build 1-D Gaussian kernel
    radius = max(1, int(3 * sigma))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel_1d = np.exp(-0.5 * (x / sigma) ** 2)
    kernel_1d /= kernel_1d.sum()

    def _convolve1d(data: np.ndarray, k: np.ndarray, axis: int) -> np.ndarray:
        """Separable 1-D convolution along one axis with edge padding."""
        pad = len(k) // 2
        pad_widths = [(0, 0)] * data.ndim
        pad_widths[axis] = (pad, pad)
        padded = np.pad(data, pad_widths, mode="edge")
        out = np.zeros_like(data, dtype=np.float32)
        for i, w in enumerate(k):
            slices = [slice(None)] * data.ndim
            slices[axis] = slice(i, i + data.shape[axis])
            out += w * padded[tuple(slices)].astype(np.float32)
        return out

    result = arr.astype(np.float32)
    result = _convolve1d(result, kernel_1d, axis=0)
    result = _convolve1d(result, kernel_1d, axis=1)
    return result.clip(0, 255).astype(np.uint8)


def _numpy_median_blur(arr: np.ndarray, ksize: int) -> np.ndarray:
    """Pure-NumPy median filter using sliding-window approach."""
    pad = ksize // 2
    if arr.ndim == 3:
        result = np.empty_like(arr)
        for c in range(arr.shape[2]):
            ch = arr[:, :, c]
            padded = np.pad(ch, pad, mode="edge")
            for i in range(arr.shape[0]):
                for j in range(arr.shape[1]):
                    result[i, j, c] = np.median(padded[i : i + ksize, j : j + ksize])
        return result
    padded = np.pad(arr, pad, mode="edge")
    result = np.empty_like(arr)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            result[i, j] = np.median(padded[i : i + ksize, j : j + ksize])
    return result


class GaussianBlurProcessor(BaseProcessor):
    """Gaussian blur: smooth image with Gaussian kernel."""

    operation = "gaussian_blur"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ksize = _ensure_odd(max(1, int(float(_param(request, "kernel_size", "5")))))
        sigma = float(_param(request, "sigma", "1.0"))
        if _CV2_AVAILABLE:
            return cv2.GaussianBlur(arr, (ksize, ksize), sigma)
        # Pure-NumPy educational fallback (no scipy required)
        return _numpy_gaussian_blur(arr, sigma)


class MedianBlurProcessor(BaseProcessor):
    """Median blur: removes salt-and-pepper noise."""

    operation = "median_blur"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ksize = _ensure_odd(max(1, int(float(_param(request, "kernel_size", "5")))))
        if _CV2_AVAILABLE:
            return cv2.medianBlur(arr, ksize)
        # Pure-NumPy fallback (slower but zero-dependency)
        return _numpy_median_blur(arr, ksize)


class BilateralFilterProcessor(BaseProcessor):
    """Bilateral filter: edge-preserving smooth."""

    operation = "bilateral_filter"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        d = int(float(_param(request, "diameter", "9")))
        sigma_color = float(_param(request, "sigma_color", "75.0"))
        sigma_space = float(_param(request, "sigma_space", "75.0"))
        if _CV2_AVAILABLE:
            rgb = arr[:, :, :3] if arr.ndim == 3 and arr.shape[2] >= 3 else arr
            blurred = cv2.bilateralFilter(rgb, d, sigma_color, sigma_space)
            if arr.ndim == 3 and arr.shape[2] == 4:
                result = arr.copy()
                result[:, :, :3] = blurred
                return result
            return blurred
        # NumPy fallback: approximate via Gaussian blur
        sigma = sigma_space / 10.0
        return _numpy_gaussian_blur(arr, max(0.5, sigma))
