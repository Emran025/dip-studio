"""Regression tests for layer actions and icon-bearing controls."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from dip_studio.presentation.sidebar import RightSidebar


def test_layer_sidebar_exposes_delete_button_and_delete_key() -> None:
    app = QApplication.instance() or QApplication([])
    sidebar = RightSidebar()
    requested: list[str] = []
    sidebar.set_layer_structure_callback(
        lambda action, _selected: requested.append(action)
    )

    delete_button = sidebar.findChild(type(sidebar.layer_lock_button), "removeLayerButton")
    assert delete_button is not None
    assert not delete_button.icon().isNull()

    sidebar.layers.setFocus()
    sidebar.layers.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Delete,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert requested == ["remove"]
