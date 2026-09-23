"""Unit tests for ColorSwatchButton, DualColorSwatchWidget, and RGBA tuple color commands."""

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from dip_studio.application.editor import EditorController
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.presentation.color_swatch import ColorSwatchButton, DualColorSwatchWidget
from dip_studio.rendering.ports import BlankDocumentRenderer


@pytest.fixture(autouse=True)
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_color_swatch_button_properties_and_signals() -> None:
    button = ColorSwatchButton((255, 0, 0, 255))
    assert button.color == QColor(255, 0, 0, 255)

    emitted_colors = []
    button.colorChanged.connect(lambda col: emitted_colors.append(col))

    button.set_color((0, 255, 0, 255))
    assert button.color == QColor(0, 255, 0, 255)
    assert len(emitted_colors) == 1
    assert emitted_colors[0] == QColor(0, 255, 0, 255)


def test_dual_color_swatch_widget_swap_and_reset() -> None:
    widget = DualColorSwatchWidget()
    assert widget.foreground_rgba == (0, 0, 0, 255)
    assert widget.background_rgba == (255, 255, 255, 255)

    # Change FG color
    widget.set_foreground_color((255, 0, 0, 255))
    assert widget.foreground_rgba == (255, 0, 0, 255)

    # Swap FG/BG
    widget.swap_colors()
    assert widget.foreground_rgba == (255, 255, 255, 255)
    assert widget.background_rgba == (255, 0, 0, 255)

    # Reset default colors (Black FG, White BG)
    widget.reset_default_colors()
    assert widget.foreground_rgba == (0, 0, 0, 255)
    assert widget.background_rgba == (255, 255, 255, 255)


def test_draw_shape_with_explicit_rgba_tuples() -> None:
    controller = EditorController(BlankDocumentRenderer(), data_store=ImageDataStore())
    controller.create_document("ColorTest", 200, 200)

    res_doc = controller.draw_shape(
        "rectangle",
        rect=(10, 10, 50, 50),
        fill_color_name=(0, 255, 128, 255),
        stroke_color_name=(255, 128, 0, 255),
        stroke_width=3,
    )
    assert res_doc is not None
