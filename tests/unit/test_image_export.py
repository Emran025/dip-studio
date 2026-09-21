"""Tests for ImageExporter and CompositeExporter infrastructure adapters."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dip_studio.infrastructure.image_export import CompositeExporter, ImageExporter


@pytest.fixture()
def rgb_image() -> np.ndarray:
    """3-channel (H, W, 3) RGB uint8 test image."""
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    arr[:4, :, 0] = 200   # red top half
    arr[4:, :, 1] = 180   # green bottom half
    return arr


@pytest.fixture()
def rgba_image() -> np.ndarray:
    arr = np.full((6, 6, 4), 128, dtype=np.uint8)
    arr[:, :, 3] = 200  # semi-transparent
    return arr


class TestImageExporter:
    def test_export_ppm(self, tmp_path: Path, rgb_image: np.ndarray) -> None:
        path = tmp_path / "out.ppm"
        exporter = ImageExporter()
        exporter.export(rgb_image, path)
        assert path.exists()
        content = path.read_bytes()
        assert content.startswith(b"P6\n")

    def test_export_ppm_contains_correct_dimensions(
        self, tmp_path: Path, rgb_image: np.ndarray
    ) -> None:
        path = tmp_path / "out.ppm"
        ImageExporter().export(rgb_image, path)
        content = path.read_text(errors="replace")
        header_line = content.split("\n")[1]
        assert "8 8" in header_line  # width=8, height=8

    def test_export_unsupported_extension_raises(
        self, tmp_path: Path, rgb_image: np.ndarray
    ) -> None:
        path = tmp_path / "out.xyz"
        with pytest.raises(Exception, match="Unsupported"):
            ImageExporter().export(rgb_image, path)

    def test_export_rgba_to_ppm_drops_alpha(
        self, tmp_path: Path, rgba_image: np.ndarray
    ) -> None:
        path = tmp_path / "out.ppm"
        ImageExporter().export(rgba_image, path)
        assert path.exists()


class TestImageExporterWithPillow:
    """Only runs if Pillow is installed."""

    @pytest.fixture(autouse=True)
    def _pillow_guard(self) -> None:
        import importlib.util
        if not importlib.util.find_spec("PIL"):
            pytest.skip("Pillow not installed")

    def test_export_png(self, tmp_path: Path, rgb_image: np.ndarray) -> None:
        path = tmp_path / "out.png"
        ImageExporter().export(rgb_image, path)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_export_jpeg(self, tmp_path: Path, rgb_image: np.ndarray) -> None:
        path = tmp_path / "out.jpg"
        ImageExporter().export(rgb_image, path, quality=80)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_export_jpeg_drops_alpha(self, tmp_path: Path, rgba_image: np.ndarray) -> None:
        """JPEG doesn't support alpha; exporter must drop it without error."""
        path = tmp_path / "out.jpg"
        ImageExporter().export(rgba_image, path, quality=85)
        assert path.exists()

    def test_export_bmp(self, tmp_path: Path, rgb_image: np.ndarray) -> None:
        path = tmp_path / "out.bmp"
        ImageExporter().export(rgb_image, path)
        assert path.exists()


class TestCompositeExporter:
    """Tests for CompositeExporter which decodes composite bytes then re-exports."""

    @pytest.fixture(autouse=True)
    def _pillow_guard(self) -> None:
        import importlib.util
        if not importlib.util.find_spec("PIL"):
            pytest.skip("Pillow not installed")

    def _make_ppm_bytes(self, w: int = 4, h: int = 4) -> bytes:
        arr = np.full((h, w, 3), 100, dtype=np.uint8)
        header = f"P6\n{w} {h}\n255\n".encode("ascii")
        return header + arr.tobytes()

    def _make_jpeg_bytes(self, w: int = 4, h: int = 4) -> bytes:
        from PIL import Image as PilImage  # type: ignore[import-untyped]
        import io
        arr = np.full((h, w, 3), 100, dtype=np.uint8)
        img = PilImage.fromarray(arr, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def test_export_from_ppm_bytes_to_png(self, tmp_path: Path) -> None:
        composite = self._make_ppm_bytes()
        path = tmp_path / "out.png"
        CompositeExporter().export_document(composite, path)
        assert path.exists()

    def test_export_from_jpeg_bytes_to_jpeg(self, tmp_path: Path) -> None:
        composite = self._make_jpeg_bytes()
        path = tmp_path / "out.jpg"
        CompositeExporter().export_document(composite, path, quality=70)
        assert path.exists()

    def test_export_from_jpeg_bytes_to_png(self, tmp_path: Path) -> None:
        composite = self._make_jpeg_bytes()
        path = tmp_path / "out.png"
        CompositeExporter().export_document(composite, path)
        assert path.exists()
