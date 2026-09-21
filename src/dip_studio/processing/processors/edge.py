"""Edge detection processors: Sobel, Canny, Laplacian."""
from __future__ import annotations

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param, _to_gray

_CV2_AVAILABLE = False
try:
    import cv2  # type: ignore[import-untyped]
    _CV2_AVAILABLE = True
except ImportError:
    pass


class SobelProcessor(BaseProcessor):
    """Sobel edge magnitude map. Educational NumPy implementation available."""
    operation = "sobel"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        gray = _to_gray(arr)
        if _CV2_AVAILABLE:
            sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        else:
            # NumPy educational Sobel
            kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64)
            ky = kx.T
            from numpy import pad
            p = pad(gray.astype(np.float64), 1, mode='edge')
            sx = sum(
                kx[i, j] * p[i:i+gray.shape[0], j:j+gray.shape[1]]
                for i in range(3) for j in range(3)
            )
            sy = sum(
                ky[i, j] * p[i:i+gray.shape[0], j:j+gray.shape[1]]
                for i in range(3) for j in range(3)
            )
        magnitude = np.sqrt(sx**2 + sy**2)
        magnitude = (magnitude / magnitude.max() * 255).clip(0, 255).astype(np.uint8) if magnitude.max() > 0 else magnitude.astype(np.uint8)
        return np.stack([magnitude, magnitude, magnitude], axis=-1) if arr.ndim == 3 else magnitude


class CannyProcessor(BaseProcessor):
    """Canny edge detector (requires OpenCV)."""
    operation = "canny"

    def validate(self, request: ProcessingRequest) -> None:
        t1 = float(_param(request, "threshold1", "50"))
        t2 = float(_param(request, "threshold2", "150"))
        if t1 < 0 or t2 < 0:
            raise ValueError("Canny thresholds must be non-negative")

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        t1 = float(_param(request, "threshold1", "50"))
        t2 = float(_param(request, "threshold2", "150"))
        gray = _to_gray(arr)
        if _CV2_AVAILABLE:
            edges = cv2.Canny(gray, t1, t2)
        else:
            # Simple threshold fallback
            edges = (gray > int(t1)).astype(np.uint8) * 255
        return np.stack([edges, edges, edges], axis=-1) if arr.ndim == 3 else edges


class LaplacianProcessor(BaseProcessor):
    """Laplacian sharpening/edge detection."""
    operation = "laplacian"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        gray = _to_gray(arr)
        if _CV2_AVAILABLE:
            lap = cv2.Laplacian(gray, cv2.CV_64F)
            lap = np.abs(lap)
        else:
            kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
            from numpy import pad
            p = pad(gray.astype(np.float64), 1, mode='edge')
            lap = np.zeros_like(gray, dtype=np.float64)
            for i in range(3):
                for j in range(3):
                    lap += kernel[i, j] * p[i:i+gray.shape[0], j:j+gray.shape[1]]
            lap = np.abs(lap)
        normalized = (lap / lap.max() * 255).clip(0, 255).astype(np.uint8) if lap.max() > 0 else lap.astype(np.uint8)
        return np.stack([normalized, normalized, normalized], axis=-1) if arr.ndim == 3 else normalized
