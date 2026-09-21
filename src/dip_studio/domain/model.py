"""Framework-independent document model and invariants."""

from dataclasses import dataclass
from typing import NewType
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


@dataclass(frozen=True, slots=True)
class Layer:
    id: LayerId
    name: str
    visible: bool = True
    opacity: float = 1.0
    buffer_id: str | None = None   # reference into ImageDataStore
    mask_id: str | None = None     # reference to a Mask id
    blend_mode: str = "normal"     # "normal" | "multiply" | "screen" | "overlay" etc.
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
        transform: "Transform | None" = None,
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
            transform=self.transform if transform is None else transform,
            locked=self.locked if locked is None else locked,
        )


@dataclass(frozen=True, slots=True)
class Mask:
    """Soft mask with values in [0.0, 1.0] stored in DataStore.
    
    mode: 'reveal' (white = show) or 'hide' (black = show)
    """
    id: str  # UUID string
    name: str
    width: int
    height: int
    mode: str = "reveal"           # "reveal" | "hide"
    buffer_id: str | None = None   # float32 mask array in DataStore
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Mask dimensions must be positive")
        if self.mode not in ("reveal", "hide"):
            raise ValidationError("Mask mode must be 'reveal' or 'hide'")


@dataclass(frozen=True, slots=True)
class SelectionRect:
    """Rectangular selection region in image coordinates."""
    x: int
    y: int
    width: int
    height: int
    feather: float = 0.0  # pixel radius for soft edge

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Selection dimensions must be positive")
        if self.feather < 0:
            raise ValidationError("Feather radius must be non-negative")


@dataclass(frozen=True, slots=True)
class Transform:
    """Affine transform stored as (tx, ty, sx, sy, rotation, skew_x, skew_y).
    
    All transforms are relative to the layer's origin.
    rotation is in degrees.
    """
    tx: float = 0.0        # translation x
    ty: float = 0.0        # translation y
    sx: float = 1.0        # scale x
    sy: float = 1.0        # scale y
    rotation: float = 0.0  # degrees
    skew_x: float = 0.0
    skew_y: float = 0.0

    def __post_init__(self) -> None:
        if self.sx == 0 or self.sy == 0:
            raise ValidationError("Scale cannot be zero")

    @property
    def is_identity(self) -> bool:
        return (self.tx == 0.0 and self.ty == 0.0
                and self.sx == 1.0 and self.sy == 1.0
                and self.rotation == 0.0
                and self.skew_x == 0.0 and self.skew_y == 0.0)


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
    ) -> "ImageDocument":
        return ImageDocument(
            self.id,
            self.name if name is None else name,
            self.image if image is None else image,
            self.layers if layers is None else layers,
            self.revision + 1,
            self.saved_revision,
            self.operations if operations is None else operations,
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
        )


@dataclass(frozen=True, slots=True)
class Project:
    id: ProjectId
    name: str
    documents: tuple[ImageDocument, ...] = ()
    format_version: int = 1
