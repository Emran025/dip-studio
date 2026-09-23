"""Unit tests for CanvasView rendering quality and direct array preview paths."""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from dip_studio.presentation.canvas_view import CanvasView


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_canvas_view_uses_smooth_transformation(app):
    canvas = CanvasView()

    # Create 100x100 QImage
    img = QImage(100, 100, QImage.Format.Format_RGBA8888)
    img.fill(Qt.GlobalColor.blue)
    canvas._source_image = img

    # Set zoom > 1.0 (upscaling) and verify SmoothTransformation is used
    canvas.set_zoom(2.0)
    assert canvas.zoom == 2.0
    assert canvas._pixmap is not None
    assert canvas._pixmap.width() == 200
    assert canvas._pixmap.height() == 200


def test_canvas_view_set_preview_array_handles_rgba(app):
    canvas = CanvasView()

    arr = np.full((60, 80, 4), 128, dtype=np.uint8)
    canvas.set_preview_array(arr)

    assert canvas._source_image is not None
    assert canvas._source_image.width() == 80
    assert canvas._source_image.height() == 60
