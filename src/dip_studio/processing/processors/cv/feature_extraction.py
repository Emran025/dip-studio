"""Feature extraction processors — SIFT, ORB, FAST, GLCM texture.

All processors follow the ``BaseProcessor`` contract: they receive a
``buffer_id`` string from ``ImageDataStore``, apply the algorithm, and
return a new ``buffer_id`` containing the visualisation / annotated result.

OpenCV is required by the feature detectors; unavailable backend support is
reported explicitly instead of returning a successful no-op.

Architecture: doc-12 Computer Vision, doc-07 description/recognition.
"""
from __future__ import annotations

import importlib.util

import numpy as np

from dip_studio.processing.processors._base import BaseProcessor
from dip_studio.processing.contracts import FeatureResult, ProcessingRequest
from dip_studio.core.errors import OptionalBackendError

_CV2 = importlib.util.find_spec("cv2") is not None


def _feature_result(algorithm: str, keypoints: list, descriptors: object | None, *, extra: dict[str, float | int | str] | None = None) -> FeatureResult:
    metrics: dict[str, float | int | str] = {
        "algorithm": algorithm,
        "keypoints": len(keypoints),
        "descriptor_dim": int(getattr(descriptors, "shape", (0, 0))[1]) if descriptors is not None and hasattr(descriptors, "shape") and len(descriptors.shape) > 1 else 0,
    }
    if extra:
        metrics.update(extra)
    return FeatureResult(metrics)


def _to_gray(arr: np.ndarray) -> np.ndarray:
    """Convert RGBA/RGB/Gray array to uint8 grayscale."""
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


class SiftProcessor(BaseProcessor):
    """Detect and describe SIFT keypoints; returns image with keypoints drawn.

    parameters:
        n_features   — max keypoints to detect (default: 500)
        draw         — "true" | "false" (default: "true") — draw keypoints on output
    """

    operation = "sift"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        n_features = int(self._param(request, "n_features", "500"))
        draw = self._param(request, "draw", "true").lower() == "true"

        if not _CV2:
            raise OptionalBackendError("sift requires the optional OpenCV backend")

        import cv2  # noqa: F811

        gray = _to_gray(arr)
        sift = cv2.SIFT_create(nfeatures=n_features)  # type: ignore[attr-defined]
        keypoints, descriptors = sift.detectAndCompute(gray, None)
        print(f"[SIFT] Detected {len(keypoints)} keypoints | "
              f"descriptor shape: {descriptors.shape if descriptors is not None else 'None'}")

        if draw and keypoints:
            result = _ensure_rgba(arr)
            bgr = cv2.cvtColor(result[:, :, :3], cv2.COLOR_RGB2BGR)
            drawn = cv2.drawKeypoints(bgr, keypoints, None,
                                      flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
            result[:, :, :3] = cv2.cvtColor(drawn, cv2.COLOR_BGR2RGB)
            _ = result
        return _feature_result("sift", keypoints, descriptors, extra={"drawn": int(draw)})


class OrbProcessor(BaseProcessor):
    """Detect and describe ORB keypoints (faster than SIFT, patent-free).

    parameters:
        n_features — max keypoints (default: 500)
    """

    operation = "orb"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        n_features = int(self._param(request, "n_features", "500"))

        if not _CV2:
            raise OptionalBackendError("orb requires the optional OpenCV backend")

        import cv2

        gray = _to_gray(arr)
        orb = cv2.ORB_create(nfeatures=n_features)
        keypoints, descriptors = orb.detectAndCompute(gray, None)
        print(f"[ORB] Detected {len(keypoints)} keypoints | "
              f"descriptor shape: {descriptors.shape if descriptors is not None else 'None'}")

        if keypoints:
            result = _ensure_rgba(arr)
            bgr = cv2.cvtColor(result[:, :, :3], cv2.COLOR_RGB2BGR)
            drawn = cv2.drawKeypoints(bgr, keypoints, None, color=(0, 255, 0))
            result[:, :, :3] = cv2.cvtColor(drawn, cv2.COLOR_BGR2RGB)
            _ = result
        return _feature_result("orb", keypoints, descriptors, extra={"drawn": 1})


class FastProcessor(BaseProcessor):
    """FAST corner detector — fastest keypoint detector in OpenCV.

    parameters:
        threshold  — FAST intensity threshold (default: 10)
        non_max    — "true"|"false" non-maximum suppression (default: "true")
    """

    operation = "fast_corners"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        threshold = int(self._param(request, "threshold", "10"))
        non_max = self._param(request, "non_max", "true").lower() == "true"

        if not _CV2:
            raise OptionalBackendError("fast_corners requires the optional OpenCV backend")

        import cv2

        gray = _to_gray(arr)
        fast = cv2.FastFeatureDetector_create(threshold=threshold, nonmaxSuppression=non_max)
        keypoints = fast.detect(gray, None)
        print(f"[FAST] Detected {len(keypoints)} corners")

        if keypoints:
            result = _ensure_rgba(arr)
            bgr = cv2.cvtColor(result[:, :, :3], cv2.COLOR_RGB2BGR)
            drawn = cv2.drawKeypoints(bgr, keypoints, None, color=(255, 0, 0))
            result[:, :, :3] = cv2.cvtColor(drawn, cv2.COLOR_BGR2RGB)
            _ = result
        return _feature_result("fast", keypoints, None, extra={"threshold": threshold, "non_max": int(non_max)})


class GlcmTextureProcessor(BaseProcessor):
    """Grey-Level Co-occurrence Matrix (GLCM) texture feature extraction.

    Computes contrast, dissimilarity, homogeneity, energy, correlation, ASM
    and prints them to the console.  Returns the input image unchanged
    (texture features are not spatially renderable).

    Uses scikit-image when available; falls back to a simple co-occurrence
    computed with NumPy.

    parameters:
        distances  — comma-separated pixel distances (default: "1")
        angles     — comma-separated angles in degrees (default: "0,45,90,135")
    """

    operation = "glcm_texture"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        distances_str = self._param(request, "distances", "1")
        angles_str = self._param(request, "angles", "0,45,90,135")
        distances = [int(d.strip()) for d in distances_str.split(",") if d.strip()]
        angles_deg = [float(a.strip()) for a in angles_str.split(",") if a.strip()]
        import math
        angles_rad = [math.radians(a) for a in angles_deg]

        gray = _to_gray(arr)

        skimage_available = importlib.util.find_spec("skimage") is not None
        if skimage_available:
            from skimage.feature import graycomatrix, graycoprops  # type: ignore
            glcm = graycomatrix(gray, distances=distances, angles=angles_rad,
                                levels=256, symmetric=True, normed=True)
            for prop in ("contrast", "dissimilarity", "homogeneity", "energy", "correlation", "ASM"):
                values = graycoprops(glcm, prop)
                print(f"[GLCM] {prop}: {values.tolist()}")
        else:
            # NumPy fallback — single distance=1, angle=0
            g = gray.astype(np.int32)
            shifted = np.roll(g, -1, axis=1)
            shifted[:, -1] = 0
            pairs = np.stack([g, shifted], axis=-1).reshape(-1, 2)
            pairs = pairs[pairs[:, 1] != 0]
            glcm = np.zeros((256, 256), dtype=np.float32)
            np.add.at(glcm, (pairs[:, 0], pairs[:, 1]), 1)
            glcm /= max(glcm.sum(), 1)
            print(f"[GLCM NumPy fallback] energy={float((glcm**2).sum()):.4f}")

        return arr  # texture features printed — image returned unchanged
