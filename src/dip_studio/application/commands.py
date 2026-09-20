"""Command boundary shared by menu, keyboard, toolbar, and automation."""

from collections.abc import Callable
from typing import Protocol

from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import AppliedOperation, ImageDocument
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.engine import ProcessingEngine


class Command(Protocol):
    def execute(self, session: DocumentSession) -> None: ...
    def undo(self, session: DocumentSession) -> None: ...


class CommandHandler:
    """Single dispatch point for menu, keyboard, toolbar, and automation."""

    def __init__(self, session: DocumentSession) -> None:
        self._session = session
        self._commands: dict[str, Callable[[], Command]] = {}

    def register(self, command_id: str, factory: Callable[[], Command]) -> None:
        if not command_id.strip():
            raise ValueError("Command id cannot be empty")
        self._commands[command_id] = factory

    def execute(self, command_id: str) -> Command:
        try:
            command = self._commands[command_id]()
        except KeyError as error:
            raise KeyError(f"Unknown command: {command_id}") from error
        command.execute(self._session)
        return command


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


class ApplyProcessing:
    def __init__(self, engine: ProcessingEngine[str, str], request: ProcessingRequest) -> None:
        self._engine = engine
        self._request = request
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        self._engine.run("document", self._request)
        self._previous = document
        operation = AppliedOperation(self._request.operation, self._request.parameters)
        session.replace(document.changed(operations=document.operations + (operation,)))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Processing command has not executed")
        session.replace(self._previous)
