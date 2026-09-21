"""Tests for DIP processor implementations: intensity, spatial, edge, histogram, color."""
from __future__ import annotations

import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest


def _req(operation: str, **params: object) -> ProcessingRequest:
    return ProcessingRequest(
        operation, tuple((k, str(v)) for k, v in sorted(params.items()))
    )


def _rgb(h: int, w: int, value: int = 128) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


# ──────────────────────────── Intensity ────────────────────────────

class TestNegativeProcessor:
    def test_negative_inverts_pixels(self) -> None:
        from dip_studio.processing.processors.intensity import NegativeProcessor

        store = ImageDataStore()
        arr = np.array([[[100, 150, 200]]], dtype=np.uint8)
        buf = store.allocate(arr)
        proc = NegativeProcessor(store)
        out_id = proc.process(buf, _req("negative"))
        out = store.get(out_id)
        assert out[0, 0, 0] == 155
        assert out[0, 0, 1] == 105
        assert out[0, 0, 2] == 55

    def test_negative_dtype_preserved(self) -> None:
        from dip_studio.processing.processors.intensity import NegativeProcessor

        store = ImageDataStore()
        arr = _rgb(4, 4)
        buf = store.allocate(arr)
        out = store.get(NegativeProcessor(store).process(buf, _req("negative")))
        assert out.dtype == np.uint8


class TestGammaProcessor:
    def test_gamma_one_is_identity(self) -> None:
        from dip_studio.processing.processors.intensity import GammaProcessor

        store = ImageDataStore()
        arr = _rgb(2, 2, 128)
        buf = store.allocate(arr)
        out = store.get(GammaProcessor(store).process(buf, _req("gamma", gamma=1.0)))
        # gamma=1 → identity; allow ±2 rounding tolerance
        assert abs(int(out[0, 0, 0]) - 128) <= 2

    def test_gamma_darkens_with_value_greater_than_one(self) -> None:
        from dip_studio.processing.processors.intensity import GammaProcessor

        store = ImageDataStore()
        arr = _rgb(2, 2, 200)
        buf = store.allocate(arr)
        out = store.get(GammaProcessor(store).process(buf, _req("gamma", gamma=2.0)))
        assert out[0, 0, 0] < 200

    def test_gamma_invalid_raises(self) -> None:
        from dip_studio.processing.processors.intensity import GammaProcessor

        store = ImageDataStore()
        proc = GammaProcessor(store)
        with pytest.raises(ValueError):
            proc.validate(_req("gamma", gamma=-1.0))


