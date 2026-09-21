"""Application ports — abstract interfaces that infrastructure must implement."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dip_studio.domain.model import ImageDocument, ImageSpec


class DocumentRepository(Protocol):
    """Storage contract for a single document."""

    def save(self, document: ImageDocument) -> None: ...
    def get(self, name: str) -> ImageDocument: ...


class ProjectStore(Protocol):
    """Storage contract for the project file format."""

    def save(self, document: ImageDocument, path: Path) -> None: ...
    def load(self, path: Path) -> ImageDocument: ...


@dataclass(frozen=True, slots=True)
class ImportedImage:
    """Value object returned by an image importer."""

    name: str
    spec: ImageSpec
    preview: bytes | None = None
    buffer_id: str | None = None  # reference into ImageDataStore


class ImageImporter(Protocol):
    extensions: tuple[str, ...]

    def import_image(self, path: Path) -> ImportedImage: ...
