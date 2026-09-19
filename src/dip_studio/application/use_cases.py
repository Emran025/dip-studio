"""Small, testable application use cases."""

from dip_studio.application.ports import DocumentRepository
from dip_studio.domain.entities import DocumentId, ImageDocument


class CreateDocument:
    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    def execute(self, name: str) -> ImageDocument:
        document = ImageDocument(DocumentId(), name.strip())
        if not document.name:
            raise ValueError("Document name cannot be empty")
        self._repository.save(document)
        return document
