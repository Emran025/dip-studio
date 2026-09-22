"""Regression coverage for visibility changes rebuilding the layer tree."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dip_studio.domain.model import Layer, LayerId
from dip_studio.presentation.sidebar import RightSidebar


def test_visibility_callback_can_rebuild_tree_without_stale_item_error() -> None:
    app = QApplication.instance() or QApplication([])
    sidebar = RightSidebar()
    first = Layer(LayerId("first"), "First", visible=True)
    second = Layer(LayerId("second"), "Second", visible=True)
    sidebar.show_layers((first, second), (first.id,))

    def change_visibility(
        layer_ids: tuple[object, ...],
        visible: bool | None,
        _opacity: float | None,
        _blend_mode: str | None,
        _locked: bool | None,
    ) -> None:
        assert layer_ids == (first.id,)
        assert visible is False
        sidebar.show_layers(
            (first.changed(visible=False), second),
            (first.id,),
        )

    sidebar.set_layer_callback(change_visibility)
    item = sidebar.layers.topLevelItem(0)
    assert item is not None
    item.setCheckState(0, Qt.CheckState.Unchecked)
    assert sidebar.layers.topLevelItem(0).checkState(0) == Qt.CheckState.Unchecked
