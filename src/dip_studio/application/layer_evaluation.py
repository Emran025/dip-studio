"""Compatibility shim for layer evaluation.

The concrete implementation lives in the rendering layer to honor DIP Studio's
architecture boundaries, while existing imports continue to work.
"""
from __future__ import annotations

from dip_studio.rendering.layer_evaluation import (
    LayerEvaluationService,
    _apply_adjustment_layer,
    _compose,
    _find_param,
    _to_rgba,
)

__all__ = [
    "LayerEvaluationService",
    "_apply_adjustment_layer",
    "_compose",
    "_find_param",
    "_to_rgba",
]
