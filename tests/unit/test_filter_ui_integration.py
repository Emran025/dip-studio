"""End-to-end checks for applying parameterized filters through the Qt UI path."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from dip_studio.application.editor import EditorController
from dip_studio.application.tool_registry import (
    default_tool_registry,
    processing_tool_definitions,
)
from dip_studio.domain.model import Layer
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.presentation.main_window import MainWindow
from dip_studio.processing.registry import build_processing_engine
from dip_studio.rendering.compositor import NumpyDocumentRenderer

PARAMETERIZED_FILTERS = tuple(
    definition.id
    for definition in processing_tool_definitions()
    if definition.parameters and definition.id != "template_match"
)
QUICK_FILTERS = tuple(
    definition.id for definition in processing_tool_definitions() if not definition.parameters
)


@pytest.fixture
def filter_window() -> tuple[MainWindow, QApplication]:
    app = QApplication.instance() or QApplication([])
    store = ImageDataStore()
    engine = build_processing_engine(store)
    renderer = NumpyDocumentRenderer(None)
    registry = default_tool_registry()
    for definition in processing_tool_definitions():
        registry.register(definition)
    controller = EditorController(
        renderer=renderer,
        data_store=store,
        processing_engine=engine,
        tool_registry=registry,
    )
    renderer._controller = controller

    source = np.zeros((48, 64, 3), dtype=np.uint8)
    source[:, :16] = (20, 80, 180)
    source[:, 16:32] = (230, 40, 40)
    source[12:36, 24:52] = (120, 220, 40)
    source[::2, ::2] = np.clip(source[::2, ::2].astype(np.int16) + 35, 0, 255)
    buffer_id = store.allocate(source)

    window = MainWindow(controller=controller)
    document = controller.create_document("Filter UI", source.shape[1], source.shape[0])
    layer = Layer(id=document.layers[0].id, name="Source", buffer_id=buffer_id)
    controller._session.replace(document.changed(layers=(layer,)))
    window._show_document(controller.document, "Loaded", (layer.id,))
    yield window, app

    window._processing_worker.cancel_all()
    window._processing_worker.wait_for_done(5000)
    window._confirm_document_transition = lambda: True
    window.close()
    app.processEvents()


@pytest.mark.parametrize("operation", PARAMETERIZED_FILTERS)
def test_filter_properties_apply_to_real_layer(
    filter_window: tuple[MainWindow, QApplication], operation: str
) -> None:
    window, app = filter_window
    controller = window._controller
    before = controller.document
    assert before is not None
    before_layer = before.layers[0]
    assert before_layer.buffer_id is not None
    before_buffer_id = before_layer.buffer_id

    window._select_tool(operation)
    panel = window._sidebar.properties
    values = panel.values()
    assert values, f"{operation} did not expose a Properties schema"

    window._apply_parameters(values)
    window._processing_worker.wait_for_done(5000)
    app.processEvents()

    after = controller.document
    assert after is not None
    after_layer = after.layers[0]
    assert after_layer.buffer_id is not None
    assert after_layer.buffer_id != before_buffer_id, operation
    assert after.operations[-1].operation == operation
    result = controller.data_store.get(after_layer.buffer_id)
    assert result.shape == (48, 64, 3)
    assert result.dtype == np.uint8
    assert window._active_tool_id == operation


@pytest.mark.parametrize("operation", QUICK_FILTERS)
def test_quick_filter_action_updates_real_layer(
    filter_window: tuple[MainWindow, QApplication], operation: str
) -> None:
    window, app = filter_window
    controller = window._controller
    before = controller.document
    assert before is not None
    before_buffer_id = before.layers[0].buffer_id
    assert before_buffer_id is not None

    window._quick_apply(operation, {})
    app.processEvents()

    after = controller.document
    assert after is not None
    after_buffer_id = after.layers[0].buffer_id
    assert after_buffer_id is not None and after_buffer_id != before_buffer_id
    assert after.operations[-1].operation == operation
    result = controller.data_store.get(after_buffer_id)
    assert result.shape == (48, 64, 3)
    assert result.dtype == np.uint8
    if operation == "negative":
        # The sample generator brightens every second pixel before applying the filter.
        assert np.array_equal(result[0, 0], np.array([200, 140, 40], dtype=np.uint8))


def test_template_match_uses_active_selection_as_template(
    filter_window: tuple[MainWindow, QApplication],
) -> None:
    window, app = filter_window
    controller = window._controller
    document = controller.document
    assert document is not None
    before_buffer_id = document.layers[0].buffer_id
    assert before_buffer_id is not None

    controller.set_selection(controller.make_selection(x=16, y=12, width=16, height=16))
    window._select_tool("template_match")
    values = window._sidebar.properties.values()
    assert values["template_buffer_id"] == ""

    window._apply_parameters(values)
    window._processing_worker.wait_for_done(5000)
    app.processEvents()

    after = controller.document
    assert after is not None
    assert after.layers[0].buffer_id != before_buffer_id
    assert after.operations[-1].operation == "template_match"
