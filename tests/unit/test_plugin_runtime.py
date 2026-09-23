from pathlib import Path

from dip_studio.application.tool_registry import InMemoryToolRegistry
from dip_studio.infrastructure.plugin_runtime import discover_and_activate_plugins
from dip_studio.processing.engine import ProcessingEngine
from dip_studio.processing.plugins import PluginRegistry


def test_runtime_discovers_and_activates_plugin(tmp_path: Path) -> None:
    plugin = tmp_path / "runtime_plugin.py"
    plugin.write_text(
        """
from dip_studio.processing.plugins import API_VERSION
class Processor:
    operation = "runtime_test"
    def validate(self, request): pass
    def process(self, image, request): return image
class Plugin:
    plugin_id = "runtime_plugin"
    api_version = API_VERSION
    def processors(self): return (Processor(),)
PLUGIN = Plugin()
""",
        encoding="utf-8",
    )
    engine = ProcessingEngine({})
    registry = PluginRegistry()
    tools = InMemoryToolRegistry()

    activated = discover_and_activate_plugins(registry, engine, tools, (tmp_path,))

    assert activated == ("runtime_plugin",)
    assert "runtime_test" in engine.operations


def test_runtime_reports_import_and_activation_failures(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("raise RuntimeError('broken import')", encoding="utf-8")
    plugin = tmp_path / "partial.py"
    plugin.write_text(
        """
class Plugin:
    plugin_id = "partial"
    api_version = 1
    def processors(self):
        raise RuntimeError("processor discovery failed")
PLUGIN = Plugin()
""",
        encoding="utf-8",
    )
    registry = PluginRegistry()
    discover_and_activate_plugins(
        registry, ProcessingEngine({}), InMemoryToolRegistry(), (tmp_path,)
    )

    failures = {(failure.plugin_id, failure.stage) for failure in registry.failures}
    assert (str(tmp_path / "broken.py"), "module_import") in failures
    assert ("partial", "processor_discovery") in failures
