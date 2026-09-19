"""Framework-independent domain entities."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DocumentId:
    value: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class ImageDocument:
    """The editable document aggregate; UI and libraries do not own this state."""

    id: DocumentId
    name: str
    source_path: str | None = None
    revision: int = 0

    def renamed(self, name: str) -> "ImageDocument":
        if not name.strip():
            raise ValueError("Document name cannot be empty")
        return ImageDocument(self.id, name.strip(), self.source_path, self.revision + 1)
