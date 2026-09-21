"""Application-facing editor orchestration for the first vertical slice."""

from pathlib import Path

from dip_studio.application.commands import ApplyProcessing
from dip_studio.application.history import UndoRedoHistory
from dip_studio.application.layer_commands import (
    AddLayer,
    ChangeLayer,
    ChangeLayers,
    DuplicateLayer,
    MoveLayer,
    PasteLayers,
    RemoveLayer,
    RemoveLayers,
    RenameLayer,
)
from dip_studio.application.ports import ImageImporter, ProjectStore
from dip_studio.application.session import DocumentSession
from dip_studio.application.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    default_tool_registry,
)
from dip_studio.domain.factories import document_from_import, new_document
from dip_studio.domain.model import ImageDocument, Layer, LayerId
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.engine import ProcessingEngine
from dip_studio.rendering.ports import RenderEngine, RenderRequest


class _OperationProcessor:
    def __init__(self, operation: str) -> None:
        self.operation = operation

    def validate(self, request: ProcessingRequest) -> None:
        if request.operation != self.operation:
            raise ValueError("operation mismatch")

    def process(self, image: str, request: ProcessingRequest) -> str:
        return image


class EditorController:
    """Owns editor state and exposes UI-neutral operations to presentation."""

    def __init__(
        self,
        renderer: RenderEngine,
        project_store: ProjectStore | None = None,
        image_importer: ImageImporter | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._renderer = renderer
        self._project_store = project_store
        self._image_importer = image_importer
        self._tool_registry = tool_registry or default_tool_registry()
        self._session = DocumentSession()
        self._sessions: dict[str, DocumentSession] = {}
        self._histories: dict[str, UndoRedoHistory] = {}
        self._clipboard: tuple[Layer, ...] = ()
        self._previews: dict[str, bytes] = {}
        self._processing = ProcessingEngine(
            {
                tool.id: _OperationProcessor(tool.id)
                for tool in self._tool_registry.list()
            }
        )

    @property
    def document(self) -> ImageDocument | None:
        return self._session.active_document

    @property
    def tools(self) -> tuple[ToolDefinition, ...]:
        return self._tool_registry.list()

    def create_document(self, name: str, width: int, height: int) -> ImageDocument:
        document = new_document(name, width, height)
        self._activate_new_document(document)
        return document

    def open_project(self, path: Path) -> ImageDocument:
        if self._project_store is None:
            raise RuntimeError("Project storage is not configured")
        document = self._project_store.load(path)
        self._activate_new_document(document)
        return document

    def open_image(self, path: Path) -> ImageDocument:
        if self._image_importer is None:
            raise RuntimeError("Image import is not configured")
        imported = self._image_importer.import_image(path)
        document = document_from_import(imported.name, imported.spec, path.stem)
        self._activate_new_document(document)
        if imported.preview is not None:
            self._previews[str(document.id)] = imported.preview
        return document

    @property
    def open_documents(self) -> tuple[ImageDocument, ...]:
        return tuple(
            document
            for session in self._sessions.values()
            if (document := session.active_document) is not None
        )

    def activate_document(self, document_id: object) -> ImageDocument:
        key = str(document_id)
        session = self._sessions.get(key)
        if session is None or session.active_document is None:
            raise KeyError("Document is not open")
        self._session = session
        return session.document

    def close_document(self, document_id: object) -> None:
        key = str(document_id)
        if key not in self._sessions:
            raise KeyError("Document is not open")
        del self._sessions[key]
        self._histories.pop(key, None)
        if self._sessions:
            self._session = next(iter(self._sessions.values()))
        else:
            self._session = DocumentSession()

    def copy_layers(self, layer_ids: tuple[LayerId, ...]) -> int:
        document = self._session.document
        selected = set(layer_ids)
        self._clipboard = tuple(layer for layer in document.layers if layer.id in selected)
        return len(self._clipboard)

    def paste_layers(self) -> ImageDocument:
        if not self._clipboard:
            raise RuntimeError("Clipboard does not contain layers")
        from uuid import uuid4

        layers = tuple(
            Layer(LayerId(uuid4()), f"{layer.name} copy", layer.visible, layer.opacity)
            for layer in self._clipboard
        )
        document = self._session.document
        self._history_for_active().execute(
            PasteLayers(layers, len(document.layers)), self._session
        )
        return self._session.document

    def save_project(self, path: Path) -> ImageDocument:
        if self._project_store is None:
            raise RuntimeError("Project storage is not configured")
        document = self._session.document
        self._project_store.save(document, path)
        saved = document.marked_saved()
        self._session.replace(saved)
        return saved

    def _activate_new_document(self, document: ImageDocument) -> None:
        session = DocumentSession(document)
        key = str(document.id)
        self._sessions[key] = session
        self._histories[key] = UndoRedoHistory()
        self._session = session

    def preview(self, viewport_width: int, viewport_height: int, zoom: float = 1.0) -> bytes:
        document = self.document
        if document is None:
            raise RuntimeError("No active document")
        preview = self._previews.get(str(document.id))
        if preview is not None:
            return preview
        return self._renderer.render(
            RenderRequest(str(document.id), viewport_width, viewport_height, zoom)
        )

    def preview_processing(self, operation: str, parameters: dict[str, object]) -> str:
        request = self._request(operation, parameters)
        return self._processing.run("document", request)

    def apply_processing(self, operation: str, parameters: dict[str, object]) -> ImageDocument:
        request = self._request(operation, parameters)
        self._history_for_active().execute(
            ApplyProcessing(self._processing, request), self._session
        )
        return self._session.document

    def undo(self) -> ImageDocument:
        self._history_for_active().undo(self._session)
        return self._session.document

    def redo(self) -> ImageDocument:
        self._history_for_active().redo(self._session)
        return self._session.document

    def set_layer_visibility(self, layer_id: LayerId, visible: bool) -> ImageDocument:
        self._history_for_active().execute(ChangeLayer(layer_id, visible=visible), self._session)
        return self._session.document

    def set_layers_visibility(self, layer_ids: tuple[LayerId, ...], visible: bool) -> ImageDocument:
        self._history_for_active().execute(ChangeLayers(layer_ids, visible=visible), self._session)
        return self._session.document

    def set_layer_opacity(self, layer_id: LayerId, opacity: float) -> ImageDocument:
        self._history_for_active().execute(ChangeLayer(layer_id, opacity=opacity), self._session)
        return self._session.document

    def set_layers_opacity(self, layer_ids: tuple[LayerId, ...], opacity: float) -> ImageDocument:
        self._history_for_active().execute(ChangeLayers(layer_ids, opacity=opacity), self._session)
        return self._session.document

    def rename_layer(self, layer_id: LayerId, name: str) -> ImageDocument:
        self._history_for_active().execute(RenameLayer(layer_id, name), self._session)
        return self._session.document

    def add_layer(self, name: str = "Layer") -> ImageDocument:
        self._history_for_active().execute(AddLayer(name), self._session)
        return self._session.document

    def duplicate_layer(self, layer_id: LayerId) -> ImageDocument:
        document = self._session.document
        index = next((i for i, layer in enumerate(document.layers) if layer.id == layer_id), None)
        if index is None:
            raise KeyError("Layer does not exist")
        self._history_for_active().execute(
            DuplicateLayer(document.layers[index], index + 1), self._session
        )
        return self._session.document

    def remove_layer(self, layer_id: LayerId) -> ImageDocument:
        self._history_for_active().execute(RemoveLayer(layer_id), self._session)
        return self._session.document

    def remove_layers(self, layer_ids: tuple[LayerId, ...]) -> ImageDocument:
        self._history_for_active().execute(RemoveLayers(layer_ids), self._session)
        return self._session.document

    def move_layer(self, layer_id: LayerId, delta: int) -> ImageDocument:
        self._history_for_active().execute(MoveLayer(layer_id, delta), self._session)
        return self._session.document

    @staticmethod
    def _request(operation: str, parameters: dict[str, object]) -> ProcessingRequest:
        return ProcessingRequest(
            operation,
            tuple((key, str(value)) for key, value in sorted(parameters.items())),
        )

    def _history_for_active(self) -> UndoRedoHistory:
        document = self._session.active_document
        if document is None:
            raise RuntimeError("No active document")
        return self._histories.setdefault(str(document.id), UndoRedoHistory())
