"""NumPy-backed document compositor that produces lossless preview bytes.

Rendering is separated from processing: processors return data,
this compositor turns layer data into a displayable image.
"""
from __future__ import annotations

import io
import math
from typing import TYPE_CHECKING

import numpy as np

from dip_studio.rendering.layer_evaluation import _apply_adjustment_layer
from dip_studio.domain.model import AdjustmentLayer, FilterLayer
from dip_studio.rendering.ports import RenderRequest
from dip_studio.core.errors import RenderingError

if TYPE_CHECKING:
    from dip_studio.application.editor import EditorController

import importlib.util

_PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None


class NumpyDocumentRenderer:
    """Composites visible layers from DataStore into PNG bytes for CanvasView."""

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

        composited = self._evaluate(document, data_store)

        if composited is None:
            return _blank_jpeg(request.viewport_width, request.viewport_height)

        result = np.clip(composited, 0, 255).astype(np.uint8)
        return _encode_png(result)

    def render_raw(self, request: RenderRequest) -> "np.ndarray | None":
        """Return the composited RGBA uint8 array (H, W, 4) without encoding.

        Returns ``None`` when there is nothing to render (no document / no data).
        Callers that need bytes (e.g. export) should call ``render()`` instead.
        This path is used by ``CanvasView.set_preview_array()`` to display the
        result via ``QImage(data, w, h, stride, Format_RGBA8888)`` — no Pillow,
        no JPEG/PNG codec, zero extra copies.
        """
        if request.viewport_width <= 0 or request.viewport_height <= 0:
            return None
        controller = self._controller
        document = controller.document
        if document is None:
            return None
        data_store = controller.data_store
        if data_store is None:
            return None

        composited = self._evaluate(document, data_store)
        if composited is None:
            return None
        return np.clip(composited, 0, 255).astype(np.uint8)

    @staticmethod
    def _evaluate(document: object, data_store: object) -> np.ndarray | None:
        img_w = document.image.width
        img_h = document.image.height
        layers = {layer.id: layer for layer in document.layers}

        def evaluate_group(group: object, active: set[object]) -> np.ndarray | None:
            if group.id in active:
                raise RenderingError(f"Layer group cycle detected at '{group.name}'")
            if not group.visible:
                return None
            active.add(group.id)
            group_result: np.ndarray | None = None
            for child_id in getattr(group, "children", ()):  # bottom to top order
                child = layers.get(child_id)
                if child is None:
                    raise RenderingError(
                        f"Layer group '{group.name}' references missing child "
                        f"'{child_id}'"
                    )
                child_result = evaluate_layer(child, active)
                if isinstance(child, (AdjustmentLayer, FilterLayer)):
                    if group_result is not None:
                        group_result = _apply_adjustment_layer(group_result, child)
                    continue
                if child_result is not None:
                    group_result = _compose(
                        group_result,
                        child_result,
                        getattr(child, "blend_mode", "normal") or "normal",
                    )
            active.remove(group.id)
            if group_result is None or group.pass_through:
                return group_result
            if group.opacity < 1.0:
                group_result = group_result.copy()
                group_result[:, :, 3] = (group_result[:, :, 3] * group.opacity).astype(np.uint8)
            return group_result

        def evaluate_layer(layer: object, active: set[object]) -> np.ndarray | None:
            if layer.id in active:
                raise RenderingError(f"Layer group cycle detected at '{layer.name}'")
            if not layer.visible:
                return None
            if hasattr(layer, "children"):
                return evaluate_group(layer, active)
            if isinstance(layer, (AdjustmentLayer, FilterLayer)):
                return None
            if layer.buffer_id is None:
                return None
            try:
                arr = data_store.get(layer.buffer_id)
            except KeyError as exc:
                raise RenderingError(
                    f"Layer '{layer.name}' references missing buffer "
                    f"'{layer.buffer_id}'"
                ) from exc
            arr_rgba = _to_rgba(arr)
            arr_rgba = _transform_layer(
                arr_rgba,
                getattr(layer, "transform", None),
                img_w,
                img_h,
            )
            if layer.mask_id is not None:
                try:
                    mask_arr = data_store.get(layer.mask_id)
                except KeyError as exc:
                    raise RenderingError(
                        f"Layer '{layer.name}' references missing mask "
                        f"'{layer.mask_id}'"
                    ) from exc
                arr_rgba = _apply_mask(
                    arr_rgba,
                    mask_arr,
                    img_w,
                    img_h,
                    layer.name,
                    getattr(layer, "mask_mode", "reveal") or "reveal",
                )
            if layer.opacity < 1.0:
                arr_rgba = arr_rgba.copy()
                arr_rgba[:, :, 3] = (arr_rgba[:, :, 3] * layer.opacity).astype(np.uint8)
            return arr_rgba

        composited: np.ndarray | None = None
        top_level_ids = {child_id for layer in document.layers if hasattr(layer, "children") for child_id in layer.children}
        for layer in document.layers:
            if layer.id in top_level_ids:
                continue
            if isinstance(layer, (AdjustmentLayer, FilterLayer)):
                if composited is not None:
                    composited = _apply_adjustment_layer(composited, layer)
                continue
            layer_result = evaluate_layer(layer, set())
            if layer_result is not None:
                composited = _compose(
                    composited,
                    layer_result,
                    getattr(layer, "blend_mode", "normal") or "normal",
                )
        return composited


