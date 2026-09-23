"""Undoable layer state transitions."""

from __future__ import annotations

from uuid import uuid4

from dip_studio.application.commands import Command
from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import (
    _UNSET,
    GroupLayer,
    ImageDocument,
    Layer,
    LayerId,
    Transform,
)


class ChangeLayer(Command):
    label = "Change Layer"

    def __init__(
        self,
        layer_id: LayerId,
        *,
        visible: bool | None = None,
        opacity: float | None = None,
        blend_mode: str | None = None,
        locked: bool | None = None,
        buffer_id: str | None = None,
        transform: Transform | None | object = _UNSET,
    ) -> None:
        self._layer_id = layer_id
        self._visible = visible
        self._opacity = opacity
        self._blend_mode = blend_mode
        self._locked = locked
        self._buffer_id = buffer_id
        self._transform = transform
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (
                position
                for position, layer in enumerate(document.layers)
                if layer.id == self._layer_id
            ),
            None,
        )
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        updated = layer.changed(
            visible=self._visible,
            opacity=self._opacity,
            blend_mode=self._blend_mode,
            locked=self._locked,
            buffer_id=self._buffer_id if self._buffer_id is not None else layer.buffer_id,
            transform=self._transform,
        )
        layers = document.layers[:index] + (updated,) + document.layers[index + 1 :]
        self._previous = document
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Layer command has not executed")
        session.replace(self._previous)


class TranslateLayer(Command):
    label = "Move Layer Position"

    def __init__(self, layer_id: LayerId, dx: float, dy: float) -> None:
        self._layer_id = layer_id
        self._dx = dx
        self._dy = dy
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (
                position
                for position, layer in enumerate(document.layers)
                if layer.id == self._layer_id
            ),
            None,
        )
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        if layer.locked:
            raise RuntimeError(f"Layer '{layer.name}' is locked")
        current_t = layer.transform or Transform()
        new_t = Transform(
            tx=current_t.tx + self._dx,
            ty=current_t.ty + self._dy,
            sx=current_t.sx,
            sy=current_t.sy,
            rotation=current_t.rotation,
            skew_x=current_t.skew_x,
            skew_y=current_t.skew_y,
        )
        updated = layer.changed(transform=new_t)
        layers = document.layers[:index] + (updated,) + document.layers[index + 1 :]
        self._previous = document
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Translate layer command has not executed")
        session.replace(self._previous)


class ChangeLayers(Command):
    label = "Change Layers"

    def __init__(
        self,
        layer_ids: tuple[LayerId, ...],
        *,
        visible: bool | None = None,
        opacity: float | None = None,
    ) -> None:
        self._layer_ids = layer_ids
        self._visible = visible
        self._opacity = opacity
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        selected = set(self._layer_ids)
        if not selected or not selected.issubset({layer.id for layer in document.layers}):
            raise KeyError("Layer does not exist")
        if self._visible is None and self._opacity is None:
            raise ValueError("Layer change has no state")
        updated = tuple(
            layer.changed(visible=self._visible, opacity=self._opacity)
            if layer.id in selected
            else layer
            for layer in document.layers
        )
        self._previous = document
        session.replace(document.changed(layers=updated))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Change layers command has not executed")
        session.replace(self._previous)


class ChangeLayersLocked(Command):
    label = "Lock Layers"

    def __init__(self, layer_ids: tuple[LayerId, ...], locked: bool) -> None:
        self._layer_ids = layer_ids
        self._locked = locked
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        selected = set(self._layer_ids)
        if not selected or not selected.issubset({layer.id for layer in document.layers}):
            raise KeyError("Layer does not exist")
        self._previous = document
        session.replace(
            document.changed(
                layers=tuple(
                    layer.changed(locked=self._locked) if layer.id in selected else layer
                    for layer in document.layers
                )
            )
        )

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Lock layers command has not executed")
        session.replace(self._previous)


