"""Tests for toolbar and interactive tool processors: Transform, Analysis, and Bridge processors."""
from __future__ import annotations

import numpy as np

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors.analysis import (
    SegmentationProcessor,
    ThresholdProcessor,
)
from dip_studio.processing.processors.tools import (
    BlurToolProcessor,
    EdgeToolProcessor,
    MorphologyToolProcessor,
)
from dip_studio.processing.processors.transform import (
    CropProcessor,
    FlipProcessor,
    RotateProcessor,
)


def _req(op: str, **params: object) -> ProcessingRequest:
    return ProcessingRequest(op, tuple((k, str(v)) for k, v in sorted(params.items())))


class TestTransformProcessors:
    def test_rotate_90_cw(self) -> None:
        store = ImageDataStore()
        # 4 rows, 2 cols
        arr = np.arange(8, dtype=np.uint8).reshape(4, 2)
        buf = store.allocate(arr)
        out_buf = RotateProcessor(store).process(buf, _req("rotate", degrees=90))
        out = store.get(out_buf)
        assert out.shape == (2, 4)

    def test_rotate_180(self) -> None:
        store = ImageDataStore()
        arr = np.array([[1, 2], [3, 4]], dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = RotateProcessor(store).process(buf, _req("rotate", degrees=180))
        out = store.get(out_buf)
        assert out[0, 0] == 4
        assert out[1, 1] == 1

    def test_flip_horizontal(self) -> None:
        store = ImageDataStore()
        arr = np.array([[10, 20], [30, 40]], dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = FlipProcessor(store).process(buf, _req("flip", direction="horizontal"))
        out = store.get(out_buf)
        assert out[0, 0] == 20
        assert out[0, 1] == 10

    def test_flip_vertical(self) -> None:
        store = ImageDataStore()
        arr = np.array([[10, 20], [30, 40]], dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = FlipProcessor(store).process(buf, _req("flip", direction="vertical"))
        out = store.get(out_buf)
        assert out[0, 0] == 30
        assert out[1, 0] == 10

    def test_crop(self) -> None:
        store = ImageDataStore()
        arr = np.arange(100, dtype=np.uint8).reshape(10, 10)
        buf = store.allocate(arr)
        out_buf = CropProcessor(store).process(buf, _req("crop", x=2, y=2, width=4, height=3))
        out = store.get(out_buf)
        assert out.shape == (3, 4)
        assert out[0, 0] == arr[2, 2]


class TestAnalysisProcessors:
    def test_threshold_binary(self) -> None:
        store = ImageDataStore()
        arr = np.array([[50, 150], [200, 30]], dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = ThresholdProcessor(store).process(
            buf, _req("threshold", method="Binary", threshold_value=100)
        )
        out = store.get(out_buf)
        assert out[0, 0] == 0
        assert out[0, 1] == 255
        assert out[1, 0] == 255
        assert out[1, 1] == 0

    def test_threshold_otsu(self) -> None:
        store = ImageDataStore()
        # Bimodal distribution
        arr = np.zeros((10, 10), dtype=np.uint8)
        arr[5:, :] = 200
        buf = store.allocate(arr)
        out_buf = ThresholdProcessor(store).process(buf, _req("threshold", method="Otsu"))
        out = store.get(out_buf)
        assert (out[:5, :] == 0).all()
        assert (out[5:, :] == 255).all()

    def test_segmentation(self) -> None:
        store = ImageDataStore()
        arr = np.arange(256, dtype=np.uint8).reshape(16, 16)
        buf = store.allocate(arr)
        out_buf = SegmentationProcessor(store).process(buf, _req("segment", clusters=4))
        out = store.get(out_buf)
        unique_vals = len(np.unique(out))
        assert unique_vals <= 4


class TestToolBridgeProcessors:
    def test_blur_tool_gaussian(self) -> None:
        store = ImageDataStore()
        arr = np.full((12, 12, 3), 100, dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = BlurToolProcessor(store).process(
            buf, _req("blur", radius=2.0, method="Gaussian")
        )
        out = store.get(out_buf)
        assert out.shape == arr.shape

    def test_blur_tool_median(self) -> None:
        store = ImageDataStore()
        arr = np.full((10, 10, 3), 150, dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = BlurToolProcessor(store).process(buf, _req("blur", radius=1.0, method="Median"))
        out = store.get(out_buf)
        assert out.shape == arr.shape

    def test_edge_tool_automatic(self) -> None:
        store = ImageDataStore()
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        arr[:, 5:, :] = 255
        buf = store.allocate(arr)
        out_buf = EdgeToolProcessor(store).process(buf, _req("edge", automatic="True"))
        out = store.get(out_buf)
        assert out.shape == arr.shape

    def test_morphology_tool_erode(self) -> None:
        store = ImageDataStore()
        arr = np.full((8, 8, 3), 200, dtype=np.uint8)
        buf = store.allocate(arr)
        out_buf = MorphologyToolProcessor(store).process(
            buf, _req("morphology", operation="Erode", kernel_size=3)
        )
        out = store.get(out_buf)
        assert out.shape == arr.shape
