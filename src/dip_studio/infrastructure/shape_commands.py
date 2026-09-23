"""Undoable shape drawing commands for DIP Studio."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from dip_studio.application.commands import Command
from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import ImageDocument, LayerId, ShapeLayer, Transform
from dip_studio.infrastructure.data_store import ImageDataStore

COLOR_MAP: dict[str, tuple[int, int, int, int]] = {
    "Red": (255, 0, 0, 255),
    "Green": (0, 255, 0, 255),
    "Blue": (0, 0, 255, 255),
    "Yellow": (255, 255, 0, 255),
    "White": (255, 255, 255, 255),
    "Black": (0, 0, 0, 255),
    "Transparent": (0, 0, 0, 0),
    "None": (0, 0, 0, 0),
}


class DrawShape(Command):
    label = "Draw Shape"

    def __init__(
        self,
        data_store: ImageDataStore,
        layer_id: LayerId,
        shape_type: str,
        rect: tuple[int, int, int, int],  # (x, y, w, h)
        fill_color_name: str | tuple[int, int, int, int] = "Red",
        stroke_color_name: str | tuple[int, int, int, int] = "Black",
        stroke_width: int = 2,
    ) -> None:
        self._store = data_store
        self._layer_id = layer_id
        self._shape_type = shape_type.lower()
        self._rect = rect
        if isinstance(fill_color_name, tuple):
            self._fill_color = fill_color_name
        else:
            self._fill_color = COLOR_MAP.get(fill_color_name, (255, 0, 0, 255))

        if isinstance(stroke_color_name, tuple):
            self._stroke_color = stroke_color_name
        else:
            self._stroke_color = COLOR_MAP.get(stroke_color_name, (0, 0, 0, 255))
        self._stroke_width = max(1, stroke_width)
        self._created_layer_id: LayerId | None = None
        self._previous: ImageDocument | None = None

    @property
    def created_layer_id(self) -> LayerId | None:
        return self._created_layer_id

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        if not any(layer.id == self._layer_id for layer in document.layers):
            raise KeyError("Layer does not exist")
        x, y, w, h = self._rect
        if w <= 0 or h <= 0:
            raise ValueError("Shape dimensions must be positive")
        if self._shape_type not in ("rectangle", "ellipse", "circle", "line", "polygon"):
            raise ValueError(f"Unsupported shape type: {self._shape_type}")
        if self._shape_type == "circle":
            self._shape_type = "ellipse"
        vertices = (float(x), float(y), float(w), float(h))
        shape = ShapeLayer(
            id=LayerId(uuid4()),
            name=f"{self._shape_type.title()} shape",
            stroke_color=self._stroke_color,
            fill_color=self._fill_color,
            stroke_width=float(self._stroke_width),
            shape_type=self._shape_type,
            vertices=vertices,
        )
        self._created_layer_id = shape.id
        layers = document.layers + (shape,)
        self._previous = document
        session.replace(document.changed(layers=layers))

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Draw shape command has not executed")
        session.replace(self._previous)


class ResizeShapeLayer(Command):
    label = "Resize Shape"

    def __init__(
        self,
        layer_id: LayerId,
        rect: tuple[int, int, int, int],
    ) -> None:
        self._layer_id = layer_id
        self._rect = rect
        self._previous: ImageDocument | None = None

    def execute(self, session: DocumentSession) -> None:
        document = session.document
        layer = next((item for item in document.layers if item.id == self._layer_id), None)
        if not isinstance(layer, ShapeLayer):
            raise ValueError("Resize requires a shape layer")
        x, y, width, height = self._rect
        if width <= 0 or height <= 0:
            raise ValueError("Shape dimensions must be positive")
        updated = replace(
            layer,
            vertices=(float(x), float(y), float(width), float(height)),
            transform=Transform(),
        )
        self._previous = document
        session.replace(
            document.changed(
                layers=tuple(updated if item.id == layer.id else item for item in document.layers)
            )
        )

    def undo(self, session: DocumentSession) -> None:
        if self._previous is None:
            raise RuntimeError("Resize shape command has not executed")
        session.replace(self._previous)
