"""Tests for Pillow-based image import and ImageFormatRegistry."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from dip_studio.core.errors import PersistenceError
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.image_import import ImageFormatRegistry, PillowImageImporter


def _write_png(path: Path, width: int = 4, height: int = 4) -> None:
    """Write a minimal PNG file using Pillow."""
    try:
        from PIL import Image  # type: ignore[import-untyped]

        img = Image.new("RGB", (width, height), color=(255, 0, 0))
        img.save(path)
    except ImportError:
        pytest.skip("Pillow not installed")


class TestPillowImageImporter:
    def test_import_png_creates_buffer(self, tmp_path: Path) -> None:
        png_path = tmp_path / "test.png"
        _write_png(png_path)
        store = ImageDataStore()
        importer = PillowImageImporter(store)
        imported = importer.import_image(png_path)
        assert imported.buffer_id is not None
        assert store.has(imported.buffer_id)

    def test_import_png_correct_dimensions(self, tmp_path: Path) -> None:
        png_path = tmp_path / "test.png"
        _write_png(png_path, width=8, height=6)
        store = ImageDataStore()
        importer = PillowImageImporter(store)
        imported = importer.import_image(png_path)
        assert imported.spec.width == 8
        assert imported.spec.height == 6

    def test_import_png_buffer_is_ndarray(self, tmp_path: Path) -> None:
        png_path = tmp_path / "test.png"
        _write_png(png_path, width=4, height=4)
        store = ImageDataStore()
        importer = PillowImageImporter(store)
        imported = importer.import_image(png_path)
        assert imported.buffer_id is not None
        arr = store.get(imported.buffer_id)
        assert isinstance(arr, np.ndarray)
        assert arr.shape[2] in (3, 4)  # RGB or RGBA

    def test_import_produces_preview_bytes(self, tmp_path: Path) -> None:
        png_path = tmp_path / "test.png"
        _write_png(png_path)
        store = ImageDataStore()
        importer = PillowImageImporter(store)
        imported = importer.import_image(png_path)
        assert imported.preview is not None
        assert len(imported.preview) > 0

    def test_import_preview_preserves_source_resolution(self, tmp_path: Path) -> None:
        png_path = tmp_path / "large.png"
        _write_png(png_path, width=1024, height=768)
        store = ImageDataStore()
        importer = PillowImageImporter(store)

        imported = importer.import_image(png_path)

        assert imported.preview is not None
        from PIL import Image  # type: ignore[import-untyped]

        with Image.open(io.BytesIO(imported.preview)) as preview:
            assert preview.size == (1024, 768)


class TestImageFormatRegistry:
    def test_registry_routes_ppm(self, tmp_path: Path) -> None:
        ppm_path = tmp_path / "test.ppm"
        ppm_path.write_bytes(b"P6\n2 1\n255\n" + b"\xff\x00\x00\x00\xff\x00")
        store = ImageDataStore()
        registry = ImageFormatRegistry(data_store=store)
        imported = registry.import_image(ppm_path)
        assert imported.name == "test"

    def test_registry_routes_png(self, tmp_path: Path) -> None:
        png_path = tmp_path / "test.png"
        _write_png(png_path)
        store = ImageDataStore()
        registry = ImageFormatRegistry(data_store=store)
        imported = registry.import_image(png_path)
        assert imported.buffer_id is not None

    def test_registry_rejects_unknown_format(self, tmp_path: Path) -> None:
        unknown_path = tmp_path / "test.xyz"
        unknown_path.write_bytes(b"garbage")
        store = ImageDataStore()
        registry = ImageFormatRegistry(data_store=store)
        with pytest.raises(PersistenceError):
            registry.import_image(unknown_path)

    def test_registry_reports_supported_formats(self) -> None:
        registry = ImageFormatRegistry(data_store=ImageDataStore())
        formats = dict(registry.supported_formats)
        assert formats["png"] == "PNG"
        assert formats["jpg"] == "JPEG"
        assert formats["webp"] == "WebP"
        assert formats["gif"] == "GIF"
