"""Versioned plugin capability contract and registry.

A plugin can register:
- Processors  (via ProcessingEngine)
- ToolDefinitions (via ToolRegistry)

Plugin discovery is an infrastructure concern:
    PluginLoader.load_all()  →  PluginRegistry.register()
                             →  ProcessingEngine + ToolRegistry updated

Example plugin module (third-party or built-in extension):

    class MyPlugin:
        plugin_id   = "my_plugin"
        api_version = 1

        def processors(self):
            return (MyProcessor(),)

        def tool_definitions(self):
            from dip_studio.application.tool_registry import ToolDefinition
            return (ToolDefinition("my_op", "My Op", "Custom", "M", ()),)

    PLUGIN = MyPlugin()
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from dip_studio.processing.contracts import Processor

_log = logging.getLogger(__name__)

API_VERSION = 1  # current plugin ABI version


@dataclass(frozen=True, slots=True)
class PluginActivationFailure:
    """A plugin failure that can be reported without stopping application startup."""

    plugin_id: str
    stage: str
    message: str


@runtime_checkable
class ProcessorPlugin(Protocol):
    """Minimal contract every DIP Studio plugin must satisfy."""

    plugin_id: str
    api_version: int

    def processors(self) -> tuple[Processor[object, object], ...]: ...  # noqa: D102


class FullPlugin(ProcessorPlugin, Protocol):
    """Extended plugin that also contributes tool definitions."""

    def tool_definitions(self) -> tuple[object, ...]: ...  # noqa: D102


class PluginRegistry:
    """Holds and activates registered plugins against a processing engine and tool registry."""

    def __init__(self) -> None:
        self._plugins: dict[str, ProcessorPlugin] = {}
        self._failures: list[PluginActivationFailure] = []

    def register(self, plugin: ProcessorPlugin) -> None:
        """Register *plugin*, replacing any prior registration with the same id."""
        if plugin.api_version != API_VERSION:
            self._failures.append(
                PluginActivationFailure(
                    plugin_id=getattr(plugin, "plugin_id", "<unknown>"),
                    stage="registration",
                    message=(
                        f"Plugin targets API v{plugin.api_version}; host supports v{API_VERSION}"
                    ),
                )
            )
            _log.warning(
                "Plugin '%s' targets API v%d but host is v%d — skipping",
                plugin.plugin_id,
                plugin.api_version,
                API_VERSION,
            )
            return
        self._plugins[plugin.plugin_id] = plugin
        _log.info("Plugin registered: %s", plugin.plugin_id)

    def unregister(self, plugin_id: str) -> None:
        """Remove plugin by id (no-op if not registered)."""
        self._plugins.pop(plugin_id, None)

    @property
    def plugin_ids(self) -> tuple[str, ...]:
        return tuple(self._plugins)

    @property
    def failures(self) -> tuple[PluginActivationFailure, ...]:
        return tuple(self._failures)

    def record_failure(self, plugin_id: str, stage: str, message: str) -> None:
        self._failures.append(PluginActivationFailure(plugin_id, stage, message))

    def activate_all(
        self,
        processing_engine: object,
        tool_registry: object | None = None,
    ) -> None:
        """Push all registered plugins into *processing_engine* and *tool_registry*.

        Args:
            processing_engine: a ``ProcessingEngine`` instance with a ``register`` method.
            tool_registry:     optional ``ToolRegistry`` instance with a ``register`` method.
        """
        for plugin in self._plugins.values():
            self._activate_one(plugin, processing_engine, tool_registry, self._failures)

    @staticmethod
    def _activate_one(
        plugin: ProcessorPlugin,
        processing_engine: object,
        tool_registry: object | None,
        failures: list[PluginActivationFailure],
    ) -> None:
        try:
            processors = plugin.processors()
        except Exception as exc:
            failures.append(
                PluginActivationFailure(plugin.plugin_id, "processor_discovery", str(exc))
            )
            _log.exception("Failed to discover processors from plugin '%s'", plugin.plugin_id)
            processors = ()
        for processor in processors:
            try:
                processing_engine.register(processor)  # type: ignore[union-attr]
                _log.debug(
                    "Registered processor '%s' from '%s'", processor.operation, plugin.plugin_id
                )
            except Exception as exc:
                failures.append(
                    PluginActivationFailure(plugin.plugin_id, "processor_registration", str(exc))
                )
                _log.exception("Failed to register processor from plugin '%s'", plugin.plugin_id)

        if tool_registry is not None and isinstance(plugin, FullPlugin):
            try:
                tool_definitions = plugin.tool_definitions()
            except Exception as exc:
                failures.append(
                    PluginActivationFailure(plugin.plugin_id, "tool_discovery", str(exc))
                )
                _log.exception("Failed to discover tools from plugin '%s'", plugin.plugin_id)
                tool_definitions = ()
            for tool_def in tool_definitions:
                try:
                    tool_registry.register(tool_def)  # type: ignore[union-attr]
                except Exception as exc:
                    failures.append(
                        PluginActivationFailure(plugin.plugin_id, "tool_registration", str(exc))
                    )
                    _log.exception("Failed to register tool from plugin '%s'", plugin.plugin_id)


class PluginLoader:
    """Discovers and loads plugin modules from a directory or a list of module names."""

    PLUGIN_ATTR = "PLUGIN"  # expected attribute name in plugin module

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def load_from_directory(self, directory: Path) -> int:
        """Scan *directory* for ``*.py`` files and load each as a plugin module.

        Returns the number of successfully loaded plugins.
        """
        count = 0
        if not directory.is_dir():
            _log.warning("Plugin directory does not exist: %s", directory)
            return 0
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            if self._load_from_path(path):
                count += 1
        return count

    def load_module(self, module_name: str) -> bool:
        """Import *module_name* and register its plugin.

        Returns True on success.
        """
        try:
            mod = importlib.import_module(module_name)
        except Exception as exc:
            self._registry.record_failure(module_name, "module_import", str(exc))
            _log.warning("Could not import plugin module: %s", module_name)
            return False
        return self._activate_module(mod, module_name)

    def _load_from_path(self, path: Path) -> bool:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            return False
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as exc:
            self._registry.record_failure(str(path), "module_import", str(exc))
            _log.exception("Error loading plugin from %s", path)
            return False
        return self._activate_module(mod, str(path))

    def _activate_module(self, mod: object, source: str) -> bool:
        plugin = getattr(mod, self.PLUGIN_ATTR, None)
        if plugin is None:
            self._registry.record_failure(source, "plugin_discovery", "Missing PLUGIN attribute")
            _log.debug("No '%s' attribute in %s — skipping", self.PLUGIN_ATTR, source)
            return False
        if not isinstance(plugin, ProcessorPlugin):
            self._registry.record_failure(
                source, "plugin_discovery", "PLUGIN does not satisfy ProcessorPlugin"
            )
            _log.warning(
                "'%s' in %s does not satisfy ProcessorPlugin protocol", self.PLUGIN_ATTR, source
            )
            return False
        self._registry.register(plugin)
        return True


# Module-level singleton registry (applications can use this or create their own)
_global_registry: PluginRegistry | None = None


def global_registry() -> PluginRegistry:
    """Return the process-wide PluginRegistry, creating it on first call."""
    global _global_registry
    if _global_registry is None:
        _global_registry = PluginRegistry()
    return _global_registry
