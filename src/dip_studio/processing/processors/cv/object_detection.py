"""Object detection processors — template matching, Hough circles/lines.

All processors follow the ``BaseProcessor`` contract. OpenCV is used for the
actual detectors and failures are reported explicitly to the application.
"""
from __future__ import annotations

import importlib.util

import numpy as np

from dip_studio.core.errors import OptionalBackendError, ProcessingError
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param

_CV2 = importlib.util.find_spec("cv2") is not None


def _to_gray(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return arr.astype(np.uint8)
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    return (
        0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    ).astype(np.uint8)


def _ensure_drawable(arr: np.ndarray) -> np.ndarray:
    """Return a writable RGB/RGBA canvas without changing existing channels."""
    if arr.ndim == 2:
        return np.stack([arr, arr, arr], axis=-1)
    return arr.copy()


def _float_param(request: ProcessingRequest, name: str, default: str, minimum: float) -> float:
    try:
        return max(minimum, float(_param(request, name, default)))
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _int_param(request: ProcessingRequest, name: str, default: str, minimum: int) -> int:
    try:
        return max(minimum, int(float(_param(request, name, default))))
    except (TypeError, ValueError, OverflowError):
        return int(default)


class TemplateMatchProcessor(BaseProcessor):
    """Draw the best normalized template match on the source image."""

    operation = "template_match"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        tmpl_bid = _param(request, "template_buffer_id", "")
        method_str = _param(request, "method", "TM_CCOEFF_NORMED")
        if not tmpl_bid or not self._store.has(tmpl_bid):
            raise ProcessingError("template_match requires a valid template_buffer_id")
        if not _CV2:
            raise OptionalBackendError("template_match requires the optional OpenCV backend")

        import cv2

        tmpl_arr = self._store.get(tmpl_bid)
        gray_src = _to_gray(arr)
        gray_tmpl = _to_gray(tmpl_arr)
        src_h, src_w = gray_src.shape
        tmpl_h, tmpl_w = gray_tmpl.shape
        if tmpl_h > src_h or tmpl_w > src_w:
            raise ProcessingError(
                "template_match requires a template no larger than the source image"
            )

        method = getattr(cv2, method_str, None)
        allowed = (cv2.TM_CCOEFF_NORMED, cv2.TM_SQDIFF_NORMED)
        if method not in allowed:
            raise ProcessingError(f"Unsupported template matching method: {method_str}")
        result_map = cv2.matchTemplate(gray_src, gray_tmpl, method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result_map)
        top_left = min_loc if method == cv2.TM_SQDIFF_NORMED else max_loc
        bottom_right = (top_left[0] + tmpl_w, top_left[1] + tmpl_h)
        score = min_val if method == cv2.TM_SQDIFF_NORMED else max_val
        print(f"[TemplateMatch] Best match at {top_left} score={score:.4f}")

        out = _ensure_drawable(arr)
        if out.shape[2] == 4:
            canvas = out[:, :, :3]
        else:
            canvas = out
        cv2.rectangle(canvas, top_left, bottom_right, (0, 255, 0), 2)
        return out


class HoughCirclesProcessor(BaseProcessor):
    """Detect circular objects and draw their centres and circumferences."""

    operation = "hough_circles"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        dp = _float_param(request, "dp", "1.0", 0.1)
        min_dist = _float_param(request, "min_dist", "20", 1.0)
        p1 = _float_param(request, "param1", "100", 1.0)
        p2 = _float_param(request, "param2", "30", 1.0)
        min_r = _int_param(request, "min_radius", "0", 0)
        max_r = _int_param(request, "max_radius", "0", 0)
        if max_r and max_r < min_r:
            raise ProcessingError("hough_circles max_radius must be 0 or >= min_radius")
        if not _CV2:
            raise OptionalBackendError("hough_circles requires the optional OpenCV backend")

        import cv2

        gray = _to_gray(arr)
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=dp,
            minDist=min_dist,
            param1=p1,
            param2=p2,
            minRadius=min_r,
            maxRadius=max_r,
        )
        out = _ensure_drawable(arr)
        canvas = out[:, :, :3]
        if circles is not None:
            circles_i = np.round(circles[0]).astype(int)
            print(f"[HoughCircles] Detected {len(circles_i)} circles")
            for cx, cy, radius in circles_i:
                cv2.circle(canvas, (int(cx), int(cy)), int(radius), (0, 255, 0), 2)
                cv2.circle(canvas, (int(cx), int(cy)), 2, (0, 0, 255), 3)
        else:
            print("[HoughCircles] No circles detected")
        return out


class HoughLinesProcessor(BaseProcessor):
    """Detect straight line segments and draw them on the source image."""

    operation = "hough_lines"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        threshold = _int_param(request, "threshold", "80", 1)
        min_length = _float_param(request, "min_length", "50", 1.0)
        max_gap = _float_param(request, "max_gap", "10", 0.0)
        if not _CV2:
            raise OptionalBackendError("hough_lines requires the optional OpenCV backend")

        import cv2

        gray = _to_gray(arr)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180,
            threshold,
            minLineLength=min_length,
            maxLineGap=max_gap,
        )
        out = _ensure_drawable(arr)
        canvas = out[:, :, :3]
        if lines is not None:
            print(f"[HoughLines] Detected {len(lines)} line segments")
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        else:
            print("[HoughLines] No lines detected")
        return out
