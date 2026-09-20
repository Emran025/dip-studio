"""Undoable layer state transitions."""

from dip_studio.application.commands import Command
from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import ImageDocument, Layer, LayerId
from uuid import uuid4


class ChangeLayer(Command):
    def __init__(
        self,
        layer_id: LayerId,
        *,
        visible: bool | None = None,
        opacity: float | None = None,
    ) -> None:
        self._layer_id = layer_id
        self._visible = visible
        self._opacity = opacity
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next(
            (position for position, layer in enumerate(document.layers) if layer.id == self._layer_id),
            None,
        )
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        updated = Layer(
            layer.id,
            layer.name,
            layer.visible if self._visible is None else self._visible,
            layer.opacity if self._opacity is None else self._opacity,
        )
        layers = document.layers[:index] + (updated,) + document.layers[index + 1 :]
        self._previous = document
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Layer command has not executed")
        session.replace(self._previous)


class ChangeLayers(Command):
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
            Layer(
                layer.id,
                layer.name,
                layer.visible if self._visible is None else self._visible,
                layer.opacity if self._opacity is None else self._opacity,
            )
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


class RenameLayer(Command):
    def __init__(self, layer_id: LayerId, name: str) -> None:
        self._layer_id = layer_id
        self._name = name
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next((i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None)
        if index is None:
            raise KeyError("Layer does not exist")
        layer = document.layers[index]
        updated = Layer(layer.id, self._name, layer.visible, layer.opacity)
        self._previous = document
        session.replace(document.changed(layers=document.layers[:index] + (updated,) + document.layers[index + 1:]))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Rename layer command has not executed")
        session.replace(self._previous)


class AddLayer(Command):
    def __init__(self, name: str, *, source: Layer | None = None, index: int | None = None) -> None:
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


class RemoveLayer(Command):
    def __init__(self, layer_id: LayerId) -> None:
        self._layer_id = layer_id
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next((i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None)
        if index is None:
            raise KeyError("Layer does not exist")
        if len(document.layers) == 1:
            raise ValueError("The document must contain at least one layer")
        self._previous = document
        layers = document.layers[:index] + document.layers[index + 1:]
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Remove layer command has not executed")
        session.replace(self._previous)


class RemoveLayers(Command):
    def __init__(self, layer_ids: tuple[LayerId, ...]) -> None:
        self._layer_ids = layer_ids
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        if not self._layer_ids or not set(self._layer_ids).issubset({layer.id for layer in document.layers}):
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
    def __init__(self, layer_id: LayerId, delta: int) -> None:
        self._layer_id = layer_id
        self._delta = delta
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        index = next((i for i, layer in enumerate(document.layers) if layer.id == self._layer_id), None)
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
    def __init__(self, source: Layer, index: int) -> None:
        super().__init__(f"{source.name} copy", source=Layer(LayerId(uuid4()), f"{source.name} copy"), index=index)
