"""Discoverable tool definitions owned by the application layer."""

from dataclasses import dataclass
from collections.abc import Callable, Mapping
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
    step: float | None = None
    description: str = ""
    validation: Callable[[object], bool] | None = None

    def validate(self, value: object) -> bool:
        """Validate a value against the declared schema without coercing it."""
        if self.choices and value not in self.choices:
            return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < self.minimum or value > self.maximum:
                return False
        return self.validation(value) if self.validation is not None else True


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    id: str
    name: str
    category: str
    description: str
    shortcut: str | None = None
    parameters: tuple[ToolParameter, ...] = ()
    capabilities: tuple[str, ...] = ()


class ToolRegistry(Protocol):
    def list(self) -> tuple[ToolDefinition, ...]: ...
    def get(self, tool_id: str) -> ToolDefinition: ...

    def validate_parameters(self, tool_id: str, values: Mapping[str, object]) -> None: ...


class InMemoryToolRegistry:
    def __init__(self, tools: tuple[ToolDefinition, ...] = ()) -> None:
        self._tools = {tool.id: tool for tool in tools}

    def register(self, tool: ToolDefinition) -> None:
        """Register an additional tool at runtime (e.g. from processing registry)."""
        self._tools[tool.id] = tool

    def list(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def get(self, tool_id: str) -> ToolDefinition:
        try:
            return self._tools[tool_id]
        except KeyError as error:
            raise KeyError(f"Unknown tool: {tool_id}") from error

    def validate_parameters(self, tool_id: str, values: Mapping[str, object]) -> None:
        tool = self.get(tool_id)
        parameters = {parameter.id: parameter for parameter in tool.parameters}
        unknown = set(values) - set(parameters)
        if unknown:
            raise ValueError(f"Unknown parameters for {tool_id}: {sorted(unknown)}")
        invalid = [
            parameter.id
            for parameter in tool.parameters
            if parameter.id in values and not parameter.validate(values[parameter.id])
        ]
        if invalid:
            raise ValueError(f"Invalid parameters for {tool_id}: {', '.join(invalid)}")


def processing_tool_definitions() -> tuple[ToolDefinition, ...]:
    """Return ToolDefinitions for all real DIP processing operations.

    These are separate from the 27 interaction-tool definitions so the
    original default_tool_registry() contract (tested by test_tool_registry.py)
    is not broken.  The composition root merges both sets.
    """
    return (
        ToolDefinition("negative", "Negative", "Filter", "Photographic negative", None),
        ToolDefinition(
            "gamma",
            "Gamma",
            "Filter",
            "Gamma correction",
            None,
            parameters=(ToolParameter("gamma", "Gamma", "number", 1.0, 0.05, 5.0),),
        ),
        ToolDefinition(
            "log_transform",
            "Log Transform",
            "Filter",
            "Logarithmic intensity transform",
            None,
            parameters=(ToolParameter("c", "Scale", "number", 1.0, 0.1, 10.0),),
        ),
        ToolDefinition(
            "brightness_contrast",
            "Brightness & Contrast",
            "Filter",
            "Linear brightness and contrast adjustment",
            None,
            parameters=(
                ToolParameter("alpha", "Contrast", "number", 1.0, 0.0, 3.0),
                ToolParameter("beta", "Brightness", "number", 0.0, -127.0, 127.0),
            ),
        ),
        ToolDefinition(
            "gaussian_blur",
            "Gaussian Blur",
            "Filter",
            "Smooth with Gaussian kernel",
            None,
            parameters=(
                ToolParameter("kernel_size", "Kernel Size", "integer", 5, 1, 51),
                ToolParameter("sigma", "Sigma", "number", 1.0, 0.1, 10.0),
            ),
        ),
        ToolDefinition(
            "median_blur",
            "Median Blur",
            "Filter",
            "Remove salt-and-pepper noise",
            None,
            parameters=(ToolParameter("kernel_size", "Kernel Size", "integer", 5, 1, 21),),
        ),
        ToolDefinition(
            "bilateral_filter",
            "Bilateral Filter",
            "Filter",
            "Edge-preserving smooth",
            None,
            parameters=(
                ToolParameter("diameter", "Diameter", "integer", 9, 1, 25),
                ToolParameter("sigma_color", "Sigma Color", "number", 75.0, 1.0, 200.0),
                ToolParameter("sigma_space", "Sigma Space", "number", 75.0, 1.0, 200.0),
            ),
        ),
        ToolDefinition("sobel", "Sobel", "Filter", "Sobel edge detection", None),
        ToolDefinition(
            "canny",
            "Canny",
            "Filter",
            "Canny edge detection",
            None,
            parameters=(
                ToolParameter("threshold1", "Low threshold", "number", 50.0, 0.0, 255.0),
                ToolParameter("threshold2", "High threshold", "number", 150.0, 0.0, 255.0),
            ),
        ),
        ToolDefinition("laplacian", "Laplacian", "Filter", "Laplacian edge/sharpening", None),
        ToolDefinition(
            "histogram_equalization",
            "Histogram Equalization",
            "Filter",
            "Global contrast enhancement",
            None,
        ),
        ToolDefinition(
            "clahe",
            "CLAHE",
            "Filter",
            "Adaptive histogram equalization",
            None,
            parameters=(
                ToolParameter("clip_limit", "Clip Limit", "number", 2.0, 0.5, 10.0),
                ToolParameter("tile_size", "Tile Size", "integer", 8, 2, 32),
            ),
        ),
        ToolDefinition(
            "erode",
            "Erode",
            "Filter",
            "Morphological erosion",
            None,
            parameters=(ToolParameter("kernel_size", "Kernel Size", "integer", 3, 1, 21),),
        ),
        ToolDefinition(
            "dilate",
            "Dilate",
            "Filter",
            "Morphological dilation",
            None,
            parameters=(ToolParameter("kernel_size", "Kernel Size", "integer", 3, 1, 21),),
        ),
        ToolDefinition(
            "morph_open",
            "Morph. Open",
            "Filter",
            "Opening: erode then dilate",
            None,
            parameters=(ToolParameter("kernel_size", "Kernel Size", "integer", 3, 1, 21),),
        ),
        ToolDefinition(
            "morph_close",
            "Morph. Close",
            "Filter",
            "Closing: dilate then erode",
            None,
            parameters=(ToolParameter("kernel_size", "Kernel Size", "integer", 3, 1, 21),),
        ),
        ToolDefinition("grayscale", "Grayscale", "Filter", "Convert to grayscale", None),
        ToolDefinition(
            "hue_saturation",
            "Hue & Saturation",
            "Filter",
            "Adjust hue, saturation, lightness",
            None,
            parameters=(
                ToolParameter("hue_shift", "Hue", "number", 0.0, -180.0, 180.0),
                ToolParameter("saturation_scale", "Saturation", "number", 1.0, 0.0, 3.0),
                ToolParameter("lightness_offset", "Lightness", "number", 0.0, -100.0, 100.0),
            ),
        ),
    )


def default_tool_registry() -> InMemoryToolRegistry:
    """Return the 27 canonical interaction-tool definitions.

    This function's output is covered by test_tool_registry.py.
    Processing-operation tools are registered separately via
    processing_tool_definitions() during composition.
    """
    return InMemoryToolRegistry(
        (
            ToolDefinition("select", "Select", "General", "Select and move objects", "V"),
            ToolDefinition(
                "selection", "Selection", "Selection", "Create a rectangular selection", "M"
            ),
            ToolDefinition(
                "ellipse_selection",
                "Ellipse selection",
                "Selection",
                "Create an elliptical selection",
                "O",
            ),
            ToolDefinition(
                "lasso", "Lasso", "Selection", "Create a freehand selection", "L"
            ),
            ToolDefinition(
                "polygon_selection",
                "Polygon selection",
                "Selection",
                "Create a polygon selection",
                "P",
            ),
            ToolDefinition(
                "color_selection",
                "Color selection",
                "Selection",
                "Select pixels by color",
                None,
            ),
            ToolDefinition(
                "crop",
                "Crop",
                "Transform",
                "Crop the active document",
                "C",
                parameters=(
                    ToolParameter("x", "X", "integer", 0, 0, 10000),
                    ToolParameter("y", "Y", "integer", 0, 0, 10000),
                    ToolParameter("width", "Width", "integer", 400, 1, 10000),
                    ToolParameter("height", "Height", "integer", 300, 1, 10000),
                ),
            ),
            ToolDefinition(
                "move", "Move", "Transform", "Move the active layer or selection", None
            ),
            ToolDefinition(
                "transform",
                "Transform",
                "Transform",
                "Scale, rotate, and transform content",
                None,
            ),
            ToolDefinition(
                "rotate",
                "Rotate",
                "Transform",
                "Rotate the active layer or selection",
                None,
                parameters=(
                    ToolParameter(
                        "degrees",
                        "Angle",
                        "choice",
                        "90",
                        choices=("90", "180", "270"),
                    ),
                ),
            ),
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
            ToolDefinition(
                "brush", "Brush", "Paint", "Paint with a soft or hard brush", "Shift+B"
            ),
            ToolDefinition("pencil", "Pencil", "Paint", "Draw hard-edged strokes", None),
            ToolDefinition(
                "eraser", "Eraser", "Paint", "Erase pixels or layer content", "Shift+E"
            ),
            ToolDefinition("fill", "Fill", "Paint", "Fill a connected region", "F"),
            ToolDefinition(
                "clone", "Clone stamp", "Retouch", "Clone pixels from a source point", None
            ),
            ToolDefinition("hand", "Hand", "Navigation", "Pan the canvas", "H"),
            ToolDefinition("zoom", "Zoom", "Navigation", "Zoom the canvas", "Z"),
            ToolDefinition("eyedropper", "Eyedropper", "Sampling", "Sample a color", "I"),
            ToolDefinition("text", "Text", "Vector", "Create text", "T"),
            ToolDefinition("shape", "Shape", "Vector", "Create a shape", "U"),
            ToolDefinition(
                "histogram",
                "Histogram",
                "Analysis",
                "Inspect image intensity distribution",
                None,
            ),
            ToolDefinition(
                "threshold",
                "Threshold",
                "Analysis",
                "Create a binary threshold preview",
                None,
                parameters=(
                    ToolParameter(
                        "method",
                        "Method",
                        "choice",
                        "Binary",
                        choices=("Binary", "Otsu"),
                    ),
                    ToolParameter("threshold_value", "Threshold", "integer", 128, 0, 255),
                    ToolParameter("inverse", "Inverse", "boolean", False),
                ),
            ),
            ToolDefinition(
                "morphology",
                "Morphology",
                "Analysis",
                "Apply morphological analysis",
                None,
                parameters=(
                    ToolParameter(
                        "operation",
                        "Operation",
                        "choice",
                        "Erode",
                        choices=("Erode", "Dilate", "Open", "Close"),
                    ),
                    ToolParameter("kernel_size", "Kernel Size", "integer", 3, 1, 31),
                ),
            ),
            ToolDefinition(
                "segment",
                "Segmentation",
                "Analysis",
                "Segment image regions",
                None,
                parameters=(
                    ToolParameter("clusters", "Regions", "integer", 3, 2, 10),
                ),
            ),
        )
    )
