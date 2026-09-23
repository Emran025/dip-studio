"""Comprehensive tests for Photoshop-style crop, layer focus, and parameter handling."""

import numpy as np

from dip_studio.application.editor import EditorController
from dip_studio.domain.model import Layer
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.presentation.dialogs import ParameterDefinition, ToolParametersPanel
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors.transform import CropProcessor
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_crop_processor_case_insensitive_parameters() -> None:
    store = ImageDataStore()
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[10:30, 20:50] = 255
    buf_id = store.allocate(arr)

    processor = CropProcessor(store)
    # Pass capitalized parameters as sent by ToolParametersPanel
    req = ProcessingRequest(
        operation="crop",
        parameters=(("X", "20"), ("Y", "10"), ("Width", "30"), ("Height", "20")),
    )
    res_id = processor.process(buf_id, req)
    res_arr = store.get(res_id)

    assert res_arr.shape == (20, 30, 3)
    assert np.all(res_arr == 255)


def test_crop_buffer_resilience_with_missing_id() -> None:
    store = ImageDataStore()
    # Missing buffer id should return fallback zero array without raising KeyError
    cropped_id = store.crop_buffer("non-existent-id", 10, 10, 50, 50, 100, 100)
    arr = store.get(cropped_id)
    assert arr.shape == (50, 50, 4)


def test_controller_crop_document_full_flow() -> None:
    store = ImageDataStore()
    arr = np.ones((200, 300, 3), dtype=np.uint8) * 128
    buf_id = store.allocate(arr)

    controller = EditorController(BlankDocumentRenderer(), data_store=store)
    doc = controller.create_document("TestDoc", 300, 200)

    # Add a layer with actual buffer
    controller.add_layer("ContentLayer")
    target_layer_id = doc.layers[0].id
    controller._session.replace(
        doc.changed(layers=(Layer(id=target_layer_id, name="Base", buffer_id=buf_id),))
    )

    cropped_doc = controller.crop_document(50, 40, 100, 80)
    assert cropped_doc.image.width == 100
    assert cropped_doc.image.height == 80

    cropped_layer = cropped_doc.layers[0]
    assert cropped_layer.buffer_id is not None
    cropped_arr = store.get(cropped_layer.buffer_id)
    assert cropped_arr.shape == (80, 100, 3)


def test_tool_parameters_panel_set_values() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    panel = ToolParametersPanel()
    schema = (
        ParameterDefinition("X", "integer", 0, 0, 10000),
        ParameterDefinition("Y", "integer", 0, 0, 10000),
        ParameterDefinition("Width", "integer", 400, 1, 10000),
        ParameterDefinition("Height", "integer", 300, 1, 10000),
    )
    panel.set_schema(schema)

    panel.set_values({"x": 25, "y": 35, "width": 120, "height": 90})
    vals = panel.values()
    assert vals["X"] == 25
    assert vals["Y"] == 35
    assert vals["Width"] == 120
    assert vals["Height"] == 90


def test_crop_document_resets_layer_transform() -> None:
    from dip_studio.domain.model import Transform

    store = ImageDataStore()
    arr = np.ones((200, 300, 4), dtype=np.uint8) * 100
    buf_id = store.allocate(arr)

    controller = EditorController(BlankDocumentRenderer(), data_store=store)
    doc = controller.create_document("TransformTest", 300, 200)
    layer = Layer(
        id=doc.layers[0].id,
        name="Transformed",
        buffer_id=buf_id,
        transform=Transform(tx=15.0, ty=15.0),
    )
    controller._session.replace(doc.changed(layers=(layer,)))

    cropped_doc = controller.crop_document(20, 20, 100, 100)
    assert cropped_doc.layers[0].transform is None


def test_main_window_crop_enter_and_undo_view_fitting() -> None:
    from PySide6.QtWidgets import QApplication

    from dip_studio.presentation.main_window import MainWindow
    from dip_studio.rendering.compositor import NumpyDocumentRenderer

    QApplication.instance() or QApplication([])
    store = ImageDataStore()
    renderer = NumpyDocumentRenderer(None)
    controller = EditorController(renderer=renderer, data_store=store)
    renderer._controller = controller

    window = MainWindow(controller=controller)
    arr = np.ones((200, 300, 4), dtype=np.uint8) * 200
    buf_id = store.allocate(arr)

    doc = controller.create_document("FlowTest", 300, 200)
    controller._session.replace(
        doc.changed(layers=(Layer(id=doc.layers[0].id, name="Base", buffer_id=buf_id),))
    )
    window._show_document(controller.document, "Loaded")
    window._tool_panel.select_tool("crop")

    # Set selection box and commit
    window._canvas.set_crop_rect_from_image(50, 50, 100, 100, 300, 200)
    window._commit_crop_from_selection()

    assert controller.document.image.width == 100
    assert controller.document.image.height == 100
    assert window._canvas._is_crop_mode is True
    assert window._canvas._selection_rect is not None

    # Undo crop
    window._undo()
    assert controller.document.image.width == 300
    assert controller.document.image.height == 200
    assert window._canvas._selection_rect is not None
    # Selection rect and display rect should be positive and aligned
    disp = window._canvas._image_display_rect()
    assert disp is not None
    assert disp.left() >= 0 and disp.top() >= 0
