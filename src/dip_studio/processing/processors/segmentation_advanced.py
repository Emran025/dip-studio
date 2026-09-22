"""Advanced segmentation and shape-description processors.

Operations
----------
watershed            : Watershed segmentation with coloured region output
region_growing       : BFS region growing from a seed pixel
contour_extract      : Morphological contour extraction and overlay
hu_moments           : Compute and print the 7 Hu moment invariants
connected_components : BFS 4-connected component labelling with colour map
grabcut              : GrabCut segmentation (requires OpenCV)

All processors extend BaseProcessor and work on NumPy arrays only.
OpenCV and SciPy are used opportunistically when available but are never
required — pure-NumPy fallbacks are provided.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _ensure_3ch, _param, _to_gray
from dip_studio.core.errors import OptionalBackendError


# ---------------------------------------------------------------------------
# Colour palette for region labels
# ---------------------------------------------------------------------------

_PALETTE: list[tuple[int, int, int]] = [
    (255, 59,  59),  (59,  189, 255), (102, 255, 102), (255, 200, 59),
    (200, 59,  255), (59,  255, 200), (255, 130, 59),  (59,  59,  255),
    (200, 255, 59),  (255, 59,  200), (59,  255, 130), (130, 59,  255),
    (255, 102, 102), (102, 200, 255), (200, 255, 102), (255, 255, 102),
    (102, 102, 255), (255, 102, 200), (102, 255, 255), (200, 200, 200),
]


def _label_to_colour(label: int) -> tuple[int, int, int]:
    return _PALETTE[label % len(_PALETTE)]


# ---------------------------------------------------------------------------
# Pure-NumPy distance transform approximation (used as Watershed seed input)
# ---------------------------------------------------------------------------

def _approx_distance_transform(binary: np.ndarray) -> np.ndarray:
    """Return a rough distance-transform via iterative erosion (NumPy-only)."""
    dist = np.zeros(binary.shape, dtype=np.float32)
    remaining = binary.astype(bool)
    step = 1
    while remaining.any():
        # Erode: a pixel survives if all 4-connected neighbours are True.
        eroded = (
            remaining
            & np.roll(remaining, 1, 0) & np.roll(remaining, -1, 0)
            & np.roll(remaining, 1, 1) & np.roll(remaining, -1, 1)
        )
        eroded[0, :] = False
        eroded[-1, :] = False
        eroded[:, 0] = False
        eroded[:, -1] = False
        new_pixels = remaining & ~eroded
        dist[new_pixels] = step
        remaining = eroded
        step += 1
    return dist


def _local_maxima(dist: np.ndarray, min_dist: int) -> np.ndarray:
    """Return boolean mask of local maxima separated by *min_dist* pixels."""
    from numpy.lib.stride_tricks import sliding_window_view
    k = max(3, 2 * min_dist + 1)
    pad = k // 2
    p = np.pad(dist, pad, mode="constant", constant_values=0)
    windows = sliding_window_view(p, (k, k))
    local_max = windows.max(axis=(-2, -1))
    return (dist == local_max) & (dist > 0)


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------

class WatershedProcessor(BaseProcessor):
    """Watershed segmentation producing a coloured region map.

    Parameters
    ----------
    min_distance : int  minimum distance between seeds (default 10)
    threshold    : int  binarisation threshold (default 0 → Otsu)
    """

    operation = "watershed"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        min_dist = max(1, int(float(_param(request, "min_distance", "10"))))
        thresh_val = int(float(_param(request, "threshold", "0")))
        gray = _to_gray(arr)
        h, w = gray.shape

        # Binarise
        if thresh_val == 0:
            thresh_val = int(np.mean(gray))
        binary = (gray > thresh_val).astype(np.uint8)

        # Try OpenCV watershed first.
        try:
            import cv2  # type: ignore[import-untyped]
            dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
            _, sure_fg = cv2.threshold(dist, 0.4 * dist.max(), 255, 0)
            sure_fg = sure_fg.astype(np.uint8)
            sure_bg = cv2.dilate(binary, None, iterations=3) * 255
            unknown = cv2.subtract(sure_bg, sure_fg)
            _, markers = cv2.connectedComponents(sure_fg)
            markers += 1
            markers[unknown == 255] = 0
            rgb = _ensure_3ch(arr)
            cv2.watershed(rgb, markers)
            out = np.zeros((h, w, 3), dtype=np.uint8)
            for label in range(1, markers.max() + 1):
                color = _label_to_colour(label - 1)
                out[markers == label] = color
            return out
        except ImportError:
            pass

        # Pure-NumPy fallback: distance transform + BFS region growing from seeds.
        try:
            from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]
            dist = distance_transform_edt(binary).astype(np.float32)
        except ImportError:
            dist = _approx_distance_transform(binary)

        seeds_mask = _local_maxima(dist, min_dist)
        seed_coords = list(zip(*np.where(seeds_mask)))
        labels = np.zeros((h, w), dtype=np.int32)
        q: deque[tuple[int, int, int]] = deque()
        for idx, (sy, sx) in enumerate(seed_coords, start=1):
            labels[sy, sx] = idx
            q.append((sy, sx, idx))

        while q:
            y, x, lbl = q.popleft()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and labels[ny, nx] == 0 and binary[ny, nx]:
                    labels[ny, nx] = lbl
                    q.append((ny, nx, lbl))

        out = np.zeros((h, w, 3), dtype=np.uint8)
        for label in range(1, labels.max() + 1):
            out[labels == label] = _label_to_colour(label - 1)
        return out


class RegionGrowingProcessor(BaseProcessor):
    """BFS region growing from a seed pixel.

    Parameters
    ----------
    seed_x    : int    seed x-coordinate (default: image centre)
    seed_y    : int    seed y-coordinate (default: image centre)
    tolerance : int    maximum colour distance from seed (default 15)
    """

    operation = "region_growing"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        h, w = arr.shape[:2]
        sx = int(float(_param(request, "seed_x", str(w // 2))))
        sy = int(float(_param(request, "seed_y", str(h // 2))))
        tol = int(float(_param(request, "tolerance", "15")))
        sx = max(0, min(sx, w - 1))
        sy = max(0, min(sy, h - 1))

        gray = _to_gray(arr).astype(np.int32)
        seed_val = int(gray[sy, sx])
        visited = np.zeros((h, w), dtype=bool)
        q: deque[tuple[int, int]] = deque([(sy, sx)])
        visited[sy, sx] = True

        while q:
            y, x = q.popleft()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    if abs(int(gray[ny, nx]) - seed_val) <= tol:
                        visited[ny, nx] = True
                        q.append((ny, nx))

        out = _ensure_3ch(arr).copy()
        out[visited] = (255, 0, 0)
        if arr.ndim == 3 and arr.shape[2] == 4:
            alpha = arr[:, :, 3:4]
            out = np.concatenate([out, alpha], axis=-1)
        return out


class ContourExtractProcessor(BaseProcessor):
    """Extract contours via morphological erosion and overlay them on the image.

    Parameters
    ----------
    threshold : int  binarisation threshold (default 128)
    color_r   : int  contour red channel 0-255 (default 0)
    color_g   : int  contour green channel 0-255 (default 255)
    color_b   : int  contour blue channel 0-255 (default 0)
    """

    operation = "contour_extract"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        thresh = int(float(_param(request, "threshold", "128")))
        cr = int(float(_param(request, "color_r", "0")))
        cg = int(float(_param(request, "color_g", "255")))
        cb = int(float(_param(request, "color_b", "0")))
        color = (cr, cg, cb)

        gray = _to_gray(arr)
        binary = (gray > thresh).astype(np.uint8)

        # Morphological erosion via 4-connected neighbour minimum.
        eroded = (
            binary
            & np.roll(binary, 1, 0) & np.roll(binary, -1, 0)
            & np.roll(binary, 1, 1) & np.roll(binary, -1, 1)
        )
        eroded[0, :] = 0
        eroded[-1, :] = 0
        eroded[:, 0] = 0
        eroded[:, -1] = 0
        contour_mask = (binary - eroded).astype(bool)

        out = _ensure_3ch(arr).copy()
        out[contour_mask] = color
        if arr.ndim == 3 and arr.shape[2] == 4:
            alpha = arr[:, :, 3:4]
            out = np.concatenate([out, alpha], axis=-1)
        return out


class HuMomentsProcessor(BaseProcessor):
    """Compute the 7 Hu moment invariants and print them to the console.

    The input image is returned unchanged; moments appear in the terminal.
    """

    operation = "hu_moments"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        gray = _to_gray(arr).astype(np.float64)
        h, w = gray.shape
        y_idx = np.arange(h, dtype=np.float64)
        x_idx = np.arange(w, dtype=np.float64)
        xx, yy = np.meshgrid(x_idx, y_idx)

        def _raw_moment(p: int, q: int) -> float:
            return float(np.sum((xx ** p) * (yy ** q) * gray))

        m00 = _raw_moment(0, 0)
        if m00 == 0:
            print("[DIP Studio] Hu Moments: image is empty (M00 = 0)")
            return arr

        cx = _raw_moment(1, 0) / m00
        cy = _raw_moment(0, 1) / m00

        def _central_moment(p: int, q: int) -> float:
            return float(np.sum(((xx - cx) ** p) * ((yy - cy) ** q) * gray))

        mu = {(p, q): _central_moment(p, q) for p in range(4) for q in range(4) if p + q <= 3}

        scale = m00 ** (1 + (2 + 0) / 2)

        def eta(p: int, q: int) -> float:
            gamma = (p + q) / 2.0 + 1.0
            denom = m00 ** gamma
            return mu[(p, q)] / (denom + 1e-12)

        n20, n02, n11 = eta(2, 0), eta(0, 2), eta(1, 1)
        n30, n12, n21, n03 = eta(3, 0), eta(1, 2), eta(2, 1), eta(0, 3)

        hu = [
            n20 + n02,
            (n20 - n02) ** 2 + 4 * n11 ** 2,
            (n30 - 3 * n12) ** 2 + (3 * n21 - n03) ** 2,
            (n30 + n12) ** 2 + (n21 + n03) ** 2,
            (n30 - 3 * n12) * (n30 + n12) * ((n30 + n12) ** 2 - 3 * (n21 + n03) ** 2)
            + (3 * n21 - n03) * (n21 + n03) * (3 * (n30 + n12) ** 2 - (n21 + n03) ** 2),
            (n20 - n02) * ((n30 + n12) ** 2 - (n21 + n03) ** 2)
            + 4 * n11 * (n30 + n12) * (n21 + n03),
            (3 * n21 - n03) * (n30 + n12) * ((n30 + n12) ** 2 - 3 * (n21 + n03) ** 2)
            - (n30 - 3 * n12) * (n21 + n03) * (3 * (n30 + n12) ** 2 - (n21 + n03) ** 2),
        ]

        print("[DIP Studio] Hu Moment Invariants:")
        for i, val in enumerate(hu, start=1):
            sign = -1 if val < 0 else 1
            log_val = sign * float(np.log10(abs(val) + 1e-30))
            print(f"  φ{i} = {val:.6e}  (log-scaled: {log_val:.4f})")

        return arr


class ConnectedComponentsProcessor(BaseProcessor):
    """Label connected components (4-connectivity) and render a colour map.

    Parameters
    ----------
    threshold : int  binarisation threshold (default 128)
    """

    operation = "connected_components"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        thresh = int(float(_param(request, "threshold", "128")))
        gray = _to_gray(arr)
        binary = (gray > thresh)
        h, w = binary.shape
        labels = np.zeros((h, w), dtype=np.int32)
        current_label = 0

        for sy in range(h):
            for sx in range(w):
                if binary[sy, sx] and labels[sy, sx] == 0:
                    current_label += 1
                    q: deque[tuple[int, int]] = deque([(sy, sx)])
                    labels[sy, sx] = current_label
                    while q:
                        y, x = q.popleft()
                        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            ny, nx = y + dy, x + dx
                            if 0 <= ny < h and 0 <= nx < w and binary[ny, nx] and labels[ny, nx] == 0:
                                labels[ny, nx] = current_label
                                q.append((ny, nx))

        out = np.zeros((h, w, 3), dtype=np.uint8)
        for lbl in range(1, current_label + 1):
            out[labels == lbl] = _label_to_colour(lbl - 1)
        return out


class GrabCutStubProcessor(BaseProcessor):
    """GrabCut foreground segmentation (requires OpenCV).

    If OpenCV is not installed, this processor raises an explicit optional
    backend error instead of reporting a successful no-op.

    Parameters
    ----------
    margin : float  fractional margin from image edges for the initial rect (default 0.1)
    """

    operation = "grabcut"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        margin = float(_param(request, "margin", "0.1"))
        try:
            import cv2  # type: ignore[import-untyped]
        except ImportError as exc:
            raise OptionalBackendError(
                "grabcut requires the optional OpenCV backend"
            ) from exc

        rgb = _ensure_3ch(arr)
        h, w = rgb.shape[:2]
        x0 = int(w * margin)
        y0 = int(h * margin)
        rw = max(1, w - 2 * x0)
        rh = max(1, h - 2 * y0)
        rect = (x0, y0, rw, rh)

        mask = np.zeros((h, w), dtype=np.uint8)
        bgd_model = np.zeros((1, 65), dtype=np.float64)
        fgd_model = np.zeros((1, 65), dtype=np.float64)
        cv2.grabCut(rgb, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
        fg_mask = np.where((mask == 2) | (mask == 0), 0, 1).astype(np.uint8)

        out = rgb.copy()
        out[fg_mask == 0] = 0
        if arr.ndim == 3 and arr.shape[2] == 4:
            alpha = arr[:, :, 3:4]
            out = np.concatenate([out, alpha], axis=-1)
        return out
