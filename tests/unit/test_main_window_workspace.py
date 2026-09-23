"""Focused MainWindow workspace and command-routing coverage."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

from dip_studio.presentation import main_window as main_window_module
from dip_studio.presentation.canvas_view import CanvasView
from dip_studio.presentation.main_window import MainWindow


@pytest.fixture
def main_window() -> MainWindow:
    app = QApplication.instance() or QApplication([])
    del app
    window = MainWindow()
    settings = window._settings()
    settings.clear()
    yield window
    window._processing_worker.cancel_all()
    window._processing_worker.wait_for_done()
    window.close()
    settings.clear()


def test_workspace_round_trip_persists_geometry_and_panel(main_window: MainWindow) -> None:
    main_window.resize(980, 640)
    main_window._sidebar.tabs.setCurrentIndex(1)
    main_window._save_workspace()

    settings = main_window._settings()
    assert isinstance(settings.value("geometry"), QByteArray)
    assert isinstance(settings.value("windowState"), QByteArray)
    assert settings.value("workspacePanel", type=int) == 1


def test_invalid_saved_workspace_restores_default_layout(main_window: MainWindow) -> None:
    settings = main_window._settings()
    settings.setValue("geometry", QByteArray(b"invalid"))
    settings.setValue("windowState", QByteArray(b"invalid"))
    settings.sync()

    main_window._restore_workspace()

    assert main_window.size().width() == 1200
    assert main_window.size().height() == 760
    assert "default layout restored" in main_window.statusBar().currentMessage()


def test_ui_command_registry_contains_shared_tool_and_processing_routes(
    main_window: MainWindow,
) -> None:
    assert "tool.select" in main_window._ui_commands
    assert "processing.sobel" in main_window._ui_commands
    assert "processing.gaussian_blur.dialog" in main_window._ui_commands
    with pytest.raises(KeyError, match="Unknown UI command"):
        main_window._dispatch_ui_command("missing.command")


def test_canvas_view_requires_valid_rgba_buffers() -> None:
    canvas = CanvasView()
    canvas.set_preview_array(np.full((2, 3, 4), 255, dtype=np.uint8))
    assert canvas._source_image is not None
    assert canvas._source_image.width() == 3

    with pytest.raises(ValueError, match="3 or 4 channels"):
        canvas.set_preview_array(np.zeros((2, 3, 2), dtype=np.uint8))

    with pytest.raises(ValueError, match="must be 2D or 3D"):
        canvas.set_preview_array(np.zeros((2,), dtype=np.uint8))


def test_refresh_preview_surfaces_failures_in_status_bar(main_window: MainWindow) -> None:
    preview_controller = MagicMock()
    preview_controller.document = SimpleNamespace(
        id="doc-1",
        name="Demo",
        image=SimpleNamespace(width=32, height=32),
        is_dirty=False,
        layers=(),
    )
    preview_controller.preview.side_effect = ValueError("bad preview")
    main_window._controller = preview_controller

    main_window._refresh_preview()

    assert "Preview render failed: bad preview" in main_window.statusBar().currentMessage()


def test_new_project_keeps_existing_documents_open(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = main_window._controller.create_document("first", 20, 20)
    main_window._show_document(first, "Created first")
    confirm = MagicMock(side_effect=AssertionError("opening must not close the active document"))
    main_window._confirm_document_transition = confirm

    class AcceptedNewProjectDialog:
        def __init__(self, _parent: MainWindow) -> None:
            pass

        def exec(self) -> int:
            return int(QDialog.DialogCode.Accepted)

        def values(self) -> SimpleNamespace:
            return SimpleNamespace(name="second", width=30, height=30)

    from PySide6.QtWidgets import QDialog

    monkeypatch.setattr(main_window_module, "NewProjectDialog", AcceptedNewProjectDialog)
    main_window._show_new_project()

    assert [document.name for document in main_window._controller.open_documents] == [
        "first",
        "second",
    ]
    assert main_window._controller.document.name == "second"
    confirm.assert_not_called()
    confirm.side_effect = None
    confirm.return_value = True


def test_open_image_does_not_request_closing_active_document(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = main_window._controller.create_document("first", 20, 20)
    second = SimpleNamespace(name="second", layers=(), image=SimpleNamespace(width=30, height=30))
    main_window._controller.open_image = MagicMock(return_value=second)
    main_window._show_document = MagicMock()
    confirm = MagicMock(side_effect=AssertionError("opening must not close the active document"))
    main_window._confirm_document_transition = confirm

    class OpenImageDialog:
        @staticmethod
        def getOpenFileName(*_args: object) -> tuple[str, str]:
            return "second.png", ""

    monkeypatch.setattr(main_window_module, "QFileDialog", OpenImageDialog)
    main_window._open_image()

    main_window._controller.open_image.assert_called_once()
    assert main_window._controller.open_documents == (first,)
    confirm.assert_not_called()
    confirm.side_effect = None
    confirm.return_value = True
