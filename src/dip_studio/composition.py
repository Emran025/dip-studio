"""Application composition root for the desktop runtime."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dip_studio.application.editor import EditorController
from dip_studio.application.tool_registry import (
    default_tool_registry,
    processing_tool_definitions,
)
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.image_import import ImageFormatRegistry
from dip_studio.infrastructure.processing_cache import ProcessingCache
from dip_studio.infrastructure.zip_project_store import ZipProjectStore
from dip_studio.infrastructure.plugin_runtime import discover_and_activate_plugins
from dip_studio.presentation.main_window import MainWindow
from dip_studio.processing.registry import build_processing_engine
from dip_studio.processing.plugins import global_registry

_LOGGER = logging.getLogger(__name__)


def create_main_window() -> MainWindow:
    data_store = ImageDataStore()
    image_importer = ImageFormatRegistry(data_store=data_store)

    # LRU processing cache — 32 slots, keyed by (buffer_id, version, op, params).
    cache = ProcessingCache(max_entries=32)
    processing_engine = build_processing_engine(data_store, cache=cache)

    # Build tool registry: merge the 27 interaction tools + all processing tools.
    tool_registry = default_tool_registry()
    for tool_def in processing_tool_definitions():
        tool_registry.register(tool_def)

    plugin_directories = _plugin_directories()
    discover_and_activate_plugins(
        global_registry(),
        processing_engine,
        tool_registry,
        plugin_directories,
    )
    plugin_registry = global_registry()

    # ZipProjectStore (format v2) persists pixel buffers alongside metadata.
    project_store = ZipProjectStore(data_store=data_store)

    # Controller created first without renderer (renderer needs controller reference).
    controller = EditorController(
        renderer=_DeferredRenderer(),  # temporary placeholder
        project_store=project_store,
        image_importer=image_importer,
        data_store=data_store,
        processing_engine=processing_engine,
        tool_registry=tool_registry,
        plugin_failures=plugin_registry.failures,
    )

    # Replace renderer with real compositor that references controller.
    from dip_studio.rendering.compositor import NumpyDocumentRenderer

    controller._renderer = NumpyDocumentRenderer(controller)

    window = MainWindow(controller)

    # Start periodic autosave (every 2 minutes) after the window is ready.
    try:
        from dip_studio.infrastructure.autosave import AutosaveWorker
        autosave = AutosaveWorker(controller, interval_seconds=120)
        autosave.start()
        # Keep a reference so the worker isn't GC'd.
        window._autosave_worker = autosave  # type: ignore[attr-defined]
    except (ImportError, RuntimeError) as exc:
        _LOGGER.warning("Autosave is unavailable: %s", exc)

    return window


def _plugin_directories() -> tuple[Path, ...]:
    """Return only explicitly configured plugin directories."""
    configured = os.environ.get("DIP_STUDIO_PLUGIN_DIRS", "")
    if not configured:
        return ()
    return tuple(
        Path(entry).expanduser()
        for entry in configured.split(os.pathsep)
        if entry.strip()
    )


class _DeferredRenderer:
    """Placeholder renderer used only during controller bootstrap."""

    def render(self, request: object) -> bytes:
        raise RuntimeError("Renderer not yet initialized")
