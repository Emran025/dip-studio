from dip_studio.application.editor import EditorController
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_editor_controller_creates_document_and_preview() -> None:
    controller = EditorController(BlankDocumentRenderer())

    document = controller.create_document("sample", 4, 3)
    preview = controller.preview(4, 3)

    assert controller.document == document
    assert preview.startswith(b"P6\n4 3\n255\n")
    assert len(preview) == len(b"P6\n4 3\n255\n") + 36


def test_editor_controller_requires_active_document() -> None:
    try:
        EditorController(BlankDocumentRenderer()).preview(4, 3)
    except RuntimeError as error:
        assert "active document" in str(error)
    else:
        raise AssertionError("preview requires an active document")
