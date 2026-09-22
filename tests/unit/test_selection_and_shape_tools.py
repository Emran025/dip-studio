"""Unit tests for selection tools, shape drawing, and Shift/Alt geometric constraints."""

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
import pytest

from dip_studio.application.editor import EditorController
from dip_studio.domain.model import Layer, LayerId, SelectionRect, ShapeLayer
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.shape_commands import DrawShape
from dip_studio.presentation.canvas_view import CanvasView
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_canvas_enter_only_commits_crop_in_crop_mode() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = CanvasView()
    canvas.set_selection_rect(QRect(1, 1, 5, 5))
    committed: list[bool] = []
    canvas.cropCommitted.connect(lambda: committed.append(True))

    canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )
    assert committed == []

    canvas.set_crop_mode(True)
    canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )
    assert committed == [True]
    canvas.close()
    del app


def test_canvas_compute_constrained_rect_shift_and_alt() -> None:
    origin = QPoint(100, 100)
    current = QPoint(200, 150)

    # 1. Unconstrained
    rect_normal = CanvasView.compute_constrained_rect(origin, current, shift=False, alt=False)
    assert rect_normal == QRect(QPoint(100, 100), QPoint(200, 150))

    # 2. Shift (1:1 aspect ratio square / circle)
    rect_shift = CanvasView.compute_constrained_rect(origin, current, shift=True, alt=False)
    assert rect_shift == QRect(QPoint(100, 100), QPoint(200, 200))

    # 3. Alt (Center-origin drawing)
    rect_alt = CanvasView.compute_constrained_rect(origin, current, shift=False, alt=True)
    assert rect_alt == QRect(0, 50, 200, 100)

    # 4. Shift + Alt (1:1 square centered on origin)
    rect_both = CanvasView.compute_constrained_rect(origin, current, shift=True, alt=True)
    assert rect_both == QRect(0, 0, 200, 200)


def test_editor_selection_and_shape_tools() -> None:
    controller = EditorController(BlankDocumentRenderer(), data_store=ImageDataStore())
    doc = controller.create_document("TestDoc", 400, 300)
    controller.add_layer("Layer 1")

    # Make selection
    sel = controller.make_selection(x=10, y=20, width=50, height=60, kind="rectangle")
    assert isinstance(sel, SelectionRect)
    assert sel.kind == "rectangle"
    assert sel.x == 10 and sel.y == 20

    controller.set_selection(sel)
    assert controller.active_selection == sel

    # Draw Shape (Rectangle)
    updated_doc = controller.draw_shape(
        "rectangle",
        rect=(20, 20, 80, 80),
        fill_color_name="Red",
        stroke_color_name="Black",
        stroke_width=2,
    )
    assert updated_doc is not None
    assert len(updated_doc.layers) >= 1
    assert isinstance(updated_doc.layers[-1], ShapeLayer)
    assert updated_doc.layers[-1].vertices == (20.0, 20.0, 80.0, 80.0)
    shape_id = updated_doc.layers[-1].id
    resized_doc = controller.resize_shape_layer(shape_id, (30, 25, 120, 90))
    resized = next(layer for layer in resized_doc.layers if layer.id == shape_id)
    assert isinstance(resized, ShapeLayer)
    assert resized.vertices == (30.0, 25.0, 120.0, 90.0)
    assert controller.hit_test_layer(140, 100).id == shape_id

    # Draw Shape (Ellipse)
    ellipse_doc = controller.draw_shape(
        "ellipse",
        rect=(50, 50, 60, 60),
        fill_color_name="Blue",
        stroke_color_name="White",
        stroke_width=1,
    )
    assert ellipse_doc is not None

    # Undo shape
    undo_doc = controller.undo()
    assert undo_doc is not None


def test_line_shape_uses_line_preview_and_accepts_axis_aligned_drag() -> None:
    controller = EditorController(BlankDocumentRenderer(), data_store=ImageDataStore())
    document = controller.create_document("Line", 100, 100)
    controller.add_layer("Layer 1")

    result = controller.draw_shape("Line", (10, 20, 70, 1))

    assert result is not None
    shape = result.layers[-1]
    assert isinstance(shape, ShapeLayer)
    assert shape.shape_type == "line"
    assert shape.vertices == (10.0, 20.0, 70.0, 1.0)
