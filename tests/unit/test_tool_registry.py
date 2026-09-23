import pytest

from dip_studio.application.shortcut_registry import default_shortcut_registry
from dip_studio.application.tool_registry import (
    InMemoryToolRegistry,
    ToolDefinition,
    ToolParameter,
    default_tool_registry,
    processing_tool_definitions,
)
from dip_studio.presentation.tool_panel import ToolPanel


def test_default_tool_registry_discovers_tools_and_parameters() -> None:
    registry = default_tool_registry()

    tools = registry.list()
    blur = registry.get("blur")

    assert [tool.name for tool in tools] == [
        "Select", "Selection", "Ellipse selection", "Lasso",
        "Polygon selection", "Color selection", "Crop", "Move", "Transform",
        "Rotate", "Blur", "Edge", "Gradient", "Brush", "Pencil", "Eraser",
        "Fill", "Clone stamp", "Hand", "Zoom", "Eyedropper", "Text",
        "Rectangle", "Ellipse", "Line", "Polygon",
        "Histogram", "Threshold", "Morphology", "Segmentation",
    ]
    assert [tool.shortcut for tool in tools] == [
        "V", "M", "O", "L", "P", None, "C", None, None, None, "B", "E",
        "G", "Shift+B", None, "Shift+E", "F", None, "H", "Z", "I", "T",
        "U", None, None, None, None, None, None, None,
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


def test_shape_tool_is_in_a_dedicated_visible_drawing_group() -> None:
    groups = dict(ToolPanel._GROUPS)

    assert groups["Drawing"] == (
        "shape_rectangle", "shape_ellipse", "shape_line", "shape_polygon"
    )
    assert all(not tool_id.startswith("shape") for tool_id in groups["Vector"])
    assert groups["Vector"] == ("text",)

    grouped_tools = [
        tool_id
        for tool_ids in groups.values()
        for tool_id in tool_ids
    ]
    assert len(grouped_tools) == len(set(grouped_tools))


def test_rectangle_shape_owns_the_drawing_shortcut() -> None:
    shortcuts = default_shortcut_registry()

    assert shortcuts.get("tool.shape_rectangle").key == "U"
    with pytest.raises(KeyError):
        shortcuts.get("tool.shape")


def test_required_blur_filters_are_exposed_in_registry_and_toolbar_group() -> None:
    required = {"gaussian_blur", "median_blur", "denoise_mean", "bilateral_filter"}
    definitions = {definition.id: definition for definition in processing_tool_definitions()}

    assert required <= definitions.keys()
    assert {definitions[tool_id].category for tool_id in required} == {"Filter"}
    assert required <= set(dict(ToolPanel._GROUPS)["Filter"])


def test_morphology_kernel_properties_are_centered_and_safe() -> None:
    definitions = {
        definition.id: definition
        for definition in (*default_tool_registry().list(), *processing_tool_definitions())
    }
    for tool_id in ("morphology", "erode", "dilate", "morph_open", "morph_close"):
        parameter = next(
            parameter for parameter in definitions[tool_id].parameters
            if parameter.id == "kernel_size"
        )
        assert parameter.step == 2
        assert parameter.validate(3)
        assert not parameter.validate(2)
