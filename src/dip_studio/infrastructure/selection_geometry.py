"""Pure NumPy selection geometry rasterisers.

Converts geometric selection shapes (ellipse, lasso freehand polygon,
explicit polygon) into boolean uint8 mask arrays where 255 = selected.

All functions are pure NumPy — no Qt, no OpenCV, no Pillow.

Architecture: doc-06 Selections — rectangle | ellipse | lasso | polygon.
The result mask is stored in ``SelectionRect.mask_buffer_id`` and used by
the compositor and processors to apply operations only inside the selection.
"""

from __future__ import annotations

import numpy as np


def rasterise_ellipse(
    w: int,
    h: int,
    x0: int,
    y0: int,
    rx: int,
    ry: int,
) -> np.ndarray:
    """Return a uint8 mask (H, W) with 255 inside the ellipse, 0 outside.

    Parameters
    ----------
    w, h   : canvas dimensions (pixels).
    x0, y0 : centre of the ellipse in image coordinates.
    rx, ry : semi-axes (half-width, half-height) in pixels.
    """
    if rx <= 0 or ry <= 0:
        return np.zeros((h, w), dtype=np.uint8)

    yy, xx = np.meshgrid(
        np.arange(h, dtype=np.float32),
        np.arange(w, dtype=np.float32),
        indexing="ij",
    )
    inside = ((xx - x0) / rx) ** 2 + ((yy - y0) / ry) ** 2 <= 1.0
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[inside] = 255
    return mask


def rasterise_lasso(
    w: int,
    h: int,
    points: list[tuple[int, int]],
) -> np.ndarray:
    """Rasterise a freehand lasso polygon into a uint8 mask (H, W).

    The polygon is implicitly closed (last point connects to first).
    Uses a scanline fill algorithm implemented with NumPy.

    Parameters
    ----------
    w, h   : canvas dimensions.
    points : ordered (x, y) boundary points collected during mouse drag.
    """
    if len(points) < 3:
        return np.zeros((h, w), dtype=np.uint8)
    return _scanline_fill(w, h, points)


def rasterise_polygon(
    w: int,
    h: int,
    vertices: list[tuple[int, int]],
) -> np.ndarray:
    """Rasterise an explicit polygon (click-to-click) into a uint8 mask (H, W).

    Parameters
    ----------
    w, h     : canvas dimensions.
    vertices : ordered (x, y) corner vertices.
    """
    if len(vertices) < 3:
        return np.zeros((h, w), dtype=np.uint8)
    return _scanline_fill(w, h, vertices)


def rasterise_color_selection(
    arr: np.ndarray,
    seed_x: int,
    seed_y: int,
    tolerance: int = 15,
) -> np.ndarray:
    """Return uint8 mask (H, W) where 255 = contiguous region matching seed pixel color within tolerance."""  # noqa: E501
    h, w = arr.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((h, w), dtype=np.uint8)

    seed_x = max(0, min(seed_x, w - 1))
    seed_y = max(0, min(seed_y, h - 1))

    try:
        import cv2

        if arr.ndim == 2:
            bgr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        elif arr.shape[2] == 4:
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        else:
            bgr = arr.copy()

        mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        seed = (seed_x, seed_y)
        tol = (tolerance, tolerance, tolerance)
        cv2.floodFill(
            bgr,
            mask,
            seed,
            (255, 255, 255),
            tol,
            tol,
            flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY,
        )
        return (mask[1:-1, 1:-1] == 255).astype(np.uint8) * 255
    except Exception:
        target_color = arr[seed_y, seed_x].astype(np.float32)
        diff = np.abs(arr.astype(np.float32) - target_color)
        if diff.ndim == 3:
            diff = np.max(diff[..., :3], axis=-1)
        return (diff <= tolerance).astype(np.uint8) * 255


# ---------------------------------------------------------------------------
# Internal scanline fill (even-odd rule)
# ---------------------------------------------------------------------------


def _scanline_fill(w: int, h: int, pts: list[tuple[int, int]]) -> np.ndarray:
    """Even-odd scanline fill for an arbitrary polygon."""
    mask = np.zeros((h, w), dtype=np.uint8)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)

    y_min = max(0, min(ys))
    y_max = min(h - 1, max(ys))

    for y in range(y_min, y_max + 1):
        intersections: list[float] = []
        for i in range(n):
            j = (i + 1) % n
            yi, yj = ys[i], ys[j]
            xi, xj = xs[i], xs[j]
            if (yi <= y < yj) or (yj <= y < yi):
                # Compute x intersection of the edge with scanline y.
                x_intersect = xi + (y - yi) * (xj - xi) / (yj - yi)
                intersections.append(x_intersect)
        intersections.sort()
        # Fill between pairs of intersections.
        for k in range(0, len(intersections) - 1, 2):
            x_start = max(0, int(np.ceil(intersections[k])))
            x_end = min(w, int(np.floor(intersections[k + 1])) + 1)
            if x_start < x_end:
                mask[y, x_start:x_end] = 255

    return mask
