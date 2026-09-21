"""Comprehensive tests for Photoshop-style crop, layer focus, and parameter handling."""
from pathlib import Path
import numpy as np
import pytest

from dip_studio.application.editor import EditorController
from dip_studio.domain.factories import new_document
from dip_studio.domain.model import ImageSpec, Layer, LayerId
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
    layer = controller.add_layer("ContentLayer")
    target_layer_id = doc.layers[0].id
    controller._session.replace(
        doc.changed(
            layers=(Layer(id=target_layer_id, name="Base", buffer_id=buf_id),)
        )
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

    app = QApplication.instance() or QApplication([])
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
