"""Application composition root for the desktop runtime."""

from dip_studio.application.editor import EditorController
from dip_studio.infrastructure.project_store import JsonProjectStore
from dip_studio.infrastructure.image_import import ImageFormatRegistry
from dip_studio.presentation.main_window import MainWindow
from dip_studio.rendering.ports import BlankDocumentRenderer


def create_main_window() -> MainWindow:
    controller = EditorController(
        BlankDocumentRenderer(), JsonProjectStore(), ImageFormatRegistry()
    )
    return MainWindow(controller)
