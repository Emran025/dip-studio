from pathlib import Path

from dip_studio.application.editor import EditorController
from dip_studio.infrastructure.project_store import JsonProjectStore
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_editor_controller_saves_and_opens_project(tmp_path: Path) -> None:
    path = tmp_path / "sample.dip"
    controller = EditorController(BlankDocumentRenderer(), JsonProjectStore())
    created = controller.create_document("sample", 20, 10)

    saved = controller.save_project(path)

    assert saved == controller.document
    assert not saved.is_dirty
    reopened = controller.open_project(path)
    assert reopened == saved


def test_editor_controller_keeps_multiple_documents_and_copies_layers() -> None:
    controller = EditorController(BlankDocumentRenderer())
    first = controller.create_document("first", 20, 10)
    second = controller.create_document("second", 30, 15)

    assert [document.name for document in controller.open_documents] == ["first", "second"]
    controller.activate_document(first.id)
    controller.copy_layers((first.layers[0].id,))
    controller.activate_document(second.id)

    pasted = controller.paste_layers()

    assert len(pasted.layers) == 2
    assert pasted.layers[-1].name == "Background copy"
    assert pasted.layers[-1].id != first.layers[0].id
