"""NumPy-backed document compositor that produces JPEG/PNG preview bytes.

Rendering is separated from processing: processors return data,
this compositor turns layer data into a displayable image.
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

import numpy as np

from dip_studio.rendering.ports import RenderRequest

if TYPE_CHECKING:
    from dip_studio.application.editor import EditorController

import importlib.util

_PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None


class NumpyDocumentRenderer:
    """Composites visible layers from DataStore into JPEG bytes for CanvasView."""

    def __init__(self, controller: EditorController) -> None:
        self._controller = controller

    def render(self, request: RenderRequest) -> bytes:
        if request.viewport_width <= 0 or request.viewport_height <= 0:
            raise ValueError("Viewport dimensions must be positive")

        controller = self._controller
        document = controller.document
        if document is None:
            return _blank_jpeg(request.viewport_width, request.viewport_height)

        data_store = controller.data_store
        if data_store is None:
            return _blank_jpeg(request.viewport_width, request.viewport_height)

        # Collect visible layers with buffers (bottom to top)
        composited: np.ndarray | None = None
        img_w = document.image.width
        img_h = document.image.height

        for layer in reversed(document.layers):
            if not layer.visible or layer.buffer_id is None:
                continue
            try:
                arr = data_store.get(layer.buffer_id)
            except KeyError:
                continue
            # Ensure RGBA
            arr_rgba = _to_rgba(arr)
            if arr_rgba.shape[:2] != (img_h, img_w):
                arr_rgba = _resize_array(arr_rgba, img_w, img_h)
            # Apply opacity
            if layer.opacity < 1.0:
                arr_rgba = arr_rgba.copy()
                arr_rgba[:, :, 3] = (arr_rgba[:, :, 3] * layer.opacity).astype(np.uint8)

            if composited is None:
                composited = arr_rgba.astype(np.float32)
            else:
                blend_mode = getattr(layer, "blend_mode", "normal") or "normal"
                composited = _alpha_composite(
                    composited, arr_rgba.astype(np.float32), blend_mode
                )

        if composited is None:
            return _blank_jpeg(request.viewport_width, request.viewport_height)

        result = np.clip(composited, 0, 255).astype(np.uint8)
        return _encode_jpeg(result)


def _to_rgba(arr: np.ndarray) -> np.ndarray:
    """Convert any ndarray to uint8 RGBA (H, W, 4)."""
    if arr.ndim == 2:
        # Grayscale → RGBA
        rgba = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
    elif arr.shape[2] == 3:
        # RGB → RGBA
        alpha = np.full((*arr.shape[:2], 1), 255, dtype=arr.dtype)
        rgba = np.concatenate([arr, alpha], axis=-1)
    elif arr.shape[2] == 4:
        rgba = arr
    else:
        rgba = arr[:, :, :4]
    return rgba.astype(np.uint8)


def _resize_array(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    """Resize using Pillow if available, otherwise crop/pad."""
    if _PILLOW_AVAILABLE:
        from PIL import Image as PilImage  # type: ignore[import-untyped]
        mode = "RGBA" if arr.shape[2] == 4 else "RGB"
        img = PilImage.fromarray(arr, mode)
        img = img.resize((w, h), PilImage.Resampling.LANCZOS)
        return np.array(img, dtype=np.uint8)
    # Fallback: crop or zero-pad
    out = np.zeros((h, w, arr.shape[2]), dtype=np.uint8)
    ch = min(h, arr.shape[0])
    cw = min(w, arr.shape[1])
    out[:ch, :cw] = arr[:ch, :cw]
    return out


def _alpha_composite(
    base: np.ndarray,
    overlay: np.ndarray,
    blend_mode: str = "normal",
) -> np.ndarray:
    """Porter-Duff source-over in float32 (H, W, 4), with blend-mode support."""
    # Normalise to [0, 1] for blend calculations
    base_f = base / 255.0
    over_f = overlay / 255.0

    a_o = over_f[:, :, 3:4]
    a_b = base_f[:, :, 3:4]

    # Apply the blend mode to the RGB channels
    base_rgb = base_f[:, :, :3]
    over_rgb = over_f[:, :, :3]
    blended_rgb = _apply_blend_mode(base_rgb, over_rgb, blend_mode)

    # Porter-Duff source-over compositing
    a_out = a_o + a_b * (1.0 - a_o)
    denom = np.where(a_out > 0, a_out, 1.0)
    rgb_out = (blended_rgb * a_o + base_rgb * a_b * (1.0 - a_o)) / denom

    result = np.concatenate([rgb_out * 255.0, a_out * 255.0], axis=-1)
    return result


def _apply_blend_mode(
    base: np.ndarray, overlay: np.ndarray, mode: str
) -> np.ndarray:
    """Return blended RGB in [0,1]. Both inputs are float32 (H,W,3) in [0,1]."""
    if mode == "normal":
        return overlay
    elif mode == "multiply":
        return base * overlay
    elif mode == "screen":
        return 1.0 - (1.0 - base) * (1.0 - overlay)
    elif mode == "overlay":
        return np.where(
            base < 0.5,
            2.0 * base * overlay,
            1.0 - 2.0 * (1.0 - base) * (1.0 - overlay),
        )
    elif mode == "soft_light":
        return np.where(
            overlay <= 0.5,
            base - (1.0 - 2.0 * overlay) * base * (1.0 - base),
            base + (2.0 * overlay - 1.0) * (
                np.where(base <= 0.25,
                         ((16.0 * base - 12.0) * base + 4.0) * base,
                         np.sqrt(np.clip(base, 0, 1))) - base
            ),
        )
    elif mode == "hard_light":
        return np.where(
            overlay < 0.5,
            2.0 * base * overlay,
            1.0 - 2.0 * (1.0 - base) * (1.0 - overlay),
        )
    elif mode == "darken":
        return np.minimum(base, overlay)
    elif mode == "lighten":
        return np.maximum(base, overlay)
    elif mode == "difference":
        return np.abs(base - overlay)
    elif mode == "exclusion":
        return base + overlay - 2.0 * base * overlay
    elif mode == "color_dodge":
        return np.where(
            overlay >= 1.0, 1.0, np.clip(base / (1.0 - overlay + 1e-9), 0, 1)
        )
    elif mode == "color_burn":
        return np.where(
            overlay <= 0.0, 0.0, np.clip(1.0 - (1.0 - base) / (overlay + 1e-9), 0, 1)
        )
    # Unknown mode → fall back to normal
    return overlay


def _encode_jpeg(arr: np.ndarray) -> bytes:
    """Encode ndarray to JPEG bytes. Falls back to PPM if Pillow is unavailable."""
    if _PILLOW_AVAILABLE:
        from PIL import Image as PilImage  # type: ignore[import-untyped]
        # Convert RGBA → RGB for JPEG (JPEG has no alpha)
        if arr.ndim == 3 and arr.shape[2] == 4:
            rgb = arr[:, :, :3]
        else:
            rgb = arr
        img = PilImage.fromarray(rgb.astype(np.uint8), "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    # Fallback PPM
    if arr.ndim == 3 and arr.shape[2] == 4:
        rgb = arr[:, :, :3]
    else:
        rgb = arr
    h, w = rgb.shape[:2]
    header = f"P6\n{w} {h}\n255\n".encode("ascii")
    return header + rgb.astype(np.uint8).tobytes()


def _blank_jpeg(w: int, h: int) -> bytes:
    arr = np.full((h, w, 3), 200, dtype=np.uint8)
    return _encode_jpeg(arr)
