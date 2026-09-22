"""Evaluation helpers for document stacks, group containers and adjustment layers."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import numpy as np

from dip_studio.core.errors import RenderingError
from dip_studio.domain.model import AdjustmentLayer, FilterLayer, GroupLayer

if TYPE_CHECKING:
    from dip_studio.domain.model import Layer


def _find_param(params: tuple[tuple[str, str], ...], key: str, default: str = "") -> str:
    values = dict(params)
    if key in values:
        return str(values[key])
    lowered = key.lower()
    for name, value in values.items():
        if name.lower() == lowered:
            return str(value)
    return default


def _apply_adjustment_layer(array: np.ndarray, layer: AdjustmentLayer | FilterLayer) -> np.ndarray:
    operation = getattr(layer, "effective_operation", layer.adjustment_type) or ""
    params = getattr(layer, "effective_parameters", layer.adjustment_params) or ()
    if not operation:
        raise RenderingError("Adjustment layer has no operation")

    rgba = array.astype(np.uint8)
    if rgba.ndim == 2:
        rgba = np.stack([rgba, rgba, rgba, np.full_like(rgba, 255)], axis=-1)
    elif rgba.shape[-1] == 3:
        alpha = np.full((*rgba.shape[:2], 1), 255, dtype=np.uint8)
        rgba = np.concatenate([rgba, alpha], axis=-1)
    elif rgba.shape[-1] != 4:
        raise RenderingError(f"Adjustment layer '{layer.name}' cannot operate on non-RGBA data")

    if operation == "grayscale":
        gray = (0.299 * rgba[:, :, 0] + 0.587 * rgba[:, :, 1] + 0.114 * rgba[:, :, 2]).astype(np.uint8)
        result = np.stack([gray, gray, gray], axis=-1)
        return np.concatenate([result, rgba[:, :, 3:4]], axis=-1)

    if operation == "brightness_contrast":
        alpha = float(_find_param(params, "alpha", "1.0"))
        beta = float(_find_param(params, "beta", "0.0"))
        return np.clip(rgba.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)

    if operation == "negative":
        return (255 - rgba).clip(0, 255).astype(np.uint8)

    if operation == "gamma":
        gamma = float(_find_param(params, "gamma", "1.0"))
        adjusted = np.power(np.clip(rgba.astype(np.float32) / 255.0, 0.0, 1.0), gamma)
        return (adjusted * 255.0).clip(0, 255).astype(np.uint8)

    if operation == "log_transform":
        c = float(_find_param(params, "c", "1.0"))
        transformed = c * np.log1p(rgba.astype(np.float32))
        max_val = float(transformed.max())
        if max_val > 0:
            transformed = transformed / max_val * 255.0
        return transformed.clip(0, 255).astype(np.uint8)

    if operation == "hue_saturation":
        sat_scale = float(_find_param(params, "saturation_scale", "1.0"))
        lightness_offset = float(_find_param(params, "lightness_offset", "0"))
        rgb = rgba[:, :, :3].astype(np.float32)
        gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
        gray3 = np.stack([gray, gray, gray], axis=-1)
        adjusted = np.clip((rgb - gray3) * sat_scale + gray3 + lightness_offset, 0, 255)
        result = adjusted.astype(np.uint8)
        if rgba.shape[-1] == 4:
            result = np.concatenate([result, rgba[:, :, 3:4]], axis=-1)
        return result.astype(np.uint8)

    raise RenderingError(f"Unsupported adjustment operation '{operation}'")


class LayerEvaluationService:
    """Deterministic evaluation of layer stacks including nested groups."""

    def __init__(self, buffer_reader: Callable[[str], np.ndarray] | None = None) -> None:
        self._buffer_reader = buffer_reader

    def evaluate(
        self,
        layers: Iterable["Layer"],
        *,
        buffer_reader: Callable[[str], np.ndarray] | None = None,
        active: set[object] | None = None,
    ) -> np.ndarray | None:
        read = self._buffer_reader if buffer_reader is None else buffer_reader
        active = set() if active is None else active
        result: np.ndarray | None = None
        ordered = tuple(layers)
        for layer in ordered:
            if layer.id in active:
                raise RenderingError(f"Layer cycle detected at '{layer.name}'")
            if not getattr(layer, "visible", True):
                continue
            if isinstance(layer, GroupLayer):
                active.add(layer.id)
                child_layers = tuple(
                    candidate
                    for child_id in reversed(getattr(layer, "children", ()))
                    for candidate in ordered
                    if getattr(candidate, "id", None) == child_id
                )
                child_result = self.evaluate(child_layers, buffer_reader=read, active=active)
                active.remove(layer.id)
                if child_result is None:
                    continue
                if getattr(layer, "pass_through", True):
                    if result is None:
                        result = child_result
                    else:
                        result = _compose(result, child_result, getattr(layer, "blend_mode", "normal") or "normal")
                    continue
                if getattr(layer, "opacity", 1.0) < 1.0:
                    child_result = child_result.copy()
                    child_result[:, :, 3] = (child_result[:, :, 3] * float(layer.opacity)).astype(np.uint8)
                if result is None:
                    result = child_result
                else:
                    result = _compose(result, child_result, getattr(layer, "blend_mode", "normal") or "normal")
                continue
            if isinstance(layer, (AdjustmentLayer, FilterLayer)):
                if result is not None:
                    result = _apply_adjustment_layer(result, layer)
                continue
            buffer_id = getattr(layer, "buffer_id", None)
            if buffer_id is None or read is None:
                continue
            source = read(buffer_id)
            image = _to_rgba(source)
            if getattr(layer, "opacity", 1.0) < 1.0:
                image = image.copy()
                image[:, :, 3] = (image[:, :, 3] * float(layer.opacity)).astype(np.uint8)
            if result is None:
                result = image
            else:
                result = _compose(result, image, getattr(layer, "blend_mode", "normal") or "normal")
        return result


def _to_rgba(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        rgba = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
    elif arr.shape[-1] == 3:
        alpha = np.full((*arr.shape[:2], 1), 255, dtype=arr.dtype)
        rgba = np.concatenate([arr, alpha], axis=-1)
    else:
        rgba = arr
    return rgba.astype(np.uint8)


def _compose(base: np.ndarray | None, overlay: np.ndarray, blend_mode: str) -> np.ndarray:
    if base is None:
        return overlay.astype(np.float32)
    base_f = base.astype(np.float32) / 255.0
    over_f = overlay.astype(np.float32) / 255.0
    a_o = over_f[:, :, 3:4]
    a_b = base_f[:, :, 3:4]
    base_rgb = base_f[:, :, :3]
    over_rgb = over_f[:, :, :3]
    blended = over_rgb if blend_mode == "normal" else base_rgb
    if blend_mode == "multiply":
        blended = base_rgb * over_rgb
    elif blend_mode == "screen":
        blended = 1.0 - (1.0 - base_rgb) * (1.0 - over_rgb)
    a_out = a_o + a_b * (1.0 - a_o)
    denom = np.where(a_out > 0, a_out, 1.0)
    rgb_out = (blended * a_o + base_rgb * a_b * (1.0 - a_o)) / denom
    return np.concatenate([rgb_out * 255.0, a_out * 255.0], axis=-1).astype(np.uint8)
