"""Shared utilities for processor implementations."""
from __future__ import annotations

import numpy as np

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest


def _param(request: ProcessingRequest, key: str, default: str = "") -> str:
    params = dict(request.parameters)
    if key in params:
        return str(params[key])
    key_lower = key.lower()
    for k, v in params.items():
        if k.lower() == key_lower:
            return str(v)
    return default


def _to_gray(arr: np.ndarray) -> np.ndarray:
    """Convert any (H,W,C) uint8 array to (H,W) grayscale uint8."""
    if arr.ndim == 2:
        return arr
    if arr.shape[2] >= 3:
        # Luminosity formula
        return (0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]).astype(np.uint8)
    return arr[:,:,0]


def _ensure_3ch(arr: np.ndarray) -> np.ndarray:
    """Ensure array is (H,W,3) uint8 RGB."""
    if arr.ndim == 2:
        return np.stack([arr, arr, arr], axis=-1)
    if arr.shape[2] == 4:
        return arr[:,:,:3]
    return arr


class BaseProcessor:
    operation: str = ""
    
    def __init__(self, data_store: ImageDataStore) -> None:
        self._store = data_store
    
    def validate(self, request: ProcessingRequest) -> None:
        pass
    
    def process(self, buffer_id: str, request: ProcessingRequest) -> str | object:
        arr = self._store.get(buffer_id)
        result = self._apply(arr, request)
        if isinstance(result, np.ndarray):
            return self._store.allocate(result)
        return result
    
    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        raise NotImplementedError
