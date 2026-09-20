from pathlib import Path

from dip_studio.application.editor import EditorController
from dip_studio.infrastructure.image_import import ImageFormatRegistry
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_imported_preview_is_used_by_editor(tmp_path: Path) -> None:
    frame = b"P6\n2 1\n255\n" + b"\xff\x00\x00\x00\xff\x00"
    path = tmp_path / "sample.ppm"
    path.write_bytes(frame)
    controller = EditorController(
        BlankDocumentRenderer(), image_importer=ImageFormatRegistry()
    )

    controller.open_image(path)

    assert controller.preview(2, 1) == frame
