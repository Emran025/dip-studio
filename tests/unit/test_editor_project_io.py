import json
import zipfile
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from dip_studio.application.editor import EditorController
from dip_studio.core.errors import PersistenceError
from dip_studio.domain.model import (
    DocumentId,
    GroupLayer,
    ImageDocument,
    ImageSpec,
    LayerId,
    Mask,
    SelectionRect,
    ShapeLayer,
    TextLayer,
)
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.project_store import JsonProjectStore
from dip_studio.infrastructure.zip_project_store import ZipProjectStore
from dip_studio.rendering.ports import BlankDocumentRenderer


def test_editor_controller_saves_and_opens_project(tmp_path: Path) -> None:
    path = tmp_path / "sample.dip"
    controller = EditorController(BlankDocumentRenderer(), JsonProjectStore())
    controller.create_document("sample", 20, 10)

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


def test_editor_controller_rejects_stale_document_snapshots(tmp_path: Path) -> None:
    controller = EditorController(BlankDocumentRenderer(), JsonProjectStore())
    original = controller.create_document("snapshot", 20, 10)
    snapshot_path = tmp_path / "snapshot_recovery.dip"
    stale_snapshot_path = tmp_path / "stale_snapshot_recovery.dip"

    assert controller.save_document_snapshot(original, snapshot_path) is True
    assert snapshot_path.exists()

    updated = original.changed()
    controller._session.replace(updated)

    assert controller.save_document_snapshot(original, stale_snapshot_path) is False
    assert not stale_snapshot_path.exists()


def test_recovery_discovery_cleanup_and_restore(tmp_path: Path) -> None:
    project_store = JsonProjectStore()
    recovery_dir = tmp_path / "recovery"
    recovery_dir.mkdir()

    doc = ImageDocument(
        id=DocumentId(uuid4()),
        name="project-alpha",
        image=ImageSpec(2, 2),
    )
    valid_path = recovery_dir / "project-alpha_recovery.dip"
    invalid_path = recovery_dir / "project-alpha_recovery_old.dip"
    temp_path = recovery_dir / "project-alpha_recovery.tmp"

    project_store.save(doc, valid_path)
    temp_path.write_text("partial", encoding="utf-8")
    invalid_path.write_text("{not-valid-json}", encoding="utf-8")

    discovered = [
        path.name
        for path in __import__(
            "dip_studio.infrastructure.autosave", fromlist=["discover_recovery_files"]
        ).discover_recovery_files("project-alpha", recovery_dir=recovery_dir)
    ]
    assert valid_path.name in discovered
    assert invalid_path.name in discovered
    assert temp_path.name not in discovered

    restored = __import__(
        "dip_studio.infrastructure.autosave", fromlist=["find_latest_recovery_file"]
    ).find_latest_recovery_file(
        document_name="project-alpha",
        recovery_dir=recovery_dir,
        project_store=project_store,
    )
    assert restored == valid_path

    kept = __import__(
        "dip_studio.infrastructure.autosave", fromlist=["cleanup_recovery_files"]
    ).cleanup_recovery_files(
        document_name="project-alpha",
        recovery_dir=recovery_dir,
        max_generations=1,
        project_store=project_store,
    )
    assert len(kept) == 1
    assert kept[0].name == valid_path.name
    assert not temp_path.exists()


def test_autosave_worker_keeps_bounded_generations(tmp_path: Path) -> None:
    from dip_studio.infrastructure.autosave import AutosaveWorker

    controller = EditorController(BlankDocumentRenderer(), JsonProjectStore())
    controller.create_document("bounded", 2, 2)
    worker = AutosaveWorker(controller, interval_seconds=1, max_generations=2)

    recovery_dir = tmp_path / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    first = recovery_dir / "bounded_recovery.dip"
    second = recovery_dir / "bounded_recovery_2.dip"
    third = recovery_dir / "bounded_recovery_3.dip"
    store = JsonProjectStore()
    store.save(controller.document, first)
    store.save(controller.document, second)
    store.save(controller.document, third)

    kept = worker.cleanup_recovery_files("bounded", recovery_dir=recovery_dir)
    assert len(kept) == 2
    assert all(path.name in {second.name, third.name} for path in kept)


