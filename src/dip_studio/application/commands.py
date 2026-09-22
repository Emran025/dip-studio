"""Command boundary shared by menu, keyboard, toolbar, and automation."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from dip_studio.application.session import DocumentSession
from dip_studio.core.errors import ProcessingError
from dip_studio.domain.model import AppliedOperation, ImageDocument, Layer, LayerId
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
    """Records a pixel-level processing operation and its result in the layer.

    Targets the layer identified by *layer_id* when provided; falls back to the
    first layer with a pixel buffer so callers that do not yet track selection
    continue to work without changes.
    """

    label = "Apply processing"

    def __init__(
        self,
        processing: "ProcessingEngine",  # type: ignore[type-arg]
        request: ProcessingRequest,
        layer_id: LayerId | None = None,
    ) -> None:
        self._processing = processing
        self._request = request
        self._layer_id = layer_id
        # Snapshot the complete document before any mutation so undo is exact.
        self._previous_document: ImageDocument | None = None

    def _find_target_layer(self, document: ImageDocument) -> Layer | None:
        """Return the layer to process, respecting *layer_id* when set."""
        if self._layer_id is not None:
            # Find the specific requested layer that also has a buffer.
            for la in document.layers:
                if la.id == self._layer_id and la.buffer_id is not None:
                    return la
            # Requested layer exists but has no buffer — nothing to process.
            return None
        # Fallback: first buffered layer (legacy / unselected-layer callers).
        return next((la for la in document.layers if la.buffer_id is not None), None)

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        # Snapshot the document before any change so undo restores it exactly.
        self._previous_document = document

        layer = self._find_target_layer(document)
        if layer is None or layer.buffer_id is None:
            raise ProcessingError(
                f"Cannot apply '{self._request.operation}': no buffered target layer"
            )

        new_buffer_id = self._processing.run(layer.buffer_id, self._request)
        if not isinstance(new_buffer_id, str) or not new_buffer_id:
            raise ProcessingError(
                f"Processor '{self._request.operation}' returned an invalid buffer"
            )
        if new_buffer_id == layer.buffer_id:
            raise ProcessingError(
                f"Processor '{self._request.operation}' produced no new result buffer"
            )

        # Use CoW .changed() to preserve ALL layer properties:
        # mask_id, blend_mode, transform, locked, opacity, visible.
        new_layer = layer.changed(buffer_id=new_buffer_id)
        new_layers = tuple(
            new_layer if la.id == layer.id else la
            for la in document.layers
        )
        new_doc = document.changed(
            layers=new_layers,
            operations=document.operations
            + (AppliedOperation(self._request.operation, self._request.parameters),)
        )
        session.replace(new_doc)

    def undo(self, session: DocumentSession) -> None:
        """Restore the document to its exact pre-execution state."""
        if self._previous_document is not None:
            session.replace(self._previous_document)
