"""Unit tests for layer advancements: layer from selection, crop document, blend modes, lock, merge down, and duplication with CoW."""
from __future__ import annotations

import numpy as np

from dip_studio.application.editor import EditorController
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.rendering.ports import BlankDocumentRenderer


def _setup_controller() -> tuple[EditorController, ImageDataStore]:
    store = ImageDataStore()
    controller = EditorController(
        renderer=BlankDocumentRenderer(),
        data_store=store,
    )
    doc = controller.create_document("TestDoc", 20, 20)
    # Put a known 20x20 test array in the base layer
    arr = np.full((20, 20, 4), 100, dtype=np.uint8)
    arr[:, :, 3] = 255
    buf_id = store.allocate(arr)
    # Assign to first layer
    layer_id = doc.layers[0].id
    controller.set_layer_visibility(layer_id, True)
    # Directly set buffer on layer
    from dip_studio.application.layer_commands import ChangeLayer
    controller._history_for_active().execute(
        ChangeLayer(layer_id, buffer_id=buf_id), controller._session
    )
    return controller, store


class TestLayerFromSelection:
    def test_layer_via_copy(self) -> None:
        controller, store = _setup_controller()
        doc = controller.document
        assert doc is not None
        assert len(doc.layers) == 1

        # Create selection of 5x5 at (2, 2)
        new_doc = controller.create_layer_from_selection((2, 2, 5, 5), cut=False)
        assert len(new_doc.layers) == 2

        new_layer = new_doc.layers[1]
        assert "Selection" in new_layer.name
        assert new_layer.buffer_id is not None

        # Check extracted pixels
        new_arr = store.get(new_layer.buffer_id)
        assert new_arr.shape == (20, 20, 4)
        # Inside selection rect: has pixel value 100
        assert (new_arr[2:7, 2:7, 0] == 100).all()
        # Outside selection rect: transparent (alpha == 0)
        assert (new_arr[:2, :, 3] == 0).all()
        assert (new_arr[7:, :, 3] == 0).all()

        # Source layer is untouched
        src_arr = store.get(doc.layers[0].buffer_id)  # type: ignore[arg-type]
        assert (src_arr[2:7, 2:7, 0] == 100).all()

    def test_layer_via_cut(self) -> None:
        controller, store = _setup_controller()
        doc = controller.document
        assert doc is not None
        src_id = doc.layers[0].id

        # Cut selection
        new_doc = controller.create_layer_from_selection((2, 2, 5, 5), layer_id=src_id, cut=True)
        assert len(new_doc.layers) == 2

        # Source layer has the region cleared to 0
        src_layer = next(l for l in new_doc.layers if l.id == src_id)
        assert src_layer.buffer_id is not None
        src_arr = store.get(src_layer.buffer_id)
        assert (src_arr[2:7, 2:7] == 0).all()


class TestCropDocument:
    def test_crop_document_dimensions_and_buffers(self) -> None:
        controller, store = _setup_controller()
        doc = controller.document
        assert doc is not None
        assert doc.image.width == 20
        assert doc.image.height == 20

        # Crop from (5, 5) to width=10, height=8
        cropped_doc = controller.crop_document(5, 5, 10, 8)
        assert cropped_doc.image.width == 10
        assert cropped_doc.image.height == 8

        layer = cropped_doc.layers[0]
        assert layer.buffer_id is not None
        arr = store.get(layer.buffer_id)
        assert arr.shape == (8, 10, 4)


class TestLayerMergeDown:
    def test_merge_down_layers(self) -> None:
        controller, store = _setup_controller()
        # Add a second layer with green content
        new_doc = controller.add_layer("Layer 2")
        top_id = new_doc.layers[1].id
        green_arr = np.zeros((20, 20, 4), dtype=np.uint8)
        green_arr[:, :, 1] = 200  # green
        green_arr[:, :, 3] = 255  # opaque
        buf_green = store.allocate(green_arr)
        from dip_studio.application.layer_commands import ChangeLayer
        controller._history_for_active().execute(
            ChangeLayer(top_id, buffer_id=buf_green, opacity=0.5), controller._session
        )

        assert len(controller.document.layers) == 2
        merged_doc = controller.merge_down(top_id)
        assert len(merged_doc.layers) == 1

        merged_buf = merged_doc.layers[0].buffer_id
        assert merged_buf is not None
        merged_arr = store.get(merged_buf)
        assert merged_arr.shape == (20, 20, 4)


class TestLayerProperties:
    def test_set_blend_mode_preserves_buffer(self) -> None:
        controller, store = _setup_controller()
        doc = controller.document
        assert doc is not None
        orig_buf = doc.layers[0].buffer_id
        assert orig_buf is not None

        updated_doc = controller.set_layer_blend_mode(doc.layers[0].id, "multiply")
        assert updated_doc.layers[0].blend_mode == "multiply"
        assert updated_doc.layers[0].buffer_id == orig_buf

    def test_set_locked_preserves_buffer(self) -> None:
        controller, store = _setup_controller()
        doc = controller.document
        assert doc is not None
        orig_buf = doc.layers[0].buffer_id
        assert orig_buf is not None

        updated_doc = controller.set_layer_locked(doc.layers[0].id, True)
        assert updated_doc.layers[0].locked is True
        assert updated_doc.layers[0].buffer_id == orig_buf

    def test_duplicate_layer_copies_buffer(self) -> None:
        controller, store = _setup_controller()
        doc = controller.document
        assert doc is not None
        orig_buf = doc.layers[0].buffer_id
        assert orig_buf is not None

        dup_doc = controller.duplicate_layer(doc.layers[0].id)
        assert len(dup_doc.layers) == 2
        dup_buf = dup_doc.layers[1].buffer_id
        assert dup_buf is not None
        assert dup_buf != orig_buf  # distinct CoW buffer
        # Verify content is identical
        assert np.array_equal(store.get(orig_buf), store.get(dup_buf))
