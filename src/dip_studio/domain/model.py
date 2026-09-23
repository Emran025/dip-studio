"""Framework-independent document model and invariants."""

from dataclasses import dataclass
from typing import Any, NewType
from uuid import UUID

from dip_studio.core.errors import ValidationError

ProjectId = NewType("ProjectId", UUID)
DocumentId = NewType("DocumentId", UUID)
LayerId = NewType("LayerId", UUID)


@dataclass(frozen=True, slots=True)
class ImageSpec:
    width: int
    height: int
    channels: int = 4
    bit_depth: int = 8
    color_space: str = "sRGB"
    has_alpha: bool = True

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.channels <= 0:
            raise ValidationError("Image dimensions and channels must be positive")

    def changed(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        channels: int | None = None,
        bit_depth: int | None = None,
        color_space: str | None = None,
        has_alpha: bool | None = None,
    ) -> "ImageSpec":
        return ImageSpec(
            width=self.width if width is None else width,
            height=self.height if height is None else height,
            channels=self.channels if channels is None else channels,
            bit_depth=self.bit_depth if bit_depth is None else bit_depth,
            color_space=self.color_space if color_space is None else color_space,
            has_alpha=self.has_alpha if has_alpha is None else has_alpha,
        )


_UNSET = object()


@dataclass(frozen=True, slots=True)
class Layer:
    id: LayerId
    name: str
    visible: bool = True
    opacity: float = 1.0
    buffer_id: str | None = None  # reference into ImageDataStore
    mask_id: str | None = None  # reference to a Mask id
    blend_mode: str = "normal"  # "normal" | "multiply" | "screen" | "overlay" etc.
    transform: "Transform | None" = None
    locked: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip() or not 0.0 <= self.opacity <= 1.0:
            raise ValidationError("Layer name and opacity are invalid")

    def changed(
        self,
        *,
        name: str | None = None,
        visible: bool | None = None,
        opacity: float | None = None,
        buffer_id: str | None = None,
        mask_id: str | None = None,
        blend_mode: str | None = None,
        transform: "Transform | None | object" = _UNSET,
        locked: bool | None = None,
    ) -> "Layer":
        return Layer(
            id=self.id,
            name=self.name if name is None else name,
            visible=self.visible if visible is None else visible,
            opacity=self.opacity if opacity is None else opacity,
            buffer_id=self.buffer_id if buffer_id is None else buffer_id,
            mask_id=self.mask_id if mask_id is None else mask_id,
            blend_mode=self.blend_mode if blend_mode is None else blend_mode,
            transform=self.transform if transform is _UNSET else transform,  # type: ignore[arg-type]
            locked=self.locked if locked is None else locked,
        )


@dataclass(frozen=True, slots=True)
class TextLayer(Layer):
    """A layer whose content is rendered from a text string.

    The text is kept editable (as string data) until the user explicitly
    rasterises it.  A pixel buffer is written to ``buffer_id`` by the
    infrastructure ``text_rasteriser`` on AddTextLayer / EditTextLayer.

    All fields per doc-06 (RTL/Arabic supported via ``direction``).
    """

    text: str = ""
    font_family: str = "Arial"
    font_size: int = 24
    bold: bool = False
    italic: bool = False
    color_rgba: tuple[int, int, int, int] = (0, 0, 0, 255)
    # Alignment: "left" | "center" | "right"
    alignment: str = "left"
    # Writing direction: "ltr" | "rtl"
    direction: str = "ltr"
    letter_spacing: float = 0.0  # extra spacing in pixels
    line_spacing: float = 1.2  # multiplier (1.0 = single, 1.5 = 1.5×)
    # Optional semi-transparent background behind text
    background_color: tuple[int, int, int, int] = (0, 0, 0, 0)

    def __post_init__(self) -> None:
        # Explicitly call parent __post_init__ to avoid Python 3.10
        # super()-in-slots-frozen-subclass MRO bug.
        Layer.__post_init__(self)
        if self.font_size <= 0:
            raise ValidationError("Font size must be positive")
        if self.alignment not in ("left", "center", "right"):
            raise ValidationError("alignment must be 'left', 'center', or 'right'")
        if self.direction not in ("ltr", "rtl"):
            raise ValidationError("direction must be 'ltr' or 'rtl'")


