from dip_studio.application.editor import EditorController
from dip_studio.application.layer_commands import ChangeLayer
from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import Layer, LayerId
from dip_studio.rendering.ports import BlankDocumentRenderer
from uuid import uuid4


def test_layer_visibility_and_opacity_are_undoable() -> None:
    controller = EditorController(BlankDocumentRenderer())
    controller.create_document("sample", 10, 10)

    layer_id = controller.document.layers[0].id
    hidden = controller.set_layer_visibility(layer_id, False)
    assert not hidden.layers[0].visible
    changed = controller.set_layer_opacity(layer_id, 0.4)
    assert changed.layers[0].opacity == 0.4

    restored = controller.undo()
    assert restored.layers[0].visible is False
    assert restored.layers[0].opacity == 1.0


def test_layer_changes_follow_identity_not_position() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)
    layer_id = document.layers[0].id
    moved = document.changed(
        layers=(
            Layer(LayerId(uuid4()), "Overlay"),
            document.layers[0],
        )
    )
    session = DocumentSession(moved)
    ChangeLayer(layer_id, opacity=0.25).execute(session)
    changed = session.document

    assert changed.layers[1].id == layer_id
    assert changed.layers[1].opacity == 0.25


def test_layer_structure_operations_are_undoable() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)
    background_id = document.layers[0].id

    added = controller.add_layer("Overlay")
    assert len(added.layers) == 2
    overlay_id = added.layers[-1].id

    duplicated = controller.duplicate_layer(overlay_id)
    assert [layer.name for layer in duplicated.layers] == ["Background", "Overlay", "Overlay copy"]

    moved = controller.move_layer(overlay_id, -1)
    assert moved.layers[0].id == overlay_id
    assert moved.layers[1].id == background_id

    removed = controller.remove_layer(overlay_id)
    assert all(layer.id != overlay_id for layer in removed.layers)

    restored = controller.undo()
    assert restored.layers[0].id == overlay_id
    assert controller.undo().layers[0].name == "Background"


def test_layer_rename_and_multi_remove_are_atomic_and_undoable() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)
    first_id = document.layers[0].id
    document = controller.add_layer("Overlay")
    second_id = document.layers[1].id
    document = controller.add_layer("Highlights")
    third_id = document.layers[2].id

    renamed = controller.rename_layer(second_id, "Retouch")
    assert renamed.layers[1].name == "Retouch"

    removed = controller.remove_layers((second_id, third_id))
    assert [layer.id for layer in removed.layers] == [first_id]

    restored = controller.undo()
    assert [layer.name for layer in restored.layers] == ["Background", "Retouch", "Highlights"]
    assert controller.undo().layers[1].name == "Overlay"


def test_multi_layer_state_changes_are_one_undoable_command() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)
    document = controller.add_layer("Overlay")
    layer_ids = tuple(layer.id for layer in document.layers)

    changed = controller.set_layers_visibility(layer_ids, False)
    assert all(not layer.visible for layer in changed.layers)
    changed = controller.set_layers_opacity(layer_ids, 0.35)
    assert all(layer.opacity == 0.35 for layer in changed.layers)

    restored = controller.undo()
    assert all(not layer.visible for layer in restored.layers)
    assert all(layer.opacity == 1.0 for layer in restored.layers)
    assert controller.undo().layers[0].visible is True


def test_structure_operations_preserve_layer_identity() -> None:
    controller = EditorController(BlankDocumentRenderer())
    document = controller.create_document("sample", 10, 10)
    document = controller.add_layer("Overlay")
    overlay_id = document.layers[1].id

    duplicated = controller.duplicate_layer(overlay_id)
    duplicate_id = next(layer.id for layer in duplicated.layers if layer.id != overlay_id and layer.name == "Overlay copy")
    moved = controller.move_layer(overlay_id, -1)

    assert moved.layers[0].id == overlay_id
    assert duplicate_id in {layer.id for layer in moved.layers}