def _compose(
    base: np.ndarray | None,
    overlay: np.ndarray,
    blend_mode: str,
) -> np.ndarray:
    if base is None:
        return overlay.astype(np.float32)
    return _alpha_composite(base, overlay.astype(np.float32), blend_mode)


def _apply_mask(
    rgba: np.ndarray,
    mask: np.ndarray,
    width: int,
    height: int,
    layer_name: str,
    mode: str,
) -> np.ndarray:
    if mask.ndim not in (2, 3) or mask.size == 0:
        raise RenderingError(f"Layer '{layer_name}' has an invalid mask shape")
    mask_2d = mask.squeeze() if mask.ndim > 2 else mask
    if mask_2d.ndim != 2:
        raise RenderingError(f"Layer '{layer_name}' has an invalid mask shape")
    mask_2d = mask_2d.astype(np.float32)
    if mask_2d.max() > 1.0:
        mask_2d /= 255.0
    if mask_2d.shape != (height, width):
        mask_2d = _fit_array_to_document(
            np.repeat(mask_2d[:, :, None], 4, axis=2).astype(np.uint8),
            width,
            height,
        )[:, :, 0].astype(np.float32) / 255.0
    if mode == "hide":
        mask_2d = 1.0 - mask_2d
    elif mode != "reveal":
        raise RenderingError(f"Layer '{layer_name}' has an invalid mask mode")
    result = rgba.copy()
    result[:, :, 3] = (result[:, :, 3].astype(np.float32) * mask_2d).astype(np.uint8)
    return result


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


