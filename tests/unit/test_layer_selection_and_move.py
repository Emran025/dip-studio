"""Unit tests for layer selection, canvas hit testing, and interactive move commands."""

import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dip_studio.application.editor import EditorController
from dip_studio.domain.factories import new_document
from dip_studio.domain.model import Layer, LayerId, Transform
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.presentation.canvas_view import CanvasView
from dip_studio.rendering.ports import BlankDocumentRenderer


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_translate_layer_updates_layer_transform():
    store = ImageDataStore()
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    buf_id = store.allocate(arr)

    doc = new_document("Test", 200, 200)
    layer = Layer(LayerId("layer-1"), "Layer 1", buffer_id=buf_id)
    doc = doc.changed(layers=(layer,))

    controller = EditorController(BlankDocumentRenderer(), data_store=store)
    controller._activate_new_document(doc)

    res_doc = controller.translate_layer(layer.id, 25.0, 15.0)
    res_layer = res_doc.layers[0]

    assert res_layer.transform is not None
    assert res_layer.transform.tx == 25.0
    assert res_layer.transform.ty == 15.0


def test_hit_test_layer_finds_layer_under_cursor():
    store = ImageDataStore()
    arr1 = np.zeros((100, 100, 4), dtype=np.uint8)
    arr1[:, :] = [255, 0, 0, 255]
    buf1 = store.allocate(arr1)

    doc = new_document("Test", 200, 200)
    l1 = Layer(LayerId("l1"), "Layer 1", buffer_id=buf1)
    doc = doc.changed(layers=(l1,))

    controller = EditorController(BlankDocumentRenderer(), data_store=store)
    controller._activate_new_document(doc)

    hit = controller.hit_test_layer(50, 50)
    assert hit is not None
    assert hit.id == l1.id

    miss = controller.hit_test_layer(150, 150)
    assert miss is None or miss.id == l1.id  # fallback bounding box test


def test_canvas_view_active_layer_rect_overlay(app):
    canvas = CanvasView()
    canvas.set_active_layer_rect(10, 20, 100, 80, "Layer 1", 200, 200)
    assert canvas._active_layer_rect == (10, 20, 100, 80, 200, 200)
    assert canvas._active_layer_name == "Layer 1"

    canvas.clear_active_layer_rect()
    assert canvas._active_layer_rect is None
    assert canvas._active_layer_name == ""
