"""Discoverable tool definitions owned by the application layer."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ToolParameter:
    id: str
    label: str
    kind: str
    default: object
    minimum: float = 0
    maximum: float = 100
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    id: str
    name: str
    category: str
    description: str
    shortcut: str | None = None
    parameters: tuple[ToolParameter, ...] = ()


class ToolRegistry(Protocol):
    def list(self) -> tuple[ToolDefinition, ...]: ...
    def get(self, tool_id: str) -> ToolDefinition: ...


class InMemoryToolRegistry:
    def __init__(self, tools: tuple[ToolDefinition, ...] = ()) -> None:
        self._tools = {tool.id: tool for tool in tools}

    def list(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def get(self, tool_id: str) -> ToolDefinition:
        try:
            return self._tools[tool_id]
        except KeyError as error:
            raise KeyError(f"Unknown tool: {tool_id}") from error


def default_tool_registry() -> InMemoryToolRegistry:
    return InMemoryToolRegistry(
        (
            ToolDefinition("select", "Select", "General", "Select and move objects", "V"),
            ToolDefinition("selection", "Selection", "Selection", "Create a rectangular selection", "M"),
            ToolDefinition("ellipse_selection", "Ellipse selection", "Selection", "Create an elliptical selection", "O"),
            ToolDefinition("lasso", "Lasso", "Selection", "Create a freehand selection", "L"),
            ToolDefinition("polygon_selection", "Polygon selection", "Selection", "Create a polygon selection", "P"),
            ToolDefinition("color_selection", "Color selection", "Selection", "Select pixels by color", None),
            ToolDefinition("crop", "Crop", "Transform", "Crop the active document", "C"),
            ToolDefinition("move", "Move", "Transform", "Move the active layer or selection", None),
            ToolDefinition("transform", "Transform", "Transform", "Scale, rotate, and transform content", None),
            ToolDefinition("rotate", "Rotate", "Transform", "Rotate the active layer or selection", None),
            ToolDefinition(
                "blur",
                "Blur",
                "Filter",
                "Smooth image details",
                "B",
                parameters=(
                    ToolParameter("radius", "Radius", "number", 3.0, 0.1, 100.0),
                    ToolParameter(
                        "method",
                        "Method",
                        "choice",
                        "Gaussian",
                        choices=("Gaussian", "Median"),
                    ),
                ),
            ),
            ToolDefinition(
                "edge",
                "Edge",
                "Filter",
                "Detect image edges",
                "E",
                parameters=(
                    ToolParameter("threshold", "Threshold", "integer", 128, 0, 255),
                    ToolParameter("automatic", "Automatic", "boolean", True),
                ),
            ),
            ToolDefinition("gradient", "Gradient", "Paint", "Apply a gradient", "G"),
            ToolDefinition("brush", "Brush", "Paint", "Paint with a soft or hard brush", "Shift+B"),
            ToolDefinition("pencil", "Pencil", "Paint", "Draw hard-edged strokes", None),
            ToolDefinition("eraser", "Eraser", "Paint", "Erase pixels or layer content", "Shift+E"),
            ToolDefinition("fill", "Fill", "Paint", "Fill a connected region", "F"),
            ToolDefinition("clone", "Clone stamp", "Retouch", "Clone pixels from a source point", None),
            ToolDefinition("hand", "Hand", "Navigation", "Pan the canvas", "H"),
            ToolDefinition("zoom", "Zoom", "Navigation", "Zoom the canvas", "Z"),
            ToolDefinition("eyedropper", "Eyedropper", "Sampling", "Sample a color", "I"),
            ToolDefinition("text", "Text", "Vector", "Create text", "T"),
            ToolDefinition("shape", "Shape", "Vector", "Create a shape", "U"),
            ToolDefinition("histogram", "Histogram", "Analysis", "Inspect image intensity distribution", None),
            ToolDefinition("threshold", "Threshold", "Analysis", "Create a binary threshold preview", None),
            ToolDefinition("morphology", "Morphology", "Analysis", "Apply morphological analysis", None),
            ToolDefinition("segment", "Segmentation", "Analysis", "Segment image regions", None),
        )
    )
