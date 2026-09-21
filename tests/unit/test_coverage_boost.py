"""Additional coverage tests for color, edge, and compositor modules."""
from __future__ import annotations

import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest


def _req(op: str, **params: object) -> ProcessingRequest:
    return ProcessingRequest(op, tuple((k, str(v)) for k, v in sorted(params.items())))


# ─────────────── Color processors ───────────────

class TestHueSaturation:
    def test_identity_saturation(self) -> None:
        from dip_studio.processing.processors.color import HueSaturationProcessor

        store = ImageDataStore()
        arr = np.array([[[200, 100, 50]]], dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(
            HueSaturationProcessor(store).process(
                buf, _req("hue_saturation", hue_shift=0.0, lightness_offset=0.0, saturation_scale=1.0)
            )
        )
        assert out.shape == (1, 1, 3)
        assert out.dtype == np.uint8

    def test_zero_saturation_produces_gray(self) -> None:
        from dip_studio.processing.processors.color import HueSaturationProcessor

        store = ImageDataStore()
        arr = np.array([[[200, 100, 50]]], dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(
            HueSaturationProcessor(store).process(
                buf, _req("hue_saturation", hue_shift=0.0, lightness_offset=0.0, saturation_scale=0.0)
            )
        )
        # All three channels should be equal (gray)
        assert abs(int(out[0, 0, 0]) - int(out[0, 0, 1])) <= 2
        assert abs(int(out[0, 0, 1]) - int(out[0, 0, 2])) <= 2

    def test_grayscale_input_returns_rgb(self) -> None:
        from dip_studio.processing.processors.color import GrayscaleProcessor

        store = ImageDataStore()
        arr = np.full((4, 4), 128, dtype=np.uint8)  # 2D grayscale
        buf = store.allocate(arr)
        out = store.get(GrayscaleProcessor(store).process(buf, _req("grayscale")))
        assert out.ndim == 3
        assert out.shape[2] == 3

    def test_rgba_grayscale_preserves_alpha(self) -> None:
        from dip_studio.processing.processors.color import GrayscaleProcessor

        store = ImageDataStore()
        arr = np.array([[[200, 100, 50, 180]]], dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(GrayscaleProcessor(store).process(buf, _req("grayscale")))
        assert out.shape == (1, 1, 4)
        assert out[0, 0, 3] == 180


# ─────────────── Edge processors (NumPy fallback path) ───────────────

class TestLaplacianProcessor:
    def test_laplacian_uniform_image_near_zero(self) -> None:
        from dip_studio.processing.processors.edge import LaplacianProcessor

        store = ImageDataStore()
        arr = np.full((8, 8, 3), 128, dtype=np.uint8)
        buf = store.allocate(arr)
        out = store.get(LaplacianProcessor(store).process(buf, _req("laplacian")))
        assert out.shape == arr.shape
        assert out.dtype == np.uint8

    def test_laplacian_detects_sharpness(self) -> None:
        from dip_studio.processing.processors.edge import LaplacianProcessor

        store = ImageDataStore()
        # Step edge: left half dark, right half bright
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        arr[:, 5:, :] = 255
        buf = store.allocate(arr)
        out = store.get(LaplacianProcessor(store).process(buf, _req("laplacian")))
        assert out.shape == arr.shape


# ─────────────── Compositor ───────────────

class TestCompositorFull:
    def test_render_document_with_no_layers_returns_blank(self) -> None:
        from unittest.mock import MagicMock
        from dip_studio.domain.model import ImageDocument, ImageSpec, DocumentId
        from dip_studio.rendering.compositor import NumpyDocumentRenderer
        from dip_studio.rendering.ports import RenderRequest
        from uuid import uuid4

        controller = MagicMock()
        doc = ImageDocument(
            id=DocumentId(uuid4()),
            name="test",
            image=ImageSpec(width=4, height=4, color_space="RGB", bit_depth=8),
            layers=(),
        )
        controller.document = doc
        controller._data_store = None
        renderer = NumpyDocumentRenderer(controller)
        result = renderer.render(RenderRequest("doc1", 4, 4, 1.0))
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_render_document_with_layer_and_buffer(self) -> None:
        from unittest.mock import MagicMock
        from dip_studio.domain.model import ImageDocument, ImageSpec, Layer, LayerId, DocumentId
        from dip_studio.infrastructure.data_store import ImageDataStore
        from dip_studio.rendering.compositor import NumpyDocumentRenderer
        from dip_studio.rendering.ports import RenderRequest
        from uuid import uuid4

        store = ImageDataStore()
        arr = np.full((4, 4, 3), 200, dtype=np.uint8)
        buf_id = store.allocate(arr)

        layer = Layer(id=LayerId(uuid4()), name="BG", buffer_id=buf_id)
        doc = ImageDocument(
            id=DocumentId(uuid4()),
            name="test",
            image=ImageSpec(width=4, height=4, color_space="RGB", bit_depth=8),
            layers=(layer,),
        )

        controller = MagicMock()
        controller.document = doc
        # compositor reads controller.data_store — wire real store
        controller.data_store = store

        renderer = NumpyDocumentRenderer(controller)
        result = renderer.render(RenderRequest("doc1", 4, 4, 1.0))
        assert isinstance(result, bytes)
        assert len(result) > 0
