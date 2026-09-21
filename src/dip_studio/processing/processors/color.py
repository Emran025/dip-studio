"""Color adjustment processors: grayscale conversion, hue/saturation."""
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


class GrayscaleProcessor(BaseProcessor):
    """Convert image to grayscale (luminosity method)."""
    operation = "grayscale"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        if arr.ndim == 2:
            return np.stack([arr, arr, arr], axis=-1)
        if arr.shape[2] >= 3:
            gray = (0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]).astype(np.uint8)
        else:
            gray = arr[:,:,0]
        result = np.stack([gray, gray, gray], axis=-1)
        if arr.ndim == 3 and arr.shape[2] == 4:
            result = np.concatenate([result, arr[:,:,3:4]], axis=-1)
        return result


class HueSaturationProcessor(BaseProcessor):
    """Adjust hue rotation and saturation scaling in HSV space."""
    operation = "hue_saturation"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        hue_shift = float(_param(request, "hue_shift", "0"))        # degrees, -180 to 180
        sat_scale = float(_param(request, "saturation_scale", "1.0"))  # multiplier
        lightness_offset = float(_param(request, "lightness_offset", "0"))  # -100 to 100

        rgb = arr[:,:,:3].astype(np.uint8) if arr.ndim == 3 else arr
        has_alpha = arr.ndim == 3 and arr.shape[2] == 4

        if _CV2_AVAILABLE:
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
            hsv[:,:,0] = (hsv[:,:,0] + hue_shift / 2.0) % 180  # OpenCV hue is 0-179
            hsv[:,:,1] = np.clip(hsv[:,:,1] * sat_scale, 0, 255)
            hsv[:,:,2] = np.clip(hsv[:,:,2] + lightness_offset, 0, 255)
            result_rgb = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
        else:
            # NumPy fallback: simple saturation via luminance desaturation blend
            gray = (0.299 * rgb[:,:,0] + 0.587 * rgb[:,:,1] + 0.114 * rgb[:,:,2])
            gray3 = np.stack([gray, gray, gray], axis=-1)
            result_rgb = np.clip((rgb.astype(np.float32) - gray3) * sat_scale + gray3 + lightness_offset, 0, 255).astype(np.uint8)

        if has_alpha:
            return np.concatenate([result_rgb, arr[:,:,3:4]], axis=-1)
        return result_rgb