def test_zip_store_round_trips_concrete_layer_types(tmp_path: Path) -> None:
    data_store = ImageDataStore()
    buffer_id = data_store.allocate(np.zeros((4, 5, 4), dtype=np.uint8))
    text = TextLayer(
        id=LayerId(uuid4()),
        name="Text",
        buffer_id=buffer_id,
        text="مرحبا",
        font_family="Noto Sans",
        font_size=32,
        direction="rtl",
        color_rgba=(10, 20, 30, 255),
    )
    shape = ShapeLayer(
        id=LayerId(uuid4()),
        name="Shape",
        buffer_id=buffer_id,
        shape_type="ellipse",
        stroke_color=(1, 2, 3, 255),
        vertices=(1.0, 2.0, 3.0, 4.0),
    )
    group = GroupLayer(
        id=LayerId(uuid4()),
        name="Group",
        children=(text.id, shape.id),
    )
    document = ImageDocument(
        id=DocumentId(uuid4()),
        name="typed",
        image=ImageSpec(5, 4),
        layers=(text, shape, group),
    )
    path = tmp_path / "typed.dip"

    ZipProjectStore(data_store).save(document, path)
    reopened = ZipProjectStore(data_store).load(path)

    assert isinstance(reopened.layers[0], TextLayer)
    assert reopened.layers[0].text == "مرحبا"
    assert isinstance(reopened.layers[1], ShapeLayer)
    assert reopened.layers[1].vertices == (1.0, 2.0, 3.0, 4.0)
    assert isinstance(reopened.layers[2], GroupLayer)
    assert reopened.layers[2].children == (text.id, shape.id)


def test_zip_store_round_trips_masks_selections_and_metadata(tmp_path: Path) -> None:
    data_store = ImageDataStore()
    pixels = data_store.allocate(np.zeros((4, 5, 4), dtype=np.uint8))
    mask_buffer = data_store.allocate(np.ones((4, 5), dtype=np.float32))
    selection_buffer = data_store.allocate(np.ones((4, 5), dtype=np.uint8))
    document = ImageDocument(
        id=DocumentId(uuid4()),
        name="selection-project",
        image=ImageSpec(5, 4),
        layers=(ShapeLayer(id=LayerId(uuid4()), name="Layer", buffer_id=pixels),),
        masks=(
            Mask(
                id="mask-1",
                name="Reveal",
                width=5,
                height=4,
                buffer_id=mask_buffer,
            ),
        ),
        selections=(
            SelectionRect(
                x=1,
                y=1,
                width=2,
                height=2,
                kind="polygon",
                mask_buffer_id=selection_buffer,
            ),
        ),
        metadata=(("author", "DIP Studio"),),
        workspace_metadata=(("panel", "layers"),),
        buffer_metadata=((pixels, {"color_space": "sRGB"}),),
        cv_objects=({"object_id": "obj-1", "class": "cat", "confidence": 0.9},),
    )
    path = tmp_path / "selection-project.dip"

    ZipProjectStore(data_store).save(document, path)
    reopened = ZipProjectStore(data_store).load(path)

    assert reopened.masks[0].name == "Reveal"
    assert reopened.masks[0].buffer_id is not None
    assert reopened.selections[0].kind == "polygon"
    assert reopened.selections[0].mask_buffer_id is not None
    assert reopened.metadata == (("author", "DIP Studio"),)
    assert reopened.workspace_metadata == (("panel", "layers"),)
    assert reopened.cv_objects[0]["object_id"] == "obj-1"
    assert reopened.buffer_metadata[0][0] == reopened.layers[0].buffer_id


def test_zip_store_rejects_unsafe_member_paths(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.dip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../metadata.json", json.dumps({"format_version": 2}))

    with pytest.raises(PersistenceError, match="unsafe members"):
        ZipProjectStore(ImageDataStore()).load(path)


def test_zip_store_rejects_out_of_range_archive_size(tmp_path: Path) -> None:
    path = tmp_path / "oversized.dip"
    original_limit = ZipProjectStore.max_archive_members
    ZipProjectStore.max_archive_members = 1
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "metadata.json",
                json.dumps(
                    {
                        "format_version": 2,
                        "document": {
                            "id": str(uuid4()),
                            "name": "test",
                            "revision": 0,
                            "image": {
                                "width": 1,
                                "height": 1,
                                "channels": 4,
                                "bit_depth": 8,
                                "color_space": "sRGB",
                                "has_alpha": True,
                            },
                            "layers": [],
                            "operations": [],
                            "masks": [],
                            "selections": [],
                            "metadata": {},
                        },
                    }
                ),
            )
            zf.writestr("buffers/large.npy", b"x" * 32)
        with pytest.raises(PersistenceError, match="too many members"):
            ZipProjectStore(ImageDataStore()).load(path)
    finally:
        ZipProjectStore.max_archive_members = original_limit


def test_zip_store_rejects_manifest_checksum_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "checksum.dip"
    metadata = json.dumps(
        {
            "format_version": 2,
            "document": {
                "id": str(uuid4()),
                "name": "checksum-test",
                "revision": 0,
                "image": {
                    "width": 1,
                    "height": 1,
                    "channels": 4,
                    "bit_depth": 8,
                    "color_space": "sRGB",
                    "has_alpha": True,
                },
                "layers": [],
                "operations": [],
                "masks": [],
                "selections": [],
                "metadata": {},
            },
        }
    ).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", metadata)
        zf.writestr(
            "checksum.manifest.json",
            json.dumps(
                {
                    "format_version": 2,
                    "sha256": "deadbeef",
                }
            ),
        )

    with pytest.raises(PersistenceError, match="checksum"):
        ZipProjectStore(ImageDataStore()).load(path)
