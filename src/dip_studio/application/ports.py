"""Ports owned by the application layer; adapters implement them."""

from typing import Protocol

from dip_studio.domain.entities import ImageDocument


class DocumentRepository(Protocol):
    def save(self, document: ImageDocument) -> None: ...
    def get(self, name: str) -> ImageDocument | None: ...
