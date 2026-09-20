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


@dataclass(frozen=True, slots=True)
class Layer:
    id: LayerId
    name: str
    visible: bool = True
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip() or not 0.0 <= self.opacity <= 1.0:
            raise ValidationError("Layer name and opacity are invalid")


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
