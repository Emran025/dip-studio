import pytest

from dip_studio.application.tool_registry import default_tool_registry


def test_default_tool_registry_discovers_tools_and_parameters() -> None:
    registry = default_tool_registry()

    tools = registry.list()
    blur = registry.get("blur")

    assert [tool.name for tool in tools] == [
        "Select", "Selection", "Lasso", "Crop", "Blur", "Edge",
        "Gradient", "Hand", "Zoom", "Eyedropper", "Text", "Shape",
    ]
    assert [tool.shortcut for tool in tools] == [
        "V", "M", "L", "C", "B", "E", "G", "H", "Z", "I", "T", "U",
    ]
    assert blur.category == "Filter"
    assert [parameter.id for parameter in blur.parameters] == ["radius", "method"]


def test_tool_registry_rejects_unknown_tool() -> None:
    with pytest.raises(KeyError, match="Unknown tool"):
        default_tool_registry().get("missing")
