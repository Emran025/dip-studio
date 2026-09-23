"""Runtime plugin discovery and activation."""

from __future__ import annotations

import logging
from pathlib import Path

from dip_studio.processing.plugins import PluginLoader, PluginRegistry

_LOGGER = logging.getLogger(__name__)


def discover_and_activate_plugins(
    registry: PluginRegistry,
    processing_engine: object,
    tool_registry: object,
    directories: tuple[Path, ...] = (),
) -> tuple[str, ...]:
    """Load plugins from explicit directories and activate them safely.

    Each plugin is isolated by ``PluginLoader`` and ``PluginRegistry``. A
    failure is logged by the loader/registry and does not prevent core startup.
    """
    loader = PluginLoader(registry)
    for directory in directories:
        loader.load_from_directory(directory)
    registry.activate_all(processing_engine, tool_registry)
    activated = registry.plugin_ids
    _LOGGER.info("Plugin runtime activation complete: %d plugin(s)", len(activated))
    return activated
