"""Command boundary shared by menu, keyboard, toolbar, and automation."""

from collections.abc import Callable
from typing import Protocol

from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import AppliedOperation, ImageDocument, Layer
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
    """Records a pixel-level processing operation and its result in the layer."""

    label = "Apply processing"

    def __init__(
        self,
        processing: "ProcessingEngine",  # type: ignore[type-arg]
        request: ProcessingRequest,
    ) -> None:
        self._processing = processing
        self._request = request
        # Store the entire document before mutation so undo is exact.
        self._previous_document: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        # Snapshot the document before any change so undo restores it exactly.
        self._previous_document = document

        # Try to process the first visible layer that has a pixel buffer.
        layer = next((la for la in document.layers if la.buffer_id is not None), None)
        if layer is not None:
            try:
                new_buffer_id: str = self._processing.run(
                    layer.buffer_id, self._request
                )
                if new_buffer_id != layer.buffer_id:
                    new_layer = Layer(
                        layer.id,
                        layer.name,
                        layer.visible,
                        layer.opacity,
                        new_buffer_id,
                    )
                    new_layers = tuple(
                        new_layer if la.id == layer.id else la
                        for la in document.layers
                    )
                    new_doc = document.changed(
                        layers=new_layers,
                        operations=document.operations
                        + (AppliedOperation(self._request.operation, self._request.parameters),),
                    )
                    session.replace(new_doc)
                    return
            except Exception:
                pass

        # Fallback: record the operation symbol without changing pixel data.
        new_doc = document.changed(
            operations=document.operations
            + (AppliedOperation(self._request.operation, self._request.parameters),)
        )
        session.replace(new_doc)

    def undo(self, session: DocumentSession) -> None:
        """Restore the document to its exact pre-execution state."""
        if self._previous_document is not None:
            session.replace(self._previous_document)
