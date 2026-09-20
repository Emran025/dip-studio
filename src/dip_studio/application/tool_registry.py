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
            ToolDefinition("selection", "Selection", "Selection", "Create a region selection", "M"),
            ToolDefinition("lasso", "Lasso", "Selection", "Create a freehand selection", "L"),
            ToolDefinition("crop", "Crop", "Transform", "Crop the active document", "C"),
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
            ToolDefinition("hand", "Hand", "Navigation", "Pan the canvas", "H"),
            ToolDefinition("zoom", "Zoom", "Navigation", "Zoom the canvas", "Z"),
            ToolDefinition("eyedropper", "Eyedropper", "Sampling", "Sample a color", "I"),
            ToolDefinition("text", "Text", "Vector", "Create text", "T"),
            ToolDefinition("shape", "Shape", "Vector", "Create a shape", "U"),
        )
    )
