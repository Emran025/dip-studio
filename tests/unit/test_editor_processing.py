from dip_studio.application.editor import EditorController
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_preview_does_not_change_document() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)

    controller.preview_processing("blur", {"Radius": 4.0})

    assert controller.document == document
    assert document.operations == ()


def test_apply_processing_is_dirty_and_undoable() -> None:
    controller = EditorController(BlankDocumentRenderer())
    original = controller.create_document("sample", 10, 10)

    applied = controller.apply_processing("blur", {"Radius": 4.0})
    restored = controller.undo()
    redone = controller.redo()

    assert applied.operations[0].operation == "blur"
    assert applied.is_dirty
    assert restored == original
    assert redone == applied
