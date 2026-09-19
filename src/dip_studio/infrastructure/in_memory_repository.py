"""Test/development adapter; filesystem and project formats belong in infrastructure."""

from dip_studio.domain.entities import ImageDocument


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, ImageDocument] = {}

    def save(self, document: ImageDocument) -> None:
        self._documents[document.name] = document

    def get(self, name: str) -> ImageDocument | None:
        return self._documents.get(name)
