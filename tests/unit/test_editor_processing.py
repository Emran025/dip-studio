import numpy as np
import pytest

from dip_studio.application.editor import EditorController
from dip_studio.core.cancellation import MutableCancellationToken
from dip_studio.core.errors import ProcessingError
from dip_studio.domain.factories import document_from_import
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.domain.model import ImageSpec
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.engine import ProcessingEngine
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_preview_does_not_change_document() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)

    with pytest.raises(ProcessingError):
        controller.preview_processing("blur", {"Radius": 4.0})

    assert controller.document == document
    assert document.operations == ()


def test_apply_processing_is_dirty_and_undoable() -> None:
    class CopyProcessor:
        operation = "copy"

        def validate(self, request: ProcessingRequest) -> None:
            return None

        def process(self, image: str, request: ProcessingRequest) -> str:
            return store.allocate(store.get(image).copy())

    store = ImageDataStore()
    source_id = store.allocate(np.zeros((10, 10, 4), dtype=np.uint8))
    controller = EditorController(
        BlankDocumentRenderer(),
        data_store=store,
        processing_engine=ProcessingEngine({"copy": CopyProcessor()}),
    )
    original = document_from_import("sample", ImageSpec(10, 10), "sample", source_id)
    controller._activate_new_document(original)

    applied = controller.apply_processing("copy", {})
    restored = controller.undo()
    redone = controller.redo()

    assert applied.operations[0].operation == "copy"
    assert applied.is_dirty
    assert restored == original
    assert redone.operations == applied.operations
    assert redone.layers[0].buffer_id != original.layers[0].buffer_id


def test_apply_processing_async_commits_worker_result_without_rerunning() -> None:
    class CopyProcessor:
        operation = "copy"

        def validate(self, request: ProcessingRequest) -> None:
            return None

        def process(self, image: str, request: ProcessingRequest) -> str:
            return store.allocate(store.get(image).copy())

    store = ImageDataStore()
    source_id = store.allocate(np.zeros((4, 4, 4), dtype=np.uint8))
    controller = EditorController(
        BlankDocumentRenderer(),
        data_store=store,
        processing_engine=ProcessingEngine({"copy": CopyProcessor()}),
    )
    controller._activate_new_document(
        document_from_import("sample", ImageSpec(4, 4), "sample", source_id)
    )
    submitted: dict[str, object] = {}

    def submit(fn, *, on_done, on_error, on_progress):
        result = fn(MutableCancellationToken(), object())
        submitted["result"] = result
        on_done(result)
        return "token"

    completed: list[object] = []
    controller.apply_processing_async(
        "copy",
        {},
        submit,
        on_done=completed.append,
    )

    assert len(completed) == 1
    assert controller.document is completed[0]
    assert controller.document.operations[0].operation == "copy"
    assert controller.document.layers[0].buffer_id == submitted["result"]


def test_apply_processing_async_releases_stale_result() -> None:
    class CopyProcessor:
        operation = "copy"

        def validate(self, request: ProcessingRequest) -> None:
            return None

        def process(self, image: str, request: ProcessingRequest) -> str:
            return store.allocate(store.get(image).copy())

    store = ImageDataStore()
    source_id = store.allocate(np.zeros((4, 4, 4), dtype=np.uint8))
    controller = EditorController(
        BlankDocumentRenderer(),
        data_store=store,
        processing_engine=ProcessingEngine({"copy": CopyProcessor()}),
    )
    controller._activate_new_document(
        document_from_import("sample", ImageSpec(4, 4), "sample", source_id)
    )
    stale: list[bool] = []

    def submit(fn, *, on_done, on_error, on_progress):
        result = fn(MutableCancellationToken(), object())
        controller.rename_layer(controller.document.layers[0].id, "edited")
        on_done(result)
        assert isinstance(result, str)
        assert not store.has(result)
        return "token"

    controller.apply_processing_async("copy", {}, submit, on_stale=lambda: stale.append(True))

    assert stale == [True]
    assert controller.document.layers[0].name == "edited"
    assert controller.document.operations == ()
