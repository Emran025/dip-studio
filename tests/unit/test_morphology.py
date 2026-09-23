"""Tests for morphological processors."""
import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors.morphology import (
    DilateProcessor,
    ErodeProcessor,
    MorphCloseProcessor,
    MorphOpenProcessor,
)


def _req(op: str, **params: object) -> ProcessingRequest:
    return ProcessingRequest(op, tuple((k, str(v)) for k, v in sorted(params.items())))


class TestErodeProcessor:
    def test_erode_shrinks_bright_region(self) -> None:
        store = ImageDataStore()
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        arr[3:7, 3:7, :] = 255
        buf = store.allocate(arr)
        out = store.get(ErodeProcessor(store).process(buf, _req("erode", kernel_size=3)))
        assert out.shape == arr.shape
        # After erosion, bright region should be smaller or equal
        bright_pixels_before = (arr[:, :, 0] == 255).sum()
        bright_pixels_after = (out[:, :, 0] == 255).sum()
        assert bright_pixels_after <= bright_pixels_before


class TestDilateProcessor:
    def test_dilate_grows_bright_region(self) -> None:
        store = ImageDataStore()
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        arr[4:6, 4:6, :] = 255
        buf = store.allocate(arr)
        out = store.get(DilateProcessor(store).process(buf, _req("dilate", kernel_size=3)))
        bright_before = (arr[:, :, 0] == 255).sum()
        bright_after = (out[:, :, 0] == 255).sum()
        assert bright_after >= bright_before


class TestOpenClose:
    def test_open_removes_small_noise(self) -> None:
        store = ImageDataStore()
        arr = np.zeros((12, 12, 3), dtype=np.uint8)
        # Small isolated dot (noise)
        arr[1, 1, :] = 255
        # Large region
        arr[5:10, 5:10, :] = 255
        buf = store.allocate(arr)
        out = store.get(MorphOpenProcessor(store).process(buf, _req("morph_open", kernel_size=3)))
        assert out.shape == arr.shape

    def test_close_fills_small_holes(self) -> None:
        store = ImageDataStore()
        arr = np.full((12, 12, 3), 255, dtype=np.uint8)
        # Small hole
        arr[5, 5, :] = 0
        buf = store.allocate(arr)
        out = store.get(MorphCloseProcessor(store).process(buf, _req("morph_close", kernel_size=3)))
        assert out.shape == arr.shape

    @pytest.mark.parametrize(
        "processor",
        [ErodeProcessor, DilateProcessor, MorphOpenProcessor, MorphCloseProcessor],
    )
    def test_even_or_invalid_kernel_is_normalized_to_a_centered_kernel(
        self, processor: type
    ) -> None:
        store = ImageDataStore()
        arr = np.zeros((9, 9), dtype=np.uint8)
        arr[4, 4] = 255
        buf = store.allocate(arr)

        even = store.get(processor(store).process(buf, _req("morphology", kernel_size=2)))
        invalid = store.get(processor(store).process(buf, _req("morphology", kernel_size="bad")))

        assert even.shape == arr.shape
        assert invalid.shape == arr.shape
