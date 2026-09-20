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
