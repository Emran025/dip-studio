"""Integration test for rendering compositor."""
from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image as PilImage

from dip_studio.rendering.compositor import (
    NumpyDocumentRenderer,
    _alpha_composite,
    _encode_jpeg,
    _encode_png,
    _fit_array_to_document,
    _transform_layer,
    _to_rgba,
)
from dip_studio.domain.model import Transform


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

    def test_encode_rgba_flattens_transparency_without_blackening_preview(self) -> None:
        arr = np.zeros((10, 10, 4), dtype=np.uint8)
        result = _encode_jpeg(arr)
        assert isinstance(result, bytes)

        rendered = np.array(PilImage.open(BytesIO(result)))
        assert rendered.mean() > 240


def test_encode_png_preserves_rendered_pixels() -> None:
    arr = np.array([[[17, 93, 201, 255]]], dtype=np.uint8)
    result = _encode_png(arr)
    rendered = np.array(PilImage.open(BytesIO(result)))
    assert rendered.tolist() == [[[17, 93, 201, 255]]]


def test_fit_array_to_document_does_not_resample_pixels() -> None:
    arr = np.zeros((2, 3, 4), dtype=np.uint8)
    arr[:, :, :3] = [17, 93, 201]
    arr[:, :, 3] = 255

    fitted = _fit_array_to_document(arr, 4, 5)

    assert fitted.shape == (5, 4, 4)
    assert np.array_equal(fitted[:2, :3], arr)
    assert np.all(fitted[2:, :, 3] == 0)
    assert np.all(fitted[:, 3, 3] == 0)


def test_transform_layer_applies_translation_and_clips() -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    source[0, 0] = [10, 20, 30, 255]

    result = _transform_layer(
        source,
        Transform(tx=1.0, ty=1.0),
        width=3,
        height=3,
    )

    assert np.array_equal(result[1, 1], source[0, 0])
    assert result[0, 0, 3] == 0


def test_render_and_render_raw_share_the_same_evaluation() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from dip_studio.infrastructure.data_store import ImageDataStore
    from dip_studio.domain.model import ImageSpec, Layer
    from dip_studio.rendering.ports import RenderRequest

    store = ImageDataStore()
    buffer_id = store.allocate(np.full((2, 2, 4), [20, 40, 60, 255], dtype=np.uint8))
    document = SimpleNamespace(
        image=ImageSpec(2, 2),
        layers=(Layer(id=__import__("uuid").uuid4(), name="layer", buffer_id=buffer_id),),
    )
    controller = MagicMock(document=document, data_store=store)
    renderer = NumpyDocumentRenderer(controller)
    request = RenderRequest("doc", 2, 2, 1.0)

    raw = renderer.render_raw(request)
    encoded = np.array(PilImage.open(BytesIO(renderer.render(request))))

    assert raw is not None
    assert np.array_equal(raw, encoded)


def test_render_raises_for_missing_layer_buffer() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from dip_studio.domain.model import ImageSpec, Layer
    from dip_studio.core.errors import RenderingError
    from dip_studio.rendering.ports import RenderRequest

    document = SimpleNamespace(
        image=ImageSpec(2, 2),
        layers=(Layer(id=__import__("uuid").uuid4(), name="broken", buffer_id="missing"),),
    )
    controller = MagicMock(document=document, data_store=MagicMock())
    controller.data_store.get.side_effect = KeyError("missing")

    with pytest.raises(RenderingError, match="missing buffer"):
        NumpyDocumentRenderer(controller).render_raw(
            RenderRequest("doc", 2, 2, 1.0)
        )


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
