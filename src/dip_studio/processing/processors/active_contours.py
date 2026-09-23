"""Active contours (snakes) processor.

Uses ``skimage.segmentation.active_contour`` when available.
Raises an explicit optional-backend error when scikit-image is absent.

Architecture: doc-07 segmentation / doc-12 roadmap Phase 4.
"""
from __future__ import annotations

import importlib.util

import numpy as np

from dip_studio.processing.processors._base import BaseProcessor
from dip_studio.processing.processors._base import _param
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.core.errors import OptionalBackendError

_SKIMAGE = importlib.util.find_spec("skimage") is not None


def _to_gray(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return arr.astype(np.float64) / 255.0
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    return (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.float64) / 255.0


class ActiveContoursProcessor(BaseProcessor):
    """Evolve a circular initial contour using the active contour (snake) model.

    The initial contour is a circle centred on the image with radius
    ``init_radius`` pixels (default: min(H, W) // 3).  After convergence the
    final contour points are drawn on the output image as a green polyline.

    parameters:
        alpha       — contour elasticity (default: 0.015)
        beta        — contour rigidity  (default: 10)
        gamma       — gradient step size (default: 0.001)
        max_iter    — max iterations (default: 2500)
        init_radius — initial circle radius in pixels (default: 0 → auto)
    """

    operation = "active_contours"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        alpha = float(_param(request, "alpha", "0.015"))
        beta = float(_param(request, "beta", "10"))
        gamma = float(_param(request, "gamma", "0.001"))
        max_iter = int(_param(request, "max_iter", "2500"))
        init_radius = int(_param(request, "init_radius", "0"))

        h, w = arr.shape[:2]
        if init_radius <= 0:
            init_radius = min(h, w) // 3
        cx, cy = w // 2, h // 2

        if not _SKIMAGE:
            raise OptionalBackendError(
                "active_contours requires the optional scikit-image backend"
            )

        from skimage.segmentation import active_contour  # type: ignore
        from skimage.filters import gaussian as sk_gaussian  # type: ignore

        gray = _to_gray(arr)
        smoothed = sk_gaussian(gray, sigma=3)

        # Build circular initial contour.
        t = np.linspace(0, 2 * np.pi, 400)
        snake_init = np.array([
            cy + init_radius * np.sin(t),
            cx + init_radius * np.cos(t),
        ]).T

        snake = active_contour(
            smoothed,
            snake_init,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            max_num_iter=max_iter,
        )

        print(f"[ActiveContours] Contour settled: {len(snake)} points "
              f"cx≈{snake[:, 1].mean():.1f} cy≈{snake[:, 0].mean():.1f}")

        # Draw the contour on the result.
        out: np.ndarray
        if arr.ndim == 2:
            out = np.repeat(arr[:, :, None], 3, axis=2)
        else:
            out = arr.copy()

        # Draw as green polyline.
        pts = snake.astype(int)
        for i in range(len(pts) - 1):
            r0, c0 = np.clip(pts[i], [0, 0], [h - 1, w - 1])
            r1, c1 = np.clip(pts[i + 1], [0, 0], [h - 1, w - 1])
            # Bresenham-like: just stamp the two endpoints for simplicity.
            out[r0, c0, :3] = [0, 220, 0]
            out[r1, c1, :3] = [0, 220, 0]
            if out.shape[2] == 4:
                out[r0, c0, 3] = 255
                out[r1, c1, 3] = 255
        return out