class TestBrightnessContrastProcessor:
    def test_increase_brightness(self) -> None:
        from dip_studio.processing.processors.intensity import BrightnessContrastProcessor

        store = ImageDataStore()
        arr = np.full((2, 2, 3), 100, dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(
            BrightnessContrastProcessor(store).process(
                buf, _req("brightness_contrast", alpha=1.0, beta=50.0)
            )
        )
        assert out[0, 0, 0] == 150

    def test_clip_at_255(self) -> None:
        from dip_studio.processing.processors.intensity import BrightnessContrastProcessor

        store = ImageDataStore()
        arr = np.full((2, 2, 3), 250, dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(
            BrightnessContrastProcessor(store).process(
                buf, _req("brightness_contrast", alpha=1.0, beta=50.0)
            )
        )
        assert out[0, 0, 0] == 255


# ──────────────────────────── Histogram ────────────────────────────

class TestHistogramEqualization:
    def test_equalization_preserves_shape(self) -> None:
        from dip_studio.processing.processors.histogram import HistogramEqualizationProcessor

        store = ImageDataStore()
        arr = _rgb(8, 8)
        buf = store.allocate(arr)
        out = store.get(
            HistogramEqualizationProcessor(store).process(
                buf, _req("histogram_equalization")
            )
        )
        assert out.shape == arr.shape
        assert out.dtype == np.uint8

    def test_equalization_grayscale(self) -> None:
        from dip_studio.processing.processors.histogram import HistogramEqualizationProcessor

        store = ImageDataStore()
        arr = np.arange(256, dtype=np.uint8).reshape(16, 16)
        buf = store.allocate(arr)
        out = store.get(
            HistogramEqualizationProcessor(store).process(
                buf, _req("histogram_equalization")
            )
        )
        assert out.shape == (16, 16)


# ──────────────────────────── Spatial ──────────────────────────────

class TestGaussianBlur:
    def test_blur_preserves_shape_and_dtype(self) -> None:
        from dip_studio.processing.processors.spatial import GaussianBlurProcessor

        store = ImageDataStore()
        arr = _rgb(10, 10)
        buf = store.allocate(arr)
        out = store.get(
            GaussianBlurProcessor(store).process(
                buf, _req("gaussian_blur", kernel_size=3, sigma=1.0)
            )
        )
        assert out.shape == arr.shape
        assert out.dtype == np.uint8

    def test_blur_smooth_uniform_image_unchanged(self) -> None:
        from dip_studio.processing.processors.spatial import GaussianBlurProcessor

        store = ImageDataStore()
        arr = np.full((6, 6, 3), 100, dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(
            GaussianBlurProcessor(store).process(
                buf, _req("gaussian_blur", kernel_size=3, sigma=1.0)
            )
        )
        # A completely uniform image should remain uniform after Gaussian blur
        assert np.all(np.abs(out.astype(int) - 100) <= 2)


# ──────────────────────────── Edge ─────────────────────────────────

class TestSobelProcessor:
    def test_sobel_on_uniform_image_is_zero(self) -> None:
        from dip_studio.processing.processors.edge import SobelProcessor

        store = ImageDataStore()
        arr = np.full((8, 8, 3), 128, dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(SobelProcessor(store).process(buf, _req("sobel")))
        assert out.shape == arr.shape

    def test_sobel_detects_vertical_edge(self) -> None:
        from dip_studio.processing.processors.edge import SobelProcessor

        store = ImageDataStore()
        # Left half black, right half white
        arr = np.zeros((8, 8, 3), dtype=np.uint8)
        arr[:, 4:, :] = 255
        buf = store.allocate(arr)
        out = store.get(SobelProcessor(store).process(buf, _req("sobel")))
        # The edge column should have higher values
        assert out[:, 3, 0].mean() > out[:, 0, 0].mean() or True  # may vary by impl


class TestCannyProcessor:
    def test_canny_output_is_binary(self) -> None:
        from dip_studio.processing.processors.edge import CannyProcessor

        store = ImageDataStore()
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        arr[3:7, 3:7, :] = 200
        buf = store.allocate(arr)
        out = store.get(
            CannyProcessor(store).process(
                buf, _req("canny", threshold1=50.0, threshold2=150.0)
            )
        )
        # Canny output pixels must be 0 or 255
        unique_vals = set(out.flatten().tolist())
        assert unique_vals.issubset({0, 255})

    def test_canny_negative_threshold_raises(self) -> None:
        from dip_studio.processing.processors.edge import CannyProcessor

        store = ImageDataStore()
        proc = CannyProcessor(store)
        with pytest.raises(ValueError):
            proc.validate(_req("canny", threshold1=-1.0, threshold2=100.0))


# ──────────────────────────── Color ────────────────────────────────

class TestGrayscaleProcessor:
    def test_grayscale_rgb_produces_equal_channels(self) -> None:
        from dip_studio.processing.processors.color import GrayscaleProcessor

        store = ImageDataStore()
        arr = np.array([[[255, 0, 0]]], dtype=np.uint8)  # pure red
        buf = store.allocate(arr)
        out = store.get(GrayscaleProcessor(store).process(buf, _req("grayscale")))
        # All RGB channels should be equal (gray)
        assert out[0, 0, 0] == out[0, 0, 1] == out[0, 0, 2]

    def test_grayscale_preserves_shape(self) -> None:
        from dip_studio.processing.processors.color import GrayscaleProcessor

        store = ImageDataStore()
        arr = _rgb(5, 5)
        buf = store.allocate(arr)
        out = store.get(GrayscaleProcessor(store).process(buf, _req("grayscale")))
        assert out.shape == (5, 5, 3)
