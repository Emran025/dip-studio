"""Analysis and segmentation processors: Threshold, Segmentation."""

from __future__ import annotations

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param, _to_gray


def _otsu_threshold(gray: np.ndarray) -> int:
    """Compute optimal threshold using Otsu's method in pure NumPy."""
    hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 256))
    total = gray.size
    if total == 0:
        return 128

    current_max = 0.0
    threshold = 128
    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0.0

    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break

        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f

        # Inter-class variance
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > current_max:
            current_max = var_between
            threshold = i

    return threshold


class ThresholdProcessor(BaseProcessor):
    """Binarize image with global, Otsu, or adaptive thresholding."""

    operation = "threshold"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        gray = _to_gray(arr)
        method = _param(request, "method", "Binary").strip().title()
        thresh_val = float(_param(request, "threshold_value", "128"))
        inverse = _param(request, "inverse", "False").lower() in ("true", "1")

        if method == "Otsu":
            t = _otsu_threshold(gray)
        else:
            t = int(thresh_val)

        binary = (gray > t).astype(np.uint8) * 255
        if inverse:
            binary = 255 - binary

        if arr.ndim == 3:
            result = np.stack([binary, binary, binary], axis=-1)
            if arr.shape[2] == 4:
                result = np.concatenate([result, arr[:, :, 3:4]], axis=-1)
            return result
        return binary


class SegmentationProcessor(BaseProcessor):
    """Region segmentation via multi-level thresholding or color quantization."""

    operation = "segment"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        clusters = max(2, int(float(_param(request, "clusters", "3"))))
        gray = _to_gray(arr)

        # Quantize grayscale intensities into 'clusters' discrete levels
        step = 256 // clusters
        quantized = (gray // step) * step + (step // 2)
        quantized = np.clip(quantized, 0, 255).astype(np.uint8)

        if arr.ndim == 3:
            result = np.stack([quantized, quantized, quantized], axis=-1)
            if arr.shape[2] == 4:
                result = np.concatenate([result, arr[:, :, 3:4]], axis=-1)
            return result
        return quantized
