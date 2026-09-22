"""Object detection processors — template matching, Hough circles/lines.

All processors follow the ``BaseProcessor`` contract.
OpenCV is used opportunistically; pure NumPy fallbacks are provided.

Architecture: doc-12 Computer Vision — Detection pipeline.
"""
from __future__ import annotations

import importlib.util

import numpy as np

from dip_studio.processing.processors._base import BaseProcessor, _param
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.core.errors import OptionalBackendError, ProcessingError

_CV2 = importlib.util.find_spec("cv2") is not None


def _to_gray(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return arr.astype(np.uint8)
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    return (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)


def _ensure_rgba(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
    if arr.shape[2] == 3:
        return np.concatenate([arr, np.full((*arr.shape[:2], 1), 255, dtype=arr.dtype)], axis=-1)
    return arr.copy()


class TemplateMatchProcessor(BaseProcessor):
    """Template matching using normalized cross-correlation.

    Draws a rectangle around the best match region in the output image.
    When no template buffer is provided, returns the input unchanged.

    parameters:
        template_buffer_id — buffer_id of the template image in DataStore
        method             — "TM_CCOEFF_NORMED" (default) | "TM_SQDIFF_NORMED"
    """

    operation = "template_match"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        tmpl_bid = _param(request, "template_buffer_id", "")
        method_str = _param(request, "method", "TM_CCOEFF_NORMED")

        if not tmpl_bid or not self._store.has(tmpl_bid):
            raise ProcessingError(
                "template_match requires a valid template_buffer_id"
            )

        if not _CV2:
            raise OptionalBackendError(
                "template_match requires the optional OpenCV backend"
            )

        import cv2

        tmpl_arr = self._store.get(tmpl_bid)
        gray_src = _to_gray(arr)
        gray_tmpl = _to_gray(tmpl_arr)

        method = getattr(cv2, method_str, cv2.TM_CCOEFF_NORMED)
        result_map = cv2.matchTemplate(gray_src, gray_tmpl, method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result_map)

        th, tw = gray_tmpl.shape[:2]
        top_left = max_loc
        bottom_right = (top_left[0] + tw, top_left[1] + th)

        print(f"[TemplateMatch] Best match at {top_left} score={max_val:.4f}")

        out = _ensure_rgba(arr)
        bgr = cv2.cvtColor(out[:, :, :3], cv2.COLOR_RGB2BGR)
        cv2.rectangle(bgr, top_left, bottom_right, (0, 255, 0), 2)
        out[:, :, :3] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return out


class HoughCirclesProcessor(BaseProcessor):
    """Hough circle transform — detect circular objects.

    parameters:
        dp           — inverse ratio of accumulator resolution (default: 1.0)
        min_dist     — minimum distance between circle centres (default: 20)
        param1       — Canny high threshold (default: 100)
        param2       — accumulator threshold (default: 30)
        min_radius   — minimum circle radius (default: 0)
        max_radius   — maximum circle radius (default: 0 = no limit)
    """

    operation = "hough_circles"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        dp = float(_param(request, "dp", "1.0"))
        min_dist = float(_param(request, "min_dist", "20"))
        p1 = float(_param(request, "param1", "100"))
        p2 = float(_param(request, "param2", "30"))
        min_r = int(_param(request, "min_radius", "0"))
        max_r = int(_param(request, "max_radius", "0"))

        if not _CV2:
            raise OptionalBackendError(
                "hough_circles requires the optional OpenCV backend"
            )

        import cv2

        gray = _to_gray(arr)
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, dp=dp, minDist=min_dist,
            param1=p1, param2=p2, minRadius=min_r, maxRadius=max_r,
        )

        out = _ensure_rgba(arr)
        if circles is not None:
            circles_i = np.round(circles[0]).astype(int)
            print(f"[HoughCircles] Detected {len(circles_i)} circles")
            bgr = cv2.cvtColor(out[:, :, :3], cv2.COLOR_RGB2BGR)
            for (cx, cy, r) in circles_i:
                cv2.circle(bgr, (cx, cy), r, (0, 255, 0), 2)
                cv2.circle(bgr, (cx, cy), 2, (0, 0, 255), 3)
            out[:, :, :3] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        else:
            print("[HoughCircles] No circles detected")
        return out


class HoughLinesProcessor(BaseProcessor):
    """Probabilistic Hough line transform — detect straight lines.

    parameters:
        threshold    — accumulator threshold (default: 80)
        min_length   — minimum line length in pixels (default: 50)
        max_gap      — max gap between line segments (default: 10)
    """

    operation = "hough_lines"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        threshold = int(_param(request, "threshold", "80"))
        min_length = float(_param(request, "min_length", "50"))
        max_gap = float(_param(request, "max_gap", "10"))

        if not _CV2:
            raise OptionalBackendError(
                "hough_lines requires the optional OpenCV backend"
            )

        import cv2

        gray = _to_gray(arr)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold,
                                minLineLength=min_length, maxLineGap=max_gap)

        out = _ensure_rgba(arr)
        if lines is not None:
            print(f"[HoughLines] Detected {len(lines)} line segments")
            bgr = cv2.cvtColor(out[:, :, :3], cv2.COLOR_RGB2BGR)
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
            out[:, :, :3] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        else:
            print("[HoughLines] No lines detected")
        return out
