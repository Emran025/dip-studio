"""Tests for processing registry — build_processing_engine wiring."""

from __future__ import annotations

import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.registry import build_processing_engine


def _req(op: str, **params: object) -> ProcessingRequest:
    return ProcessingRequest(op, tuple((k, str(v)) for k, v in sorted(params.items())))


class TestBuildProcessingEngine:
    def test_engine_built_successfully(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        assert engine is not None

    def test_negative_registered(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.full((4, 4, 3), 100, dtype=np.uint8)
        buf = store.allocate(arr)
        out_id = engine.run(buf, _req("negative"))
        out = store.get(out_id)
        assert out[0, 0, 0] == 155

    def test_gaussian_blur_registered(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.full((8, 8, 3), 128, dtype=np.uint8)
        buf = store.allocate(arr)
        out_id = engine.run(buf, _req("gaussian_blur", kernel_size=3, sigma=1.0))
        out = store.get(out_id)
        assert out.shape == (8, 8, 3)

    def test_unknown_operation_raises(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        buf = store.allocate(arr)
        with pytest.raises(KeyError):
            engine.run(buf, _req("nonexistent_op"))

    def test_histogram_equalization_registered(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, axis=2)
        buf = store.allocate(arr)
        out_id = engine.run(buf, _req("histogram_equalization"))
        out = store.get(out_id)
        assert out.shape == arr.shape

    def test_grayscale_registered(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.array([[[255, 0, 0]]], dtype=np.uint8)
        buf = store.allocate(arr)
        out_id = engine.run(buf, _req("grayscale"))
        out = store.get(out_id)
        assert out[0, 0, 0] == out[0, 0, 1] == out[0, 0, 2]

    def test_sobel_registered(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        arr[:, 5:, :] = 255
        buf = store.allocate(arr)
        out_id = engine.run(buf, _req("sobel"))
        out = store.get(out_id)
        assert out.shape == (10, 10, 3)

    def test_erode_registered(self) -> None:
        store = ImageDataStore()
        engine = build_processing_engine(store)
        arr = np.full((6, 6, 3), 255, dtype=np.uint8)
        buf = store.allocate(arr)
        out_id = engine.run(buf, _req("erode", kernel_size=3))
        out = store.get(out_id)
        assert out.shape == (6, 6, 3)
