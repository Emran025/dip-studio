"""Application-facing editor orchestration for the first vertical slice."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from dip_studio.application.commands import ApplyProcessing
from dip_studio.application.history import UndoRedoHistory
from dip_studio.core.errors import PersistenceError
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

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore


class EditorController:
    """Owns editor state and exposes UI-neutral operations to presentation."""

    def __init__(
        self,
        renderer: RenderEngine,
        project_store: ProjectStore | None = None,
        image_importer: ImageImporter | None = None,
        tool_registry: ToolRegistry | None = None,
        data_store: ImageDataStore | None = None,
        processing_engine: ProcessingEngine | None = None,  # type: ignore[type-arg]
    ) -> None:
        self._renderer = renderer
        self._project_store = project_store
        self._image_importer = image_importer
        self._tool_registry = tool_registry or default_tool_registry()
        if data_store is None and image_importer is not None:
            data_store = getattr(image_importer, "_data_store", None)
        elif data_store is not None and image_importer is not None and getattr(image_importer, "_data_store", None) is None:
            image_importer._data_store = data_store
        self._data_store = data_store
        self._session = DocumentSession()
        self._sessions: dict[str, DocumentSession] = {}
        self._histories: dict[str, UndoRedoHistory] = {}
        self._clipboard: tuple[Layer, ...] = ()
        self._previews: dict[str, bytes] = {}
        self._active_tool_id: str = ""
        if processing_engine is not None:
            self._processing = processing_engine
        else:
            from dip_studio.processing.engine import ProcessingEngine as _PE
            self._processing = _PE({})

    @property
    def document(self) -> ImageDocument | None:
        return self._session.active_document

    @property
    def tools(self) -> tuple[ToolDefinition, ...]:
        return self._tool_registry.list()

    @property
    def data_store(self) -> ImageDataStore | None:
        return self._data_store

    @property
    def active_tool_id(self) -> str:
        """The currently selected tool id, or empty string if none."""
        return self._active_tool_id

    def set_active_tool(self, tool_id: str) -> None:
        """Activate a tool by id. Validates it exists in the registry."""
        if tool_id and not any(t.id == tool_id for t in self._tool_registry.list()):
            raise KeyError(f"Tool not found: {tool_id}")
        self._active_tool_id = tool_id

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
        # Pass buffer_id into the background layer so the renderer can use it
        document = document_from_import(
            imported.name, imported.spec, path.stem, imported.buffer_id
        )
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

    def export_image(self, path: Path, quality: int = 85) -> None:
        """Render the active document to a flat composite and save to *path*.

        Raises:
            RuntimeError: if no document is open.
            PersistenceError: if writing fails or format is unsupported.
        """
        from dip_studio.infrastructure.image_export import CompositeExporter

        if self.document is None:
            raise RuntimeError("No active document")
        # Render at document resolution (zoom = 1.0)
        doc = self.document
        composite_bytes = self.preview(doc.image.width, doc.image.height, zoom=1.0)
        CompositeExporter().export_document(composite_bytes, path, quality)

    def place_image(self, path: Path) -> ImageDocument:
        """Import *path* and add it as a new layer in the active document."""
        if self._image_importer is None:
            raise RuntimeError("Image import is not configured")
        if self.document is None:
            raise RuntimeError("No active document — use open_image to start a new document")
        imported = self._image_importer.import_image(path)
        from uuid import uuid4

        new_layer = Layer(
            id=LayerId(uuid4()),
            name=imported.name or path.stem,
            buffer_id=imported.buffer_id,
        )
        self._history_for_active().execute(
            AddLayer(new_layer), self._session
        )
        return self._session.document

    def _activate_new_document(self, document: ImageDocument) -> None:
        session = DocumentSession(document)
        key = str(document.id)
        self._sessions[key] = session
        self._histories[key] = UndoRedoHistory()
        self._session = session

    def preview(
        self, viewport_width: int, viewport_height: int, zoom: float = 1.0
    ) -> bytes:
        document = self.document
        if document is None:
            raise RuntimeError("No active document")
        # Prefer cached bytes from import (preserves original pixel data).
        if document.revision > 0:
            self._previews.pop(str(document.id), None)
        preview = self._previews.get(str(document.id))
        if preview is not None:
            return preview
        # Fall back to the render engine (compositor or blank renderer).
        return self._renderer.render(
            RenderRequest(str(document.id), viewport_width, viewport_height, zoom)
        )


    def preview_processing(
        self, operation: str, parameters: dict[str, object]
    ) -> bytes | None:
        """Run a processing operation without mutating the document.

        Returns preview bytes if the engine produced output, or None
        if no processor is registered for *operation*.
        """
        document = self.document
        if document is None:
            return None
        request = self._request(operation, parameters)
        # Get the first layer with a buffer_id
        layer = next(
            (la for la in document.layers if la.buffer_id is not None), None
        )
        if layer is None or self._data_store is None:
            return None
        try:
            result_buffer_id: str = self._processing.run(layer.buffer_id, request)
        except (KeyError, Exception):
            return None
        active_buf_ids = {
            la.buffer_id for doc in self.open_documents for la in doc.layers if la.buffer_id is not None
        }
        if result_buffer_id in active_buf_ids:
            return None  # stub returned input unchanged
        # Encode result as JPEG preview bytes
        try:
            from dip_studio.rendering.compositor import _encode_jpeg
            arr = self._data_store.get(result_buffer_id)
            # Release the temporary buffer safely
            if result_buffer_id not in active_buf_ids:
                self._data_store.release(result_buffer_id)
            return _encode_jpeg(arr)
        except Exception:
            return None

    def apply_processing(
        self, operation: str, parameters: dict[str, object]
    ) -> ImageDocument:
        request = self._request(operation, parameters)
        self._history_for_active().execute(
            ApplyProcessing(self._processing, request), self._session
        )
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def undo(self) -> ImageDocument:
        self._history_for_active().undo(self._session)
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def redo(self) -> ImageDocument:
        self._history_for_active().redo(self._session)
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def history_labels(self) -> list[str]:
        """Return ordered list of history command labels for the active document."""
        document = self.document
        if document is None:
            return []
        history = self._histories.get(str(document.id))
        if history is None:
            return []
        return history.labels()

    def history_current_index(self) -> int:
        """Return the index of the current state in the undo stack."""
        document = self.document
        if document is None:
            return -1
        history = self._histories.get(str(document.id))
        if history is None:
            return -1
        return history.current_index()

    def history_jump_to(self, index: int) -> ImageDocument:
        """Jump to an arbitrary history state by index."""
        self._history_for_active().jump_to(index, self._session)
        return self._session.document

    def set_layer_visibility(
        self, layer_id: LayerId, visible: bool
    ) -> ImageDocument:
        self._history_for_active().execute(
            ChangeLayer(layer_id, visible=visible), self._session
        )
        return self._session.document

    def set_layers_visibility(
        self, layer_ids: tuple[LayerId, ...], visible: bool
    ) -> ImageDocument:
        self._history_for_active().execute(
            ChangeLayers(layer_ids, visible=visible), self._session
        )
        return self._session.document

    def set_layer_opacity(
        self, layer_id: LayerId, opacity: float
    ) -> ImageDocument:
        self._history_for_active().execute(
            ChangeLayer(layer_id, opacity=opacity), self._session
        )
        return self._session.document

    def set_layers_opacity(
        self, layer_ids: tuple[LayerId, ...], opacity: float
    ) -> ImageDocument:
        self._history_for_active().execute(
            ChangeLayers(layer_ids, opacity=opacity), self._session
        )
        return self._session.document

    def resize_layer_to_rect(
        self,
        layer_id: LayerId,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> ImageDocument:
        """Resize only one layer's content; keep document bounds unchanged."""
        if self._data_store is None:
            raise RuntimeError("Image data storage is not configured")
        document = self._session.document
        layer = next((item for item in document.layers if item.id == layer_id), None)
        if layer is None or layer.buffer_id is None:
            raise ValueError("Selected layer has no image content")
        source_buffer_id = self._ensure_layer_buffer(document, layer)
        buffer_id = self._data_store.resize_buffer_to_rect(
            source_buffer_id,
            x,
            y,
            width,
            height,
            document.image.width,
            document.image.height,
        )
        self._history_for_active().execute(
            ChangeLayer(layer.id, buffer_id=buffer_id), self._session
        )
        self._previews.pop(str(document.id), None)
        return self._session.document

    def _ensure_layer_buffer(self, document: ImageDocument, layer: Layer) -> str:
        """Restore an imported layer buffer if a stale preview released it."""
        if self._data_store is None or layer.buffer_id is None:
            raise ValueError("Selected layer has no image content")
        if self._data_store.has(layer.buffer_id):
            return layer.buffer_id
        preview = self._previews.get(str(document.id))
        if preview is None:
            raise KeyError(f"Buffer not found: {layer.buffer_id}")
        try:
            import io
            from PIL import Image as PilImage
            import numpy as np

            with PilImage.open(io.BytesIO(preview)) as image:
                array = np.array(image.convert("RGBA"), dtype=np.uint8)
            restored_id = self._data_store.allocate(array)
        except (OSError, ValueError, TypeError) as error:
            raise PersistenceError(
                f"Could not restore image data for layer: {layer.name}"
            ) from error
        self._history_for_active().execute(
            ChangeLayer(layer.id, buffer_id=restored_id), self._session
        )
        return restored_id

    def rename_layer(self, layer_id: LayerId, name: str) -> ImageDocument:
        self._history_for_active().execute(
            RenameLayer(layer_id, name), self._session
        )
        return self._session.document

    def add_layer(self, name: str = "Layer") -> ImageDocument:
        self._history_for_active().execute(AddLayer(name), self._session)
        return self._session.document

    def duplicate_layer(self, layer_id: LayerId) -> ImageDocument:
        document = self._session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == layer_id),
            None,
        )
        if index is None:
            raise KeyError("Layer does not exist")
        source = document.layers[index]
        new_buf_id = None
        if source.buffer_id is not None and self._data_store is not None:
            new_buf_id = self._data_store.copy_on_write(source.buffer_id)
        self._history_for_active().execute(
            DuplicateLayer(source, index + 1, buffer_id=new_buf_id), self._session
        )
        return self._session.document

    def set_layer_blend_mode(
        self, layer_id: LayerId, blend_mode: str
    ) -> ImageDocument:
        from dip_studio.application.layer_commands import SetLayerBlendMode

        self._history_for_active().execute(
            SetLayerBlendMode(layer_id, blend_mode.lower()), self._session
        )
        return self._session.document

    def set_layer_locked(
        self, layer_id: LayerId, locked: bool
    ) -> ImageDocument:
        from dip_studio.application.layer_commands import SetLayerLocked

        self._history_for_active().execute(
            SetLayerLocked(layer_id, locked), self._session
        )
        return self._session.document

    def merge_down(self, layer_id: LayerId) -> ImageDocument:
        from dip_studio.application.layer_commands import MergeDown

        document = self._session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == layer_id),
            None,
        )
        if index is None:
            raise KeyError("Layer does not exist")
        if index == 0:
            raise ValueError("Cannot merge down the bottom layer")
        upper = document.layers[index]
        lower = document.layers[index - 1]

        merged_buffer_id = lower.buffer_id
        if (
            self._data_store is not None
            and upper.buffer_id is not None
            and lower.buffer_id is not None
        ):
            merged_buffer_id = self._data_store.merge_buffers(
                lower.buffer_id, upper.buffer_id, upper.opacity, upper.blend_mode
            )

        self._history_for_active().execute(
            MergeDown(upper.id, lower.id, merged_buffer_id), self._session
        )
        return self._session.document

    def create_layer_from_selection(
        self,
        rect: tuple[int, int, int, int],
        layer_id: LayerId | None = None,
        cut: bool = False,
    ) -> ImageDocument:
        """Create a new layer containing only the pixels inside rect (x, y, width, height).

        If cut=True, clears the selected pixels in the source layer.
        """
        from dip_studio.application.layer_commands import AddLayer, ChangeLayer

        document = self._session.document
        if not document.layers:
            raise RuntimeError("No layers available")

        if layer_id is not None:
            idx = next(
                (i for i, l in enumerate(document.layers) if l.id == layer_id),
                len(document.layers) - 1,
            )
        else:
            idx = len(document.layers) - 1
        src_layer = document.layers[idx]

        x, y, w, h = rect
        doc_w = document.image.width
        doc_h = document.image.height

        new_buffer_id = None
        if self._data_store is not None and src_layer.buffer_id is not None:
            new_buffer_id, cut_buf_id = self._data_store.extract_selection(
                src_layer.buffer_id, x, y, w, h, doc_w, doc_h, cut=cut
            )
            if cut and cut_buf_id is not None:
                self._history_for_active().execute(
                    ChangeLayer(src_layer.id, buffer_id=cut_buf_id), self._session
                )

        new_layer_name = f"{src_layer.name} Selection"
        new_layer = Layer(
            id=LayerId(uuid4()),
            name=new_layer_name,
            visible=True,
            opacity=1.0,
            buffer_id=new_buffer_id,
            blend_mode=src_layer.blend_mode,
        )
        self._history_for_active().execute(
            AddLayer(new_layer_name, source=new_layer, index=idx + 1), self._session
        )
        self._previews.pop(str(document.id), None)
        return self._session.document

    def crop_document(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> ImageDocument:
        """Crop all layers and resize the document to (width, height)."""
        from dip_studio.application.layer_commands import CropDocument

        document = self._session.document
        doc_w = document.image.width
        doc_h = document.image.height

        x1 = max(0, min(x, doc_w - 1))
        y1 = max(0, min(y, doc_h - 1))
        x2 = max(x1 + 1, min(x + width, doc_w))
        y2 = max(y1 + 1, min(y + height, doc_h))
        new_w = x2 - x1
        new_h = y2 - y1

        buffer_map: dict[LayerId, str] = {}
        if self._data_store is not None:
            for layer in document.layers:
                if layer.buffer_id is not None:
                    buffer_map[layer.id] = self._data_store.crop_buffer(
                        layer.buffer_id, x, y, width, height, doc_w, doc_h
                    )

        self._history_for_active().execute(
            CropDocument(new_w, new_h, buffer_map), self._session
        )
        self._previews.pop(str(document.id), None)
        return self._session.document

    def remove_layer(self, layer_id: LayerId) -> ImageDocument:
        self._history_for_active().execute(RemoveLayer(layer_id), self._session)
        return self._session.document

    def remove_layers(
        self, layer_ids: tuple[LayerId, ...]
    ) -> ImageDocument:
        self._history_for_active().execute(
            RemoveLayers(layer_ids), self._session
        )
        return self._session.document

    def move_layer(self, layer_id: LayerId, delta: int) -> ImageDocument:
        self._history_for_active().execute(
            MoveLayer(layer_id, delta), self._session
        )
        return self._session.document

    @staticmethod
    def _request(
        operation: str, parameters: dict[str, object]
    ) -> ProcessingRequest:
        return ProcessingRequest(
            operation,
            tuple((key, str(value)) for key, value in sorted(parameters.items())),
        )

    def _history_for_active(self) -> UndoRedoHistory:
        document = self._session.active_document
        if document is None:
            raise RuntimeError("No active document")
        return self._histories.setdefault(str(document.id), UndoRedoHistory())
