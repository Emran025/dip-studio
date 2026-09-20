from pathlib import Path

import pytest

from dip_studio.application.editor import EditorController
from dip_studio.core.errors import PersistenceError
from dip_studio.infrastructure.image_import import ImageFormatRegistry, PpmImageImporter
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_ppm_import_creates_new_document(tmp_path: Path) -> None:
    path = tmp_path / "photo.ppm"
    path.write_bytes(b"P6\n7 5\n255\n" + b"\0" * 105)
    controller = EditorController(BlankDocumentRenderer(), image_importer=ImageFormatRegistry())

    document = controller.open_image(path)

    assert document.name == "photo"
    assert document.image.width == 7
    assert document.image.height == 5
    assert document.layers[0].name == "photo"


def test_registry_rejects_unknown_format(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError, match="No image importer"):
        ImageFormatRegistry().importer_for(tmp_path / "photo.png")


def test_ppm_import_rejects_invalid_data(tmp_path: Path) -> None:
    path = tmp_path / "broken.ppm"
    path.write_bytes(b"not an image")

    with pytest.raises(PersistenceError):
        PpmImageImporter().import_image(path)
