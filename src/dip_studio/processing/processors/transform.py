"""Geometric transform processors: Rotate, Flip, Crop."""
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


class RotateProcessor(BaseProcessor):
    """Rotate image by 90, 180, 270 degrees or arbitrary angle."""

    operation = "rotate"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        degrees = float(_param(request, "degrees", "90"))
        norm_deg = int(degrees) % 360

        if norm_deg == 90:
            # 90 degrees clockwise
            return np.rot90(arr, k=-1)
        elif norm_deg == 180:
            return np.rot90(arr, k=2)
        elif norm_deg == 270:
            # 90 degrees counter-clockwise
            return np.rot90(arr, k=1)
        elif norm_deg == 0:
            return arr.copy()

        # Arbitrary angle rotation
        if _CV2_AVAILABLE:
            h, w = arr.shape[:2]
            center = (w / 2.0, h / 2.0)
            matrix = cv2.getRotationMatrix2D(center, -degrees, 1.0)
            return cv2.warpAffine(
                arr,
                matrix,
                (w, h),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0, 0) if arr.ndim == 3 and arr.shape[2] == 4 else (0, 0, 0),
            )

        # Fallback using PIL if available
        try:
            from PIL import Image as PilImage  # type: ignore[import-untyped]

            mode = "RGBA" if (arr.ndim == 3 and arr.shape[2] == 4) else "RGB"
            if arr.ndim == 2:
                mode = "L"
            img = PilImage.fromarray(arr, mode)
            rotated = img.rotate(-degrees, expand=False)
            return np.array(rotated, dtype=np.uint8)
        except ImportError:
            # Fallback to nearest 90
            k = -round(degrees / 90.0) % 4
            return np.rot90(arr, k=k)


class FlipProcessor(BaseProcessor):
    """Flip image horizontally or vertically."""

    operation = "flip"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        direction = _param(request, "direction", "horizontal").strip().lower()
        if direction in ("horizontal", "h"):
            return np.ascontiguousarray(np.fliplr(arr))
        elif direction in ("vertical", "v"):
            return np.ascontiguousarray(np.flipud(arr))
        return arr.copy()


class CropProcessor(BaseProcessor):
    """Crop image to rectangle (x, y, width, height)."""

    operation = "crop"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        h, w = arr.shape[:2]
        x = max(0, int(float(_param(request, "x", "0"))))
        y = max(0, int(float(_param(request, "y", "0"))))
        cw = int(float(_param(request, "width", str(w))))
        ch = int(float(_param(request, "height", str(h))))

        x2 = min(w, x + max(1, cw))
        y2 = min(h, y + max(1, ch))

        if x >= w or y >= h or x >= x2 or y >= y2:
            return arr.copy()

        return np.ascontiguousarray(arr[y:y2, x:x2])
