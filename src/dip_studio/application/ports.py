"""Ports owned by the application layer; adapters implement them."""

from typing import Protocol
from dataclasses import dataclass
from pathlib import Path

from dip_studio.domain.model import ImageDocument, ImageSpec


class DocumentRepository(Protocol):
    def save(self, document: ImageDocument) -> None: ...
    def get(self, name: str) -> ImageDocument | None: ...


class ProjectStore(Protocol):
    def save(self, document: ImageDocument, path: Path) -> None: ...
    def load(self, path: Path) -> ImageDocument: ...


@dataclass(frozen=True, slots=True)
class ImportedImage:
    name: str
    spec: ImageSpec
    preview: bytes | None = None


class ImageImporter(Protocol):
    extensions: tuple[str, ...]

    def import_image(self, path: Path) -> ImportedImage: ...