def _fit_array_to_document(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    """Fit a layer canvas without resampling or changing its pixel values."""
    out = np.zeros((h, w, arr.shape[2]), dtype=np.uint8)
    ch = min(h, arr.shape[0])
    cw = min(w, arr.shape[1])
    out[:ch, :cw] = arr[:ch, :cw]
    return out


def _transform_layer(
    arr: np.ndarray,
    transform: object | None,
    width: int,
    height: int,
) -> np.ndarray:
    """Place a layer using origin -> scale -> skew -> rotation -> translation.

    Sampling is nearest-neighbour and pixels outside the document are clipped.
    The transform origin is the layer's top-left pixel, matching the domain
    contract that transforms are relative to the layer origin.
    """
    if transform is None or getattr(transform, "is_identity", False):
        return _fit_array_to_document(arr, width, height)

    sx = float(transform.sx)
    sy = float(transform.sy)
    skew_x = math.tan(math.radians(float(transform.skew_x)))
    skew_y = math.tan(math.radians(float(transform.skew_y)))
    angle = math.radians(float(transform.rotation))
    scale = np.array([[sx, 0.0], [0.0, sy]], dtype=np.float64)
    skew = np.array([[1.0, skew_x], [skew_y, 1.0]], dtype=np.float64)
    rotation = np.array(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]],
        dtype=np.float64,
    )
    matrix = rotation @ skew @ scale
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise RenderingError("Layer transform is not invertible") from exc

    yy, xx = np.indices((height, width), dtype=np.float64)
    coordinates = np.stack(
        (xx - float(transform.tx), yy - float(transform.ty)),
        axis=-1,
    )
    source = coordinates @ inverse.T
    source_x = np.rint(source[..., 0]).astype(np.int64)
    source_y = np.rint(source[..., 1]).astype(np.int64)
    valid = (
        (source_x >= 0)
        & (source_x < arr.shape[1])
        & (source_y >= 0)
        & (source_y < arr.shape[0])
    )
    output = np.zeros((height, width, arr.shape[2]), dtype=np.uint8)
    output[valid] = arr[source_y[valid], source_x[valid]]
    return output


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
        # Flatten transparency onto white before converting to JPEG. Simply
        # dropping alpha turns transparent pixels black in the post-edit
        # preview, even though the underlying crop data is intact.
        if arr.ndim == 3 and arr.shape[2] == 4:
            rgba = arr.astype(np.float32)
            alpha = rgba[:, :, 3:4] / 255.0
            background = np.full_like(rgba[:, :, :3], 255.0)
            rgb = np.round(
                rgba[:, :, :3] * alpha + background * (1.0 - alpha)
            ).astype(np.uint8)
        else:
            rgb = arr
        img = PilImage.fromarray(rgb.astype(np.uint8), "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    # Fallback PPM
    if arr.ndim == 3 and arr.shape[2] == 4:
        rgba = arr.astype(np.float32)
        alpha = rgba[:, :, 3:4] / 255.0
        background = np.full_like(rgba[:, :, :3], 255.0)
        rgb = np.round(
            rgba[:, :, :3] * alpha + background * (1.0 - alpha)
        ).astype(np.uint8)
    else:
        rgb = arr
    h, w = rgb.shape[:2]
    header = f"P6\n{w} {h}\n255\n".encode("ascii")
    return header + rgb.astype(np.uint8).tobytes()


def _encode_png(arr: np.ndarray) -> bytes:
    """Encode a rendered preview losslessly, preserving color and alpha."""
    if _PILLOW_AVAILABLE:
        from PIL import Image as PilImage  # type: ignore[import-untyped]

        if arr.ndim == 3 and arr.shape[2] == 4:
            image = PilImage.fromarray(arr.astype(np.uint8), "RGBA")
        elif arr.ndim == 3 and arr.shape[2] == 3:
            image = PilImage.fromarray(arr.astype(np.uint8), "RGB")
        else:
            image = PilImage.fromarray(arr.astype(np.uint8), "L")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    # PPM is the existing dependency-free fallback; flatten alpha first.
    if arr.ndim == 3 and arr.shape[2] == 4:
        rgba = arr.astype(np.float32)
        alpha = rgba[:, :, 3:4] / 255.0
        background = np.full_like(rgba[:, :, :3], 255.0)
        rgb = np.round(
            rgba[:, :, :3] * alpha + background * (1.0 - alpha)
        ).astype(np.uint8)
    elif arr.ndim == 3:
        rgb = arr[:, :, :3]
    else:
        rgb = np.repeat(arr[:, :, None], 3, axis=2)
    h, w = rgb.shape[:2]
    header = f"P6\n{w} {h}\n255\n".encode("ascii")
    return header + rgb.astype(np.uint8).tobytes()


def _blank_jpeg(w: int, h: int) -> bytes:
    arr = np.full((h, w, 3), 200, dtype=np.uint8)
    return _encode_jpeg(arr)