@dataclass(frozen=True, slots=True)
class ShapeLayer(Layer):
    """A layer whose content is a vector shape.

    The shape is stored as geometric data and rasterised on demand.
    ``shape_type``: ``rectangle`` | ``ellipse`` | ``polygon`` | ``line`` | ``path``
    """

    shape_type: str = "rectangle"
    stroke_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    fill_color: tuple[int, int, int, int] = (0, 0, 0, 0)
    stroke_width: float = 1.0
    # Polygon / path vertices stored as flat (x0,y0,x1,y1,...) tuple
    vertices: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        Layer.__post_init__(self)  # explicit call — avoids frozen+slots super() bug
        if self.stroke_width < 0:
            raise ValidationError("Stroke width must be non-negative")
        if self.shape_type not in ("rectangle", "ellipse", "line", "polygon"):
            raise ValidationError(f"Unsupported shape type: {self.shape_type}")
        if self.buffer_id is None and (len(self.vertices) < 4 or len(self.vertices) % 2 != 0):
            raise ValidationError("Shape geometry must contain coordinate pairs")


@dataclass(frozen=True, slots=True)
class AdjustmentLayer(Layer):
    """Non-destructive adjustment applied to all layers below it.

    ``adjustment_type`` maps to a registered processor operation string,
    e.g. ``brightness_contrast``, ``hue_saturation``.
    """

    adjustment_type: str = ""
    adjustment_params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FilterLayer(AdjustmentLayer):
    """Compatibility alias for filter-style non-destructive adjustments.

    ``filter_type`` is kept as the canonical operation name for filters while
    ``adjustment_type`` is retained for generic adjustment layers.
    """

    filter_type: str = ""
    filter_params: tuple[tuple[str, str], ...] = ()

    @property
    def effective_operation(self) -> str:
        return self.adjustment_type or self.filter_type

    @property
    def effective_parameters(self) -> tuple[tuple[str, str], ...]:
        if self.adjustment_params:
            return self.adjustment_params
        return self.filter_params


@dataclass(frozen=True, slots=True)
class GroupLayer(Layer):
    """Container grouping ordered child layer IDs.

    ``pass_through=True``: children blend directly into the parent stack.
    ``pass_through=False``: children composite to an internal buffer first,
    enabling group-level opacity / blend mode.
    """

    children: tuple[LayerId, ...] = ()
    pass_through: bool = True

    def __post_init__(self) -> None:
        Layer.__post_init__(self)
        seen: set[LayerId] = set()
        for child_id in self.children:
            if child_id in seen:
                raise ValidationError("Group children must be unique")
            seen.add(child_id)


# Union alias — use for type-narrowing where a specific layer kind matters.
AnyLayer = Layer | TextLayer | ShapeLayer | AdjustmentLayer | FilterLayer | GroupLayer


@dataclass(frozen=True, slots=True)
class ImageLayer(Layer):
    """Concrete image-backed layer used as the default bitmap layer type.

    This is kept as a compatibility alias for the flat document model: the
    document still stores a tuple of layers, but callers can inspect or create a
    concrete image-backed variant when they need stricter invariants.
    """

    def __post_init__(self) -> None:
        Layer.__post_init__(self)
        if self.buffer_id is None:
            raise ValidationError("ImageLayer requires a buffer_id")


@dataclass(frozen=True, slots=True)
class LayerTree:
    """Tree view over a document's layers with validation for cycles and children."""

    layers: tuple[Layer, ...]

    def __post_init__(self) -> None:
        ids = [layer.id for layer in self.layers]
        if len(ids) != len(set(ids)):
            raise ValidationError("Layer ids must be unique within a layer tree")
        by_id = {layer.id: layer for layer in self.layers}
        seen: set[LayerId] = set()

        def walk(layer: Layer) -> None:
            if layer.id in seen:
                raise ValidationError(f"Layer cycle detected at '{layer.name}'")
            seen.add(layer.id)
            if isinstance(layer, GroupLayer):
                for child_id in layer.children:
                    child = by_id.get(child_id)
                    if child is None:
                        raise ValidationError(
                            f"Group layer '{layer.name}' references missing child '{child_id}'"
                        )
                    walk(child)

        for layer in self.layers:
            if isinstance(layer, GroupLayer):
                walk(layer)

    def flat(self) -> tuple[Layer, ...]:
        return self.layers

    def top_level(self) -> tuple[Layer, ...]:
        ids = {
            child_id
            for layer in self.layers
            if isinstance(layer, GroupLayer)
            for child_id in layer.children
        }
        return tuple(layer for layer in self.layers if layer.id not in ids)


@dataclass(frozen=True, slots=True)
class Mask:
    """Soft mask with values in [0.0, 1.0] stored in DataStore.

    mode: 'reveal' (white = show) or 'hide' (black = show)
    """

    id: str  # UUID string
    name: str
    width: int
    height: int
    mode: str = "reveal"  # "reveal" | "hide"
    buffer_id: str | None = None  # float32 mask array in DataStore
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Mask dimensions must be positive")
        if self.mode not in ("reveal", "hide"):
            raise ValidationError("Mask mode must be 'reveal' or 'hide'")


