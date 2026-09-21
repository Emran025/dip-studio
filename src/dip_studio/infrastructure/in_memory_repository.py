"""In-memory document repository for tests and development."""
from __future__ import annotations

from dip_studio.domain.model import ImageDocument


class InMemoryDocumentRepository:
    """Volatile in-memory store; not for production."""

    def __init__(self) -> None:
        self._store: dict[str, ImageDocument] = {}

    def save(self, document: ImageDocument) -> None:
        self._store[document.name] = document

    def get(self, name: str) -> ImageDocument:
        try:
            return self._store[name]
        except KeyError as error:
            raise KeyError(f"Document not found: {name}") from error
