"""Bridge processors mapping tool definitions (blur, edge, morphology) to specific algorithms."""

from __future__ import annotations

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param
from dip_studio.processing.processors.edge import CannyProcessor, SobelProcessor
from dip_studio.processing.processors.morphology import (
    DilateProcessor,
    ErodeProcessor,
    MorphCloseProcessor,
    MorphOpenProcessor,
)
from dip_studio.processing.processors.spatial import (
    GaussianBlurProcessor,
    MedianBlurProcessor,
)


class BlurToolProcessor(BaseProcessor):
    """Bridge for the interactive 'blur' tool (radius, method)."""

    operation = "blur"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        method = _param(request, "method", "Gaussian").strip().capitalize()
        radius = max(0.1, float(_param(request, "radius", "3.0")))
        ksize = max(1, int(radius * 2) + 1)

        if method == "Median":
            req = ProcessingRequest("median_blur", (("kernel_size", str(ksize)),))
            return MedianBlurProcessor(self._store)._apply(arr, req)
        else:
            sigma = max(0.5, radius / 2.0)
            req = ProcessingRequest(
                "gaussian_blur",
                (("kernel_size", str(ksize)), ("sigma", str(sigma))),
            )
            return GaussianBlurProcessor(self._store)._apply(arr, req)


class EdgeToolProcessor(BaseProcessor):
    """Bridge for the interactive 'edge' tool (threshold, automatic)."""

    operation = "edge"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        automatic = _param(request, "automatic", "True").strip().lower() in ("true", "1")
        th = max(1, int(float(_param(request, "threshold", "128"))))

        if automatic:
            req = ProcessingRequest("sobel", ())
            return SobelProcessor(self._store)._apply(arr, req)
        else:
            req = ProcessingRequest(
                "canny",
                (("threshold1", str(max(1, th // 2))), ("threshold2", str(th))),
            )
            return CannyProcessor(self._store)._apply(arr, req)


class MorphologyToolProcessor(BaseProcessor):
    """Bridge for the interactive 'morphology' tool (operation, kernel_size)."""

    operation = "morphology"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        op = _param(request, "operation", "Erode").strip().lower()
        ksize = max(1, int(float(_param(request, "kernel_size", "3"))))
        sub_req = ProcessingRequest(op, (("kernel_size", str(ksize)),))

        if op in ("dilate", "dilation"):
            return DilateProcessor(self._store)._apply(arr, sub_req)
        elif op in ("open", "morph_open", "opening"):
            return MorphOpenProcessor(self._store)._apply(arr, sub_req)
        elif op in ("close", "morph_close", "closing"):
            return MorphCloseProcessor(self._store)._apply(arr, sub_req)
        else:
            return ErodeProcessor(self._store)._apply(arr, sub_req)
