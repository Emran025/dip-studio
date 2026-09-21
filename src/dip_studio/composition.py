"""Application composition root for the desktop runtime."""
from __future__ import annotations

from dip_studio.application.editor import EditorController
from dip_studio.application.tool_registry import (
    default_tool_registry,
    processing_tool_definitions,
)
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.image_import import ImageFormatRegistry
from dip_studio.infrastructure.project_store import JsonProjectStore
from dip_studio.presentation.main_window import MainWindow
from dip_studio.processing.registry import build_processing_engine


def create_main_window() -> MainWindow:
    data_store = ImageDataStore()
    image_importer = ImageFormatRegistry(data_store=data_store)
    processing_engine = build_processing_engine(data_store)

    # Build tool registry: merge the 27 interaction tools + all processing tools.
    tool_registry = default_tool_registry()
    for tool_def in processing_tool_definitions():
        tool_registry.register(tool_def)

    # Controller created first without renderer (renderer needs controller reference).
    controller = EditorController(
        renderer=_DeferredRenderer(),  # temporary placeholder
        project_store=JsonProjectStore(),
        image_importer=image_importer,
        data_store=data_store,
        processing_engine=processing_engine,
        tool_registry=tool_registry,
    )

    # Replace renderer with real compositor that references controller.
    from dip_studio.rendering.compositor import NumpyDocumentRenderer

    controller._renderer = NumpyDocumentRenderer(controller)

    return MainWindow(controller)


class _DeferredRenderer:
    """Placeholder renderer used only during controller bootstrap."""

    def render(self, request: object) -> bytes:
        raise RuntimeError("Renderer not yet initialized")
