"""Tests for the plugin system: PluginRegistry, PluginLoader, and global_registry."""
from __future__ import annotations

import pytest

from dip_studio.processing.contracts import ProcessingRequest, Processor
from dip_studio.processing.engine import ProcessingEngine
from dip_studio.processing.plugins import (
    API_VERSION,
    PluginLoader,
    PluginRegistry,
    global_registry,
)


# ─────────────────── Stub Processor ───────────────────

class _NoopProcessor:
    operation = "noop_test"

    def validate(self, request: ProcessingRequest) -> None:
        pass

    def process(self, image: object, request: ProcessingRequest) -> object:
        return image


# ─────────────────── Stub Plugin ───────────────────

class _GoodPlugin:
    plugin_id = "test_good_plugin"
    api_version = API_VERSION

    def processors(self) -> tuple[_NoopProcessor, ...]:
        return (_NoopProcessor(),)


class _WrongVersionPlugin:
    plugin_id = "bad_version"
    api_version = 999  # wrong

    def processors(self) -> tuple[_NoopProcessor, ...]:
        return (_NoopProcessor(),)


# ─────────────────── Tests ───────────────────

class TestPluginRegistry:
    def test_register_good_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register(_GoodPlugin())
        assert "test_good_plugin" in registry.plugin_ids

    def test_wrong_version_plugin_is_skipped(self) -> None:
        registry = PluginRegistry()
        registry.register(_WrongVersionPlugin())
        assert "bad_version" not in registry.plugin_ids

    def test_unregister_removes_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register(_GoodPlugin())
        registry.unregister("test_good_plugin")
        assert "test_good_plugin" not in registry.plugin_ids

    def test_activate_all_registers_processors(self) -> None:
        registry = PluginRegistry()
        registry.register(_GoodPlugin())
        engine: ProcessingEngine[object, object] = ProcessingEngine({})
        registry.activate_all(engine)
        assert "noop_test" in engine.operations

    def test_register_replaces_existing(self) -> None:
        registry = PluginRegistry()
        registry.register(_GoodPlugin())
        registry.register(_GoodPlugin())  # second registration same id
        assert registry.plugin_ids.count("test_good_plugin") == 1


class TestProcessingEngineExtensions:
    def test_register_adds_operation(self) -> None:
        engine: ProcessingEngine[object, object] = ProcessingEngine({})
        engine.register(_NoopProcessor())
        assert "noop_test" in engine.operations

    def test_unregister_removes_operation(self) -> None:
        engine: ProcessingEngine[object, object] = ProcessingEngine({})
        engine.register(_NoopProcessor())
        engine.unregister("noop_test")
        assert "noop_test" not in engine.operations

    def test_run_with_registered_processor(self) -> None:
        engine: ProcessingEngine[object, object] = ProcessingEngine({})
        engine.register(_NoopProcessor())
        result = engine.run("data", ProcessingRequest("noop_test", ()))
        assert result == "data"

    def test_run_unknown_raises_key_error(self) -> None:
        engine: ProcessingEngine[object, object] = ProcessingEngine({})
        with pytest.raises(KeyError):
            engine.run("data", ProcessingRequest("missing", ()))

    def test_operations_property(self) -> None:
        engine: ProcessingEngine[object, object] = ProcessingEngine({"noop_test": _NoopProcessor()})  # type: ignore[arg-type]
        assert "noop_test" in engine.operations


class TestPluginLoader:
    def test_load_nonexistent_directory(self, tmp_path: object) -> None:
        import pathlib
        registry = PluginRegistry()
        loader = PluginLoader(registry)
        count = loader.load_from_directory(pathlib.Path("/nonexistent_dir_xyz"))
        assert count == 0

    def test_load_module_nonexistent(self) -> None:
        registry = PluginRegistry()
        loader = PluginLoader(registry)
        result = loader.load_module("nonexistent_module_xyz_123")
        assert result is False

    def test_load_from_directory_with_plugin_file(self, tmp_path: object) -> None:
        import pathlib
        tmp = pathlib.Path(str(tmp_path))
        plugin_file = tmp / "my_plugin.py"
        plugin_file.write_text(
            f"""
from dip_studio.processing.plugins import API_VERSION
from dip_studio.processing.contracts import ProcessingRequest

class _P:
    operation = "my_test_op"
    def validate(self, r): pass
    def process(self, img, r): return img

class _Plugin:
    plugin_id = "my_plugin"
    api_version = {API_VERSION}
    def processors(self):
        return (_P(),)

PLUGIN = _Plugin()
""",
            encoding="utf-8",
        )
        registry = PluginRegistry()
        loader = PluginLoader(registry)
        count = loader.load_from_directory(tmp)
        assert count == 1
        assert "my_plugin" in registry.plugin_ids


class TestGlobalRegistry:
    def test_global_registry_is_singleton(self) -> None:
        r1 = global_registry()
        r2 = global_registry()
        assert r1 is r2

    def test_global_registry_is_plugin_registry(self) -> None:
        assert isinstance(global_registry(), PluginRegistry)
