import pytest

from dip_studio.application.tool_registry import (
    InMemoryToolRegistry,
    ToolDefinition,
    ToolParameter,
    default_tool_registry,
)


def test_default_tool_registry_discovers_tools_and_parameters() -> None:
    registry = default_tool_registry()

    tools = registry.list()
    blur = registry.get("blur")

    assert [tool.name for tool in tools] == [
        "Select", "Selection", "Ellipse selection", "Lasso",
        "Polygon selection", "Color selection", "Crop", "Move", "Transform",
        "Rotate", "Blur", "Edge", "Gradient", "Brush", "Pencil", "Eraser",
        "Fill", "Clone stamp", "Hand", "Zoom", "Eyedropper", "Text", "Shape",
        "Histogram", "Threshold", "Morphology", "Segmentation",
    ]
    assert [tool.shortcut for tool in tools] == [
        "V", "M", "O", "L", "P", None, "C", None, None, None, "B", "E",
        "G", "Shift+B", None, "Shift+E", "F", None, "H", "Z", "I", "T",
        "U", None, None, None, None,
    ]
    assert blur.category == "Filter"
    assert [parameter.id for parameter in blur.parameters] == ["radius", "method"]


def test_tool_registry_rejects_unknown_tool() -> None:
    with pytest.raises(KeyError, match="Unknown tool"):
        default_tool_registry().get("missing")


def test_tool_parameter_schema_supports_step_description_and_validation() -> None:
    parameter = ToolParameter(
        "threshold", "Threshold", "number", 10, 0, 100, (),
        step=0.5, description="Detection threshold",
        validation=lambda value: float(value) == 10,
    )
    registry = InMemoryToolRegistry((
        ToolDefinition("custom", "Custom", "Plugin", "Custom tool", parameters=(parameter,)),
    ))

    assert parameter.step == 0.5
    assert parameter.description == "Detection threshold"
    registry.validate_parameters("custom", {"threshold": 10})
    with pytest.raises(ValueError, match="Invalid parameters"):
        registry.validate_parameters("custom", {"threshold": 11})