@dataclass(frozen=True, slots=True)
class SelectionRect:
    """Selection region in image coordinates.

    ``kind``: ``rectangle`` | ``ellipse`` | ``lasso`` | ``polygon``

    For non-rectangular kinds, ``mask_buffer_id`` points to a boolean
    (uint8) mask array stored in ``ImageDataStore`` where 255 = selected.
    The bounding ``(x, y, width, height)`` is always set for quick hit-testing
    regardless of the selection kind.
    """

    x: int
    y: int
    width: int
    height: int
    feather: float = 0.0  # pixel radius for soft edge
    kind: str = "rectangle"  # "rectangle" | "ellipse" | "lasso" | "polygon"
    mask_buffer_id: str | None = None  # non-rect selection mask (uint8 H×W)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Selection dimensions must be positive")
        if self.feather < 0:
            raise ValidationError("Feather radius must be non-negative")
        if self.kind not in (
            "rectangle",
            "ellipse",
            "lasso",
            "polygon",
            "color_selection",
            "color",
        ):
            raise ValidationError("Selection kind must be rectangle, ellipse, lasso, or polygon")


@dataclass(frozen=True, slots=True)
class Transform:
    """Affine transform stored as (tx, ty, sx, sy, rotation, skew_x, skew_y).

    All transforms are relative to the layer's origin.
    rotation is in degrees.
    """

    tx: float = 0.0  # translation x
    ty: float = 0.0  # translation y
    sx: float = 1.0  # scale x
    sy: float = 1.0  # scale y
    rotation: float = 0.0  # degrees
    skew_x: float = 0.0
    skew_y: float = 0.0

    def __post_init__(self) -> None:
        if self.sx == 0 or self.sy == 0:
            raise ValidationError("Scale cannot be zero")

    @property
    def is_identity(self) -> bool:
        return (
            self.tx == 0.0
            and self.ty == 0.0
            and self.sx == 1.0
            and self.sy == 1.0
            and self.rotation == 0.0
            and self.skew_x == 0.0
            and self.skew_y == 0.0
        )


@dataclass(frozen=True, slots=True)
class AppliedOperation:
    operation: str
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ImageDocument:
    id: DocumentId
    name: str
    image: ImageSpec
    layers: tuple[Layer, ...] = ()
    revision: int = 0
    saved_revision: int = 0
    operations: tuple[AppliedOperation, ...] = ()
    masks: tuple[Mask, ...] = ()
    selections: tuple[SelectionRect, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    workspace_metadata: tuple[tuple[str, str], ...] = ()
    buffer_metadata: tuple[tuple[str, dict[str, Any]], ...] = ()
    cv_objects: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("Document name cannot be empty")

    @property
    def is_dirty(self) -> bool:
        return self.revision != self.saved_revision

    def changed(
        self,
        *,
        name: str | None = None,
        image: ImageSpec | None = None,
        layers: tuple[Layer, ...] | None = None,
        operations: tuple[AppliedOperation, ...] | None = None,
        masks: tuple[Mask, ...] | None = None,
        selections: tuple[SelectionRect, ...] | None = None,
        metadata: tuple[tuple[str, str], ...] | None = None,
        workspace_metadata: tuple[tuple[str, str], ...] | None = None,
        buffer_metadata: tuple[tuple[str, dict[str, Any]], ...] | None = None,
        cv_objects: tuple[dict[str, Any], ...] | None = None,
    ) -> "ImageDocument":
        return ImageDocument(
            self.id,
            self.name if name is None else name,
            self.image if image is None else image,
            self.layers if layers is None else layers,
            self.revision + 1,
            self.saved_revision,
            self.operations if operations is None else operations,
            self.masks if masks is None else masks,
            self.selections if selections is None else selections,
            self.metadata if metadata is None else metadata,
            self.workspace_metadata if workspace_metadata is None else workspace_metadata,
            self.buffer_metadata if buffer_metadata is None else buffer_metadata,
            self.cv_objects if cv_objects is None else cv_objects,
        )

    def marked_saved(self) -> "ImageDocument":
        return ImageDocument(
            self.id,
            self.name,
            self.image,
            self.layers,
            self.revision,
            self.revision,
            self.operations,
            self.masks,
            self.selections,
            self.metadata,
            self.workspace_metadata,
            self.buffer_metadata,
            self.cv_objects,
        )

    @property
    def layer_tree(self) -> LayerTree:
        return LayerTree(self.layers)


@dataclass(frozen=True, slots=True)
class Project:
    id: ProjectId
    name: str
    documents: tuple[ImageDocument, ...] = ()
    format_version: int = 1
