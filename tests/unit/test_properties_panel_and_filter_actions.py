"""Unit tests verifying filter menu action signal handling and layer properties panel behavior."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from dip_studio.application.editor import EditorController
from dip_studio.application.tool_registry import default_tool_registry, processing_tool_definitions
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.presentation.dialogs import ParameterDefinition, ToolParametersPanel
from dip_studio.presentation.main_window import MainWindow
from dip_studio.rendering.compositor import NumpyDocumentRenderer


@pytest.fixture
def main_window():
    app = QApplication.instance() or QApplication([])
    store = ImageDataStore()
    renderer = NumpyDocumentRenderer(None)

    tool_reg = default_tool_registry()
    for tool_def in processing_tool_definitions():
        tool_reg.register(tool_def)

    controller = EditorController(
        renderer=renderer,
        data_store=store,
        tool_registry=tool_reg,
    )
    renderer._controller = controller

    window = MainWindow(controller=controller)
    yield window
    window._processing_worker._pool.clear()
    # Closing a dirty real window asks the user what to do; a fixture must not
    # block on that modal dialog during automated teardown.
    window._confirm_document_transition = lambda: True
    window.close()
    app.processEvents()


def test_processing_action_signal_does_not_raise_keyerror_false(main_window: MainWindow):
    """QAction.triggered(checked) signal passes a boolean.
    _processing_action returned lambda must consume the boolean without overriding command_id.
    """
    # Test quick apply processing action (no dialog)
    action_handler = main_window._processing_action("negative", {})
    action = QAction("Negative Test", main_window)
    action.triggered.connect(action_handler)

    # Triggering action must not raise KeyError: 'Unknown UI command: False'
    action.trigger()

    # Test dialog processing action
    action_handler_dialog = main_window._processing_action("gaussian_blur", {}, dialog=True)
    action_dialog = QAction("Blur Test", main_window)
    action_dialog.triggered.connect(action_handler_dialog)
    action_dialog.trigger()

    assert main_window._active_tool_id == "gaussian_blur"


def test_layer_selection_updates_properties_panel_schema(main_window: MainWindow):
    """Selecting a layer in move/select mode populates the Properties panel with element controls."""  # noqa: E501
    controller = main_window._controller
    doc = controller.create_document("TestDoc", 400, 300)
    layer = controller.add_layer("Layer 1").layers[0]

    main_window._show_document(doc, "Test")
    main_window._select_tool("move")
    main_window._on_layer_selection_changed(layer.id)

    panel = main_window._sidebar.properties
    values = panel.values()

    assert values.get("layer_name") == layer.name or values.get("Name") == layer.name
    assert values.get("opacity") == layer.opacity or values.get("Opacity") == layer.opacity
    assert main_window._is_editing_layer_properties is True


def test_editing_layer_properties_in_sidebar_updates_layer(main_window: MainWindow):
    """Editing Layer properties via sidebar Properties panel updates layer opacity, blend mode, and name."""  # noqa: E501
    controller = main_window._controller
    doc = controller.create_document("TestDoc", 400, 300)
    layer = controller.add_layer("Layer 1").layers[0]

    main_window._show_document(doc, "Test")
    main_window._on_layer_selection_changed(layer.id)

    # Simulate changing opacity in properties panel
    main_window._on_properties_value_changed(
        {
            "layer_name": "Renamed Layer",
            "opacity": 0.5,
            "blend_mode": "Multiply",
            "visible": True,
            "locked": False,
            "pos_x": 10,
            "pos_y": 20,
        }
    )

    updated_doc = controller.document
    updated_layer = updated_doc.layers[0]

    assert updated_layer.name == "Renamed Layer"
    assert updated_layer.opacity == pytest.approx(0.5)
    assert updated_layer.blend_mode == "multiply"


def test_tool_parameters_panel_can_replace_schema_repeatedly():
    """Changing filters repeatedly must not reuse a deleted actions widget."""
    panel = ToolParametersPanel()
    schema = (ParameterDefinition("Radius", "integer", 3, 1, 99),)

    panel.set_schema(schema, show_actions=True)
    panel.set_schema(schema, show_actions=True)
    panel.set_schema((), show_actions=False)
    QApplication.instance().processEvents()

    panel.set_schema(schema, show_actions=True)
    assert panel._actions is not None


def test_number_parameters_keep_small_processing_values() -> None:
    panel = ToolParametersPanel()
    panel.set_schema((ParameterDefinition("Step", "number", 0.001, 0.0001, 1.0),))

    assert panel.values()["Step"] == pytest.approx(0.001)