class RenameLayer(Command):
    label = "Rename Layer"

    def __init__(self, layer_id: LayerId, name: str) -> None:
        self._layer_id = layer_id
        self._name = name
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None
        )
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        updated = layer.changed(name=self._name)
        self._previous = document
        session.replace(
            document.changed(
                layers=document.layers[:index] + (updated,) + document.layers[index + 1 :]
            )
        )

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Rename layer command has not executed")
        session.replace(self._previous)


class AddLayer(Command):
    label = "Add Layer"

    def __init__(
        self,
        name: str,
        *,
        source: Layer | None = None,
        index: int | None = None,
    ) -> None:
        self._layer = source or Layer(LayerId(uuid4()), name)
        self._index = index
        self._previous: ImageDocument | None = None

    @property
    def layer_id(self) -> LayerId:
        return self._layer.id

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = len(document.layers) if self._index is None else self._index
        if not 0 <= index <= len(document.layers):
            raise IndexError("Layer insertion index is out of range")
        self._previous = document
        layers = document.layers[:index] + (self._layer,) + document.layers[index:]
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Add layer command has not executed")
        session.replace(self._previous)


class PasteLayers(Command):
    label = "Paste Layers"

    def __init__(self, layers: tuple[Layer, ...], index: int | None = None) -> None:
        if not layers:
            raise ValueError("At least one layer is required")
        self._layers = layers
        self._index = index
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = len(document.layers) if self._index is None else self._index
        if not 0 <= index <= len(document.layers):
            raise IndexError("Layer insertion index is out of range")
        self._previous = document
        updated = document.layers[:index] + self._layers + document.layers[index:]
        session.replace(document.changed(layers=updated))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Paste layers command has not executed")
        session.replace(self._previous)


class RemoveLayer(Command):
    label = "Remove Layer"

    def __init__(self, layer_id: LayerId) -> None:
        self._layer_id = layer_id
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None
        )
        if index is None:
            raise KeyError("Layer does not exist")
        if len(document.layers) == 1:
            raise ValueError("The document must contain at least one layer")
        self._previous = document
        layers = document.layers[:index] + document.layers[index + 1 :]
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Remove layer command has not executed")
        session.replace(self._previous)


class RemoveLayers(Command):
    label = "Remove Layers"

    def __init__(self, layer_ids: tuple[LayerId, ...]) -> None:
        self._layer_ids = layer_ids
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        if not self._layer_ids or not set(self._layer_ids).issubset(
            {layer.id for layer in document.layers}
        ):
            raise KeyError("Layer does not exist")
        if len(document.layers) - len(self._layer_ids) < 1:
            raise ValueError("The document must contain at least one layer")
        self._previous = document
        layers = tuple(layer for layer in document.layers if layer.id not in self._layer_ids)
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Remove layers command has not executed")
        session.replace(self._previous)


class MoveLayer(Command):
    label = "Move Layer"

    def __init__(self, layer_id: LayerId, delta: int) -> None:
        self._layer_id = layer_id
        self._delta = delta
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None
        )
        if index is None:
            raise KeyError("Layer does not exist")
        target = index + self._delta
        if not 0 <= target < len(document.layers):
            raise IndexError("Layer cannot move outside the document")
        self._previous = document
        ordered = list(document.layers)
        ordered[index], ordered[target] = ordered[target], ordered[index]
        session.replace(document.changed(layers=tuple(ordered)))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Move layer command has not executed")
        session.replace(self._previous)


class DuplicateLayer(AddLayer):
    label = "Duplicate Layer"

    def __init__(self, source: Layer, index: int, buffer_id: str | None = None) -> None:
        copied = Layer(
            id=LayerId(uuid4()),
            name=f"{source.name} copy",
            visible=source.visible,
            opacity=source.opacity,
            buffer_id=buffer_id if buffer_id is not None else source.buffer_id,
            mask_id=source.mask_id,
            blend_mode=source.blend_mode,
            transform=source.transform,
            locked=source.locked,
        )
        super().__init__(copied.name, source=copied, index=index)


