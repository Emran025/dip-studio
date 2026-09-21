"""Integration test for rendering compositor."""
from __future__ import annotations

import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.rendering.compositor import NumpyDocumentRenderer, _alpha_composite, _encode_jpeg, _to_rgba


class TestAlphaComposite:
    def test_opaque_overlay_replaces_base(self) -> None:
        base = np.zeros((2, 2, 4), dtype=np.float32)
        overlay = np.full((2, 2, 4), 255, dtype=np.float32)
        result = _alpha_composite(base, overlay)
        assert result[0, 0, 3] > 200  # fully opaque

    def test_transparent_overlay_preserves_base(self) -> None:
        base = np.full((2, 2, 4), [100, 100, 100, 255], dtype=np.float32)
        overlay = np.zeros((2, 2, 4), dtype=np.float32)  # fully transparent
        result = _alpha_composite(base, overlay)
        assert abs(result[0, 0, 0] - 100) < 5


class TestToRgba:
    def test_grayscale_to_rgba(self) -> None:
        arr = np.full((3, 3), 128, dtype=np.uint8)
        result = _to_rgba(arr)
        assert result.shape == (3, 3, 4)
        assert result[0, 0, 3] == 255

    def test_rgb_to_rgba(self) -> None:
        arr = np.zeros((3, 3, 3), dtype=np.uint8)
        result = _to_rgba(arr)
        assert result.shape == (3, 3, 4)

    def test_rgba_passthrough(self) -> None:
        arr = np.zeros((3, 3, 4), dtype=np.uint8)
        result = _to_rgba(arr)
        assert result.shape == (3, 3, 4)


class TestEncodeJpeg:
    def test_encode_jpeg_returns_bytes(self) -> None:
        arr = np.full((10, 10, 3), 200, dtype=np.uint8)
        result = _encode_jpeg(arr)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_rgba_drops_alpha(self) -> None:
        arr = np.zeros((10, 10, 4), dtype=np.uint8)
        result = _encode_jpeg(arr)
        assert isinstance(result, bytes)


class TestNumpyDocumentRenderer:
    def test_render_without_document_returns_blank(self) -> None:
        from unittest.mock import MagicMock
        controller = MagicMock()
        controller.document = None
        from dip_studio.rendering.ports import RenderRequest
        renderer = NumpyDocumentRenderer(controller)
        result = renderer.render(RenderRequest("doc1", 100, 100, 1.0))
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_render_invalid_viewport_raises(self) -> None:
        from unittest.mock import MagicMock
        controller = MagicMock()
        from dip_studio.rendering.ports import RenderRequest
        renderer = NumpyDocumentRenderer(controller)
        with pytest.raises(ValueError):
            renderer.render(RenderRequest("doc1", 0, 100, 1.0))
