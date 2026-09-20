"""Single owner of the active document state; views receive snapshots."""

from dataclasses import dataclass

from dip_studio.domain.model import ImageDocument


@dataclass
class DocumentSession:
    _document: ImageDocument | None = None

    @property
    def active_document(self) -> ImageDocument | None:
        return self._document

    def open(self, document: ImageDocument) -> None:
        self._document = document

    @property
    def document(self) -> ImageDocument:
        if self._document is None:
            raise RuntimeError("No active document")
        return self._document

    def replace(self, document: ImageDocument) -> None:
        if self._document is None or document.id != self._document.id:
            raise ValueError("Document identity mismatch")
        self._document = document
