"""Command boundary shared by menu, keyboard, toolbar, and automation."""

from typing import Protocol

from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import ImageDocument


class Command(Protocol):
    def execute(self, session: DocumentSession) -> None: ...
    def undo(self, session: DocumentSession) -> None: ...


class ReplaceDocument:
    def __init__(self, document: ImageDocument) -> None:
        self.document = document
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        self._previous = session.document
        session.replace(self.document)

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Command has not executed")
        session.replace(self._previous)
