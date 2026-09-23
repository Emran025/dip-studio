"""Intensity transformation processors: negative, gamma, log, brightness/contrast.

NumPy educational implementations as per doc 07-dip-processing-engine-and-library-stack.md.
"""

from __future__ import annotations

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param


class NegativeProcessor(BaseProcessor):
    """Photographic negative: I_out = 255 - I_in."""

    operation = "negative"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        return (255 - arr.astype(np.int16)).clip(0, 255).astype(np.uint8)


class GammaProcessor(BaseProcessor):
    """Power-law (gamma) transformation: I_out = (I_in/255)^gamma * 255."""

    operation = "gamma"

    def validate(self, request: ProcessingRequest) -> None:
        gamma_s = _param(request, "gamma", "1.0")
        try:
            g = float(gamma_s)
            if g <= 0:
                raise ValueError("gamma must be positive")
        except ValueError as e:
            raise ValueError(f"Invalid gamma parameter: {e}") from e

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        gamma = float(_param(request, "gamma", "1.0"))
        normalized = arr.astype(np.float32) / 255.0
        result = np.power(np.clip(normalized, 0.0, 1.0), gamma)
        return (result * 255.0).clip(0, 255).astype(np.uint8)


class LogTransformProcessor(BaseProcessor):
    """Logarithmic transform: I_out = c * log(1 + I_in)."""

    operation = "log_transform"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        c = float(_param(request, "c", "1.0"))
        result = c * np.log1p(arr.astype(np.float32))
        # Normalize to [0, 255]
        max_val = result.max()
        if max_val > 0:
            result = result / max_val * 255.0
        return result.clip(0, 255).astype(np.uint8)


class BrightnessContrastProcessor(BaseProcessor):
    """Linear adjustment: I_out = alpha * I_in + beta.

    alpha: contrast (default 1.0), beta: brightness offset (default 0).
    """

    operation = "brightness_contrast"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        alpha = float(_param(request, "alpha", "1.0"))  # contrast
        beta = float(_param(request, "beta", "0"))  # brightness
        result = arr.astype(np.float32) * alpha + beta
        return result.clip(0, 255).astype(np.uint8)
