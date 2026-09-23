"""High-level application use cases."""

from __future__ import annotations

from dip_studio.application.ports import DocumentRepository
from dip_studio.domain.factories import new_document
from dip_studio.domain.model import ImageDocument


class CreateDocument:
    """Create a new blank document and persist it."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    def execute(self, name: str) -> ImageDocument:
        name = name.strip()
        if not name:
            raise ValueError("Document name cannot be empty")
        document = new_document(name, 800, 600)
        self._repository.save(document)
        return document
