"""Application-facing editor orchestration for the first vertical slice."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dip_studio.application.commands import ApplyProcessing, ReplaceDocument
from dip_studio.application.history import UndoRedoHistory
from dip_studio.core.errors import PersistenceError, ProcessingError
from dip_studio.application.layer_commands import (
    AddLayer,
    ChangeLayer,
    ChangeLayers,
    ChangeLayersLocked,
    DuplicateLayer,
    MoveLayer,
    PasteLayers,
    RemoveLayer,
    RemoveLayers,
    RenameLayer,
)
from dip_studio.application.ports import ImageImporter, ProjectStore
from dip_studio.application.session import DocumentSession
from dip_studio.application.result_store import ProcessingResultStore
from dip_studio.application.backend_capabilities import (
    BackendCapability,
    discover_backend_capabilities,
)
from dip_studio.application.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    default_tool_registry,
)
from dip_studio.domain.factories import document_from_import, new_document
from dip_studio.domain.model import (
    AppliedOperation,
    ImageDocument,
    Layer,
    LayerId,
    ShapeLayer,
)
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.contracts import ProcessingResult
from dip_studio.processing.engine import ProcessingEngine
from dip_studio.processing.plugins import PluginActivationFailure
from dip_studio.rendering.ports import RenderEngine, RenderRequest
from dip_studio.infrastructure.data_store import ImageDataStore

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore


@dataclass(frozen=True, slots=True)
class ProcessingJobSnapshot:
    """Immutable state captured before a background processing job starts."""

    document_id: DocumentId
    document_revision: int
    layer_id: LayerId
    input_buffer_id: str
    input_buffer_version: int
    mask_versions: tuple[tuple[str, int], ...] = ()
    selection_versions: tuple[tuple[str, int], ...] = ()


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
        result_store: ProcessingResultStore | None = None,
        plugin_failures: tuple[PluginActivationFailure, ...] = (),
    ) -> None:
        self._renderer = renderer
        self._project_store = project_store
        self._image_importer = image_importer
        self._tool_registry = tool_registry or default_tool_registry()
        if data_store is None and image_importer is not None:
            data_store = getattr(image_importer, "_data_store", None)
        if data_store is None:
            data_store = ImageDataStore()
        if image_importer is not None:
            if hasattr(image_importer, "set_data_store"):
                image_importer.set_data_store(data_store)
            else:
                image_importer._data_store = data_store
        self._data_store = data_store
        self._result_store = result_store or ProcessingResultStore()
        self._plugin_failures = plugin_failures
        self._session = DocumentSession()
        self._sessions: dict[str, DocumentSession] = {}
        self._histories: dict[str, UndoRedoHistory] = {}
        self._clipboard: tuple[Layer, ...] = ()
        self._previews: dict[str, bytes] = {}
        self._active_tool_id: str = ""
        self._active_layer_id: LayerId | None = None
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
    def backend_capabilities(self) -> tuple[BackendCapability, ...]:
        """Report optional backend availability for presentation and automation."""
        return discover_backend_capabilities()

    @property
    def plugin_failures(self) -> tuple[PluginActivationFailure, ...]:
        """Return plugin failures captured during composition."""
        return self._plugin_failures

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

    def validate_tool_parameters(self, tool_id: str, values: Mapping[str, object]) -> None:
        """Validate presentation-provided values against a registered tool schema."""
        validator = getattr(self._tool_registry, "validate_parameters", None)
        if validator is not None:
            validator(tool_id, values)

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
        self._result_store.remove_document(document_id)
        if self._sessions:
            self._session = next(iter(self._sessions.values()))
        else:
            self._session = DocumentSession()

    def store_processing_result(
        self,
        result_id: str,
        result: ProcessingResult,
        *,
        document_id: object | None = None,
    ) -> None:
        """Store a typed non-pixel result for the selected document."""
        target = self.document.id if document_id is None else document_id
        self._result_store.put(target, result_id, result)

    def processing_results(
        self, *, document_id: object | None = None
    ) -> dict[str, ProcessingResult]:
        """Return a snapshot of typed results for a document."""
        target = self.document.id if document_id is None else document_id
        return dict(self._result_store.snapshot(target))

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

    def save_document_snapshot(self, document: ImageDocument, path: Path) -> bool:
        """Persist a captured document only if it is still current.

        This is used by recovery/autosave workers. The caller captures the
        immutable document on the UI thread; the worker only performs I/O when
        the snapshot still matches the active revision.
        """
        if self._project_store is None:
            raise RuntimeError("Project storage is not configured")
        current = self.document
        if current is None or current.id != document.id or current.revision != document.revision:
            return False
        self._project_store.save(document, path)
        return True

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

        Raises:
            ProcessingError: if the document has no buffered target or the
                operation fails.
        """
        document = self.document
        if document is None:
            raise ProcessingError("Cannot preview processing without a document")
        request = self._request(operation, parameters)
        # Get the first layer with a buffer_id
        layer = next(
            (la for la in document.layers if la.buffer_id is not None), None
        )
        if layer is None or self._data_store is None or layer.buffer_id is None:
            raise ProcessingError("Cannot preview processing without a buffered layer")
        result_buffer_id = self._processing.run(layer.buffer_id, request)
        active_buf_ids = {
            la.buffer_id for doc in self.open_documents for la in doc.layers if la.buffer_id is not None
        }
        if result_buffer_id in active_buf_ids:
            raise ProcessingError(
                f"Processor '{operation}' returned an existing buffer instead of a preview result"
            )
        # Encode result as JPEG preview bytes
        try:
            from dip_studio.rendering.compositor import _encode_jpeg
            arr = self._data_store.get(result_buffer_id)
            # Release the temporary buffer safely
            if result_buffer_id not in active_buf_ids:
                self._data_store.release(result_buffer_id)
            return _encode_jpeg(arr)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            if self._data_store.has(result_buffer_id):
                self._data_store.release(result_buffer_id)
            raise ProcessingError(f"Could not encode preview for '{operation}'") from exc

    def apply_processing(
        self, operation: str, parameters: dict[str, object]
    ) -> ImageDocument:
        request = self._request(operation, parameters)
        # Target the active layer if one is tracked.
        layer_id = self._active_layer_id
        self._history_for_active().execute(
            ApplyProcessing(self._processing, request, layer_id=layer_id),
            self._session,
        )
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def apply_processing_async(
        self,
        operation: str,
        parameters: dict[str, object],
        submit: Callable[..., Any],
        *,
        on_done: Callable[[ImageDocument], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_stale: Callable[[], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> Any:
        """Apply processing through an injected background-job boundary.

        ``submit`` is deliberately a plain callable so the application layer
        remains independent of Qt. It must accept a callback receiving
        ``(cancellation_token, progress_reporter)`` and support the same
        ``on_done``, ``on_error`` and ``on_progress`` keyword callbacks as the
        presentation worker.
        """
        document = self.document
        if document is None:
            error = ProcessingError("Cannot apply processing without a document")
            if on_error is not None:
                on_error(error)
            return None

        layer = self._find_processing_layer(document)
        if layer is None or layer.buffer_id is None or self._data_store is None:
            error = ProcessingError(
                f"Cannot apply '{operation}': no buffered target layer"
            )
            if on_error is not None:
                on_error(error)
            return None

        request = self._request(operation, parameters)
        captured_buffer_id = layer.buffer_id
        snapshot = ProcessingJobSnapshot(
            document_id=document.id,
            document_revision=document.revision,
            layer_id=layer.id,
            input_buffer_id=captured_buffer_id,
            input_buffer_version=self._data_store.version(captured_buffer_id),
            mask_versions=tuple(
                (mask.buffer_id, self._data_store.version(mask.buffer_id))
                for mask in document.masks
                if mask.buffer_id is not None and self._data_store.has(mask.buffer_id)
            ),
            selection_versions=tuple(
                (selection.mask_buffer_id, self._data_store.version(selection.mask_buffer_id))
                for selection in document.selections
                if (
                    selection.mask_buffer_id is not None
                    and self._data_store.has(selection.mask_buffer_id)
                )
            ),
        )

        def run(token: Any, reporter: Any) -> str:
            return self._processing.run(
                captured_buffer_id,
                request,
                cancellation=token,
                progress=reporter,
                metadata={"preview": False, "document_id": str(snapshot.document_id)},
            )

        def commit(result_buffer_id: Any) -> None:
            current = self.document
            if (
                current is None
                or current.id != snapshot.document_id
                or current.revision != snapshot.document_revision
                or self._data_store is None
                or not self._data_store.has(snapshot.input_buffer_id)
                or self._data_store.version(snapshot.input_buffer_id)
                != snapshot.input_buffer_version
                or any(
                    not self._data_store.has(buffer_id)
                    or self._data_store.version(buffer_id) != version
                    for buffer_id, version in (
                        snapshot.mask_versions + snapshot.selection_versions
                    )
                )
            ):
                if isinstance(result_buffer_id, str) and self._data_store is not None:
                    self._data_store.release(result_buffer_id)
                if on_stale is not None:
                    on_stale()
                return
            if not isinstance(result_buffer_id, str) or not result_buffer_id:
                error = ProcessingError(
                    f"Processor '{operation}' returned an invalid buffer"
                )
                if on_error is not None:
                    on_error(error)
                return
            if result_buffer_id == captured_buffer_id:
                error = ProcessingError(
                    f"Processor '{operation}' produced no new result buffer"
                )
                if on_error is not None:
                    on_error(error)
                return
            try:
                target = next(layer for layer in current.layers if layer.id == snapshot.layer_id)
                new_layer = target.changed(buffer_id=result_buffer_id)
                new_document = current.changed(
                    layers=tuple(
                        new_layer if layer.id == snapshot.layer_id else layer
                        for layer in current.layers
                    ),
                    operations=current.operations
                    + (AppliedOperation(operation, request.parameters),),
                )
                self._history_for_active().execute(
                    ReplaceDocument(new_document), self._session
                )
            except Exception as exc:
                if self._data_store.has(result_buffer_id):
                    self._data_store.release(result_buffer_id)
                if on_error is not None:
                    on_error(exc)
                return
            self._previews.pop(str(snapshot.document_id), None)
            if on_done is not None:
                on_done(self._session.document)

        return submit(
            run,
            on_done=commit,
            on_error=on_error,
            on_progress=on_progress,
        )

    def _find_processing_layer(self, document: ImageDocument) -> Layer | None:
        if self._active_layer_id is not None:
            return next(
                (
                    layer
                    for layer in document.layers
                    if layer.id == self._active_layer_id
                    and layer.buffer_id is not None
                ),
                None,
            )
        return next(
            (layer for layer in document.layers if layer.buffer_id is not None),
            None,
        )

    # ------------------------------------------------------------------
    # Active-layer tracking
    # ------------------------------------------------------------------

    @property
    def active_layer_id(self) -> "LayerId | None":
        """The ID of the currently selected layer, or None when unset."""
        return self._active_layer_id

    def set_active_layer(self, layer_id: "LayerId | None") -> None:
        """Record which layer the user has selected in the layer panel."""
        self._active_layer_id = layer_id

    @property
    def active_selection(self) -> object | None:
        doc = self.document
        return doc.selections[-1] if doc and doc.selections else None

    def set_selection(self, selection: object | None) -> "ImageDocument | None":
        """Set or update active selection rect / mask on current document."""
        doc = self.document
        if doc is None:
            return None
        selections = (selection,) if selection is not None else ()
        updated = doc.changed(selections=selections)
        self._session.replace(updated)
        return self._session.document

    def draw_shape(
        self,
        shape_type: str,
        rect: tuple[int, int, int, int],
        fill_color_name: str | tuple[int, int, int, int] = "Red",
        stroke_color_name: str | tuple[int, int, int, int] = "Black",
        stroke_width: int = 2,
    ) -> "ImageDocument | None":
        """Draw a vector/raster shape on the active layer."""
        from dip_studio.infrastructure.shape_commands import DrawShape

        doc = self.document
        if doc is None or self._data_store is None:
            return None
        layer_id = self._active_layer_id
        if layer_id is None:
            if not doc.layers:
                return None
            layer_id = doc.layers[-1].id
        command = DrawShape(
            self._data_store,
            layer_id,
            shape_type,
            rect,
            fill_color_name,
            stroke_color_name,
            stroke_width,
        )
        self._history_for_active().execute(command, self._session)
        if command.created_layer_id is not None:
            self._active_layer_id = command.created_layer_id
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def color_selection(
        self, x: int, y: int, tolerance: int = 15
    ) -> "ImageDocument | None":
        """Magic Wand: select connected pixels with matching color at (x, y)."""
        doc = self.document
        store = self.data_store
        if doc is None or store is None:
            return None
        layer = next((la for la in doc.layers if la.buffer_id is not None), None)
        if layer is None or layer.buffer_id is None:
            return None
        try:
            from dip_studio.application.presentation_bridge import rasterise_color_selection

            arr = store.get(layer.buffer_id)
            h, w = arr.shape[:2]
            mask_binary = rasterise_color_selection(arr, x, y, tolerance=tolerance)
            mask_bid = store.allocate(mask_binary)

            sel = self.make_selection(
                x=0, y=0, width=w, height=h, kind="color_selection", mask_buffer_id=mask_bid
            )
            return self.set_selection(sel)
        except Exception:
            return None

    def translate_layer(
        self, layer_id: "LayerId", dx: float, dy: float
    ) -> "ImageDocument":
        """Translate a layer while keeping its content inside the document."""
        from dip_studio.application.layer_commands import TranslateLayer

        document = self._session.document
        layer = next(
            (candidate for candidate in document.layers if candidate.id == layer_id),
            None,
        )
        if layer is None:
            raise KeyError("Layer does not exist")
        if layer.locked:
            raise RuntimeError(f"Layer '{layer.name}' is locked")

        transform = layer.transform
        current_tx = float(transform.tx) if transform else 0.0
        current_ty = float(transform.ty) if transform else 0.0
        scale_x = abs(float(transform.sx)) if transform else 1.0
        scale_y = abs(float(transform.sy)) if transform else 1.0

        if isinstance(layer, ShapeLayer) and len(layer.vertices) >= 4:
            base_x, base_y, width, height = (
                float(value) for value in layer.vertices[:4]
            )
        elif layer.buffer_id is not None and self._data_store is not None:
            try:
                buffer = self._data_store.get(layer.buffer_id)
            except KeyError:
                buffer = None
            if buffer is not None and buffer.ndim >= 2:
                base_x, base_y = 0.0, 0.0
                height, width = buffer.shape[:2]
            else:
                base_x, base_y, width, height = (
                    0.0,
                    0.0,
                    float(document.image.width),
                    float(document.image.height),
                )
        else:
            base_x, base_y, width, height = (
                0.0,
                0.0,
                float(document.image.width),
                float(document.image.height),
            )

        rendered_width = max(1.0, width * scale_x)
        rendered_height = max(1.0, height * scale_y)
        min_tx = -base_x
        max_tx = max(min_tx, float(document.image.width) - rendered_width - base_x)
        min_ty = -base_y
        max_ty = max(min_ty, float(document.image.height) - rendered_height - base_y)
        target_tx = min(max(current_tx + dx, min_tx), max_tx)
        target_ty = min(max(current_ty + dy, min_ty), max_ty)

        self._history_for_active().execute(
            TranslateLayer(layer_id, target_tx - current_tx, target_ty - current_ty),
            self._session,
        )
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def resize_shape_layer(
        self, layer_id: "LayerId", rect: tuple[int, int, int, int]
    ) -> "ImageDocument":
        """Resize a vector shape while preserving its editable layer identity."""
        from dip_studio.infrastructure.shape_commands import ResizeShapeLayer

        self._history_for_active().execute(
            ResizeShapeLayer(layer_id, rect), self._session
        )
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def hit_test_layer(self, x: int, y: int) -> "Layer | None":
        """Return the top-most visible layer containing pixel content at (x, y)."""
        doc = self.document
        store = self.data_store
        if doc is None:
            return None
        # Test layers top-to-bottom
        for layer in reversed(doc.layers):
            if not layer.visible:
                continue
            if isinstance(layer, ShapeLayer):
                x0, y0, width, height = (
                    int(round(value)) for value in layer.vertices[:4]
                )
                transform = layer.transform
                tx = int(transform.tx) if transform else 0
                ty = int(transform.ty) if transform else 0
                sx = transform.sx if transform else 1.0
                sy = transform.sy if transform else 1.0
                right = x0 + tx + int(width * sx)
                bottom = y0 + ty + int(height * sy)
                if min(x0 + tx, right) <= x <= max(x0 + tx, right) and min(y0 + ty, bottom) <= y <= max(y0 + ty, bottom):
                    return layer
            elif layer.buffer_id is not None and store is not None:
                try:
                    arr = store.get(layer.buffer_id)
                    h, w = arr.shape[:2]
                    t = layer.transform
                    tx = t.tx if t else 0.0
                    ty = t.ty if t else 0.0
                    local_x = int(x - tx)
                    local_y = int(y - ty)
                    if 0 <= local_x < w and 0 <= local_y < h:
                        if arr.ndim == 3 and arr.shape[2] == 4:
                            if arr[local_y, local_x, 3] > 0:
                                return layer
                        else:
                            return layer
                except Exception:
                    pass
            else:
                if 0 <= x < doc.image.width and 0 <= y < doc.image.height:
                    return layer
        return None

    @staticmethod
    def make_selection(**kwargs: object) -> object:
        from dip_studio.domain.model import SelectionRect
        return SelectionRect(**kwargs)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Paint / draw tools (Phase 5)
    # ------------------------------------------------------------------

    def paint_stroke(
        self,
        points: "list[tuple[int, int]]",
        color: "tuple[int, int, int, int]",
        size: int = 10,
        hardness: float = 0.8,
        opacity: float = 1.0,
    ) -> "ImageDocument | None":
        """Paint a brush stroke into the active layer buffer.

        Returns the updated document or None if no paintable layer is found.
        """
        from dip_studio.infrastructure.paint_commands import PaintStroke

        document = self.document
        if document is None or self._data_store is None:
            return None
        layer_id = self._active_layer_id
        if layer_id is None:
            # Fall back to first buffered layer.
            layer = next((la for la in document.layers if la.buffer_id is not None), None)
            if layer is None:
                return None
            layer_id = layer.id
        self._history_for_active().execute(
            PaintStroke(self._data_store, layer_id, points, color, size, hardness, opacity),
            self._session,
        )
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def eraser_stroke(
        self,
        points: "list[tuple[int, int]]",
        size: int = 20,
        hardness: float = 0.8,
        opacity: float = 1.0,
    ) -> "ImageDocument | None":
        """Erase pixels from the active layer (reduces alpha).

        Returns the updated document or None if no erasable layer is found.
        """
        from dip_studio.infrastructure.paint_commands import EraserStroke

        document = self.document
        if document is None or self._data_store is None:
            return None
        layer_id = self._active_layer_id
        if layer_id is None:
            layer = next((la for la in document.layers if la.buffer_id is not None), None)
            if layer is None:
                return None
            layer_id = layer.id
        self._history_for_active().execute(
            EraserStroke(self._data_store, layer_id, points, size, hardness, opacity),
            self._session,
        )
        self._previews.pop(str(self._session.document.id), None)
        return self._session.document

    def flood_fill(
        self,
        x: int,
        y: int,
        color: "tuple[int, int, int, int]",
        tolerance: int = 15,
    ) -> "ImageDocument | None":
        """BFS flood-fill into the active layer at pixel (x, y).

        Returns the updated document or None if no fillable layer is found.
        """
        from dip_studio.infrastructure.paint_commands import FloodFill

        document = self.document
        if document is None or self._data_store is None:
            return None
        layer_id = self._active_layer_id
        if layer_id is None:
            layer = next((la for la in document.layers if la.buffer_id is not None), None)
            if layer is None:
                return None
            layer_id = layer.id
        self._history_for_active().execute(
            FloodFill(self._data_store, layer_id, x, y, color, tolerance),
            self._session,
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
            with PilImage.open(io.BytesIO(preview)) as image:
                from dip_studio.infrastructure.preview_decoder import decode_rgba
                array = decode_rgba(image)
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

    def set_layers_locked(
        self, layer_ids: tuple[LayerId, ...], locked: bool
    ) -> ImageDocument:
        self._history_for_active().execute(
            ChangeLayersLocked(layer_ids, locked), self._session
        )
        return self._session.document

    def group_layers(self, layer_ids: tuple[LayerId, ...]) -> ImageDocument:
        from dip_studio.application.layer_commands import GroupLayers

        command = GroupLayers(layer_ids)
        self._history_for_active().execute(command, self._session)
        self._active_layer_id = command.group_id
        return self._session.document

    def ungroup_layer(self, layer_id: LayerId) -> ImageDocument:
        from dip_studio.application.layer_commands import UngroupLayer

        self._history_for_active().execute(
            UngroupLayer(layer_id), self._session
        )
        self._active_layer_id = None
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