class SetLayerBlendMode(Command):
    label = "Change Blend Mode"

    def __init__(self, layer_id: LayerId, blend_mode: str) -> None:
        self._layer_id = layer_id
        self._blend_mode = blend_mode
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None
        )
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        updated = layer.changed(blend_mode=self._blend_mode)
        self._previous = document
        session.replace(
            document.changed(
                layers=document.layers[:index] + (updated,) + document.layers[index + 1 :]
            )
        )

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Command has not executed")
        session.replace(self._previous)


class SetLayerLocked(Command):
    label = "Lock Layer"

    def __init__(self, layer_id: LayerId, locked: bool) -> None:
        self._layer_id = layer_id
        self._locked = locked
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None
        )
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        updated = layer.changed(locked=self._locked)
        self._previous = document
        session.replace(
            document.changed(
                layers=document.layers[:index] + (updated,) + document.layers[index + 1 :]
            )
        )

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Command has not executed")
        session.replace(self._previous)


class GroupLayers(Command):
    label = "Group Layers"

    def __init__(self, layer_ids: tuple[LayerId, ...], name: str = "Group") -> None:
        self._layer_ids = layer_ids
        self._name = name
        self._group_id: LayerId | None = None
        self._previous: ImageDocument | None = None

    @property
    def group_id(self) -> LayerId | None:
        return self._group_id

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        selected = set(self._layer_ids)
        if len(selected) < 1:
            raise ValueError("Select at least one layer to group")
        if not selected.issubset({layer.id for layer in document.layers}):
            raise KeyError("Layer does not exist")
        children = tuple(layer.id for layer in document.layers if layer.id in selected)
        group = GroupLayer(
            id=LayerId(uuid4()),
            name=self._name,
            children=children,
        )
        self._group_id = group.id
        self._previous = document
        session.replace(document.changed(layers=document.layers + (group,)))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Group command has not executed")
        session.replace(self._previous)


class UngroupLayer(Command):
    label = "Ungroup Layers"

    def __init__(self, group_id: LayerId) -> None:
        self._group_id = group_id
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        group = next((layer for layer in document.layers if layer.id == self._group_id), None)
        if not isinstance(group, GroupLayer):
            raise ValueError("Selected layer is not a group")
        self._previous = document
        session.replace(
            document.changed(
                layers=tuple(layer for layer in document.layers if layer.id != group.id)
            )
        )

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Ungroup command has not executed")
        session.replace(self._previous)


class MergeDown(Command):
    label = "Merge Down"

    def __init__(
        self,
        upper_layer_id: LayerId,
        lower_layer_id: LayerId,
        merged_buffer_id: str | None,
    ) -> None:
        self._upper_id = upper_layer_id
        self._lower_id = lower_layer_id
        self._merged_buffer_id = merged_buffer_id
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        idx_upper = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._upper_id), None
        )
        idx_lower = next(
            (i for i, layer in enumerate(document.layers) if layer.id == self._lower_id), None
        )
        if idx_upper is None or idx_lower is None:
            raise KeyError("Layers do not exist")
        lower_layer = document.layers[idx_lower]
        merged_layer = lower_layer.changed(buffer_id=self._merged_buffer_id)
        layers = tuple(
            merged_layer if layer.id == self._lower_id else layer
            for layer in document.layers
            if layer.id != self._upper_id
        )
        self._previous = document
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Command has not executed")
        session.replace(self._previous)


class CropDocument(Command):
    label = "Crop Document"

    def __init__(
        self,
        new_width: int,
        new_height: int,
        layer_buffer_map: dict[LayerId, str],
    ) -> None:
        self._new_width = new_width
        self._new_height = new_height
        self._layer_buffer_map = layer_buffer_map
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        new_spec = document.image.changed(width=self._new_width, height=self._new_height)
        new_layers = tuple(
            layer.changed(
                buffer_id=self._layer_buffer_map.get(layer.id, layer.buffer_id),
                transform=None,
            )
            for layer in document.layers
        )
        self._previous = document
        session.replace(document.changed(image=new_spec, layers=new_layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Command has not executed")
        session.replace(self._previous)
