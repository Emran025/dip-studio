"""Application commands for TextLayer creation and editing.

Both commands follow the ``Command`` Protocol: ``execute()`` + ``undo()``.
They live in ``application/`` (no Qt imports; Qt is only in infrastructure).

Architecture: doc-06 TextLayer — first-class editable layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import LayerId, TextLayer

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore


class AddTextLayer:
    """Insert a new TextLayer into the active document.

    ``execute()``
        1. Rasterises the ``TextLayer`` to an RGBA buffer via
           ``infrastructure.text_rasteriser``.
        2. Stores the buffer in ``data_store``.
        3. Inserts the layer (with its ``buffer_id``) at the top of the stack.

    ``undo()``
        Removes the layer and releases its pixel buffer.
    """

    label: str = "Add text layer"

    def __init__(self, data_store: ImageDataStore, text_layer: TextLayer) -> None:
        self._store = data_store
        self._prototype = text_layer
        self._inserted_layer: TextLayer | None = None
        self._inserted_buffer_id: str | None = None

    def execute(self, session: DocumentSession) -> None:
        from dip_studio.infrastructure.text_rasteriser import rasterise_text

        doc = session.document
        img_w = doc.image.width
        img_h = doc.image.height

        arr = rasterise_text(self._prototype, img_w, img_h)
        buffer_id = self._store.allocate(arr)
        self._inserted_buffer_id = buffer_id

        layer = TextLayer(
            id=self._prototype.id,
            name=self._prototype.name,
            text=self._prototype.text,
            font_family=self._prototype.font_family,
            font_size=self._prototype.font_size,
            bold=self._prototype.bold,
            italic=self._prototype.italic,
            color_rgba=self._prototype.color_rgba,
            alignment=self._prototype.alignment,
            direction=self._prototype.direction,
            letter_spacing=self._prototype.letter_spacing,
            line_spacing=self._prototype.line_spacing,
            background_color=self._prototype.background_color,
            buffer_id=buffer_id,
        )
        self._inserted_layer = layer
        new_layers = (layer,) + doc.layers
        session.replace(doc.changed(layers=new_layers))

    def undo(self, session: DocumentSession) -> None:
        if self._inserted_layer is None:
            return
        doc = session.document
        new_layers = tuple(la for la in doc.layers if la.id != self._inserted_layer.id)
        if self._inserted_buffer_id:
            self._store.release(self._inserted_buffer_id)
        session.replace(doc.changed(layers=new_layers))


class EditTextLayer:
    """Re-rasterise an existing ``TextLayer`` with new properties.

    ``execute()``
        1. Finds the layer by ``layer_id`` in the document.
        2. Re-rasterises with the new ``TextLayer`` prototype.
        3. Releases the old buffer and stores the new one.
        4. Replaces the layer in the document.

    ``undo()``
        Restores the old layer and its buffer.
    """

    label: str = "Edit text layer"

    def __init__(
        self,
        data_store: ImageDataStore,
        layer_id: LayerId,
        new_text_layer: TextLayer,
    ) -> None:
        self._store = data_store
        self._layer_id = layer_id
        self._new_prototype = new_text_layer
        self._old_layer: TextLayer | None = None
        self._old_snapshot_id: str | None = None  # snapshot of old buffer for undo
        self._new_buffer_id: str | None = None

    def execute(self, session: DocumentSession) -> None:
        from dip_studio.infrastructure.text_rasteriser import rasterise_text

        doc = session.document
        old = next((la for la in doc.layers if la.id == self._layer_id), None)
        if old is None or not isinstance(old, TextLayer):
            return
        self._old_layer = old

        # Snapshot old buffer so undo can restore pixels.
        if old.buffer_id and self._store.has(old.buffer_id):
            snap = self._store.get(old.buffer_id).copy()
            self._old_snapshot_id = self._store.allocate(snap)

        img_w = doc.image.width
        img_h = doc.image.height
        arr = rasterise_text(self._new_prototype, img_w, img_h)
        new_buffer_id = self._store.allocate(arr)
        self._new_buffer_id = new_buffer_id

        # Release old buffer (snapshot kept separately for undo).
        if old.buffer_id:
            self._store.release(old.buffer_id)

        new_layer = TextLayer(
            id=old.id,
            name=self._new_prototype.name,
            visible=old.visible,
            opacity=old.opacity,
            mask_id=old.mask_id,
            blend_mode=old.blend_mode,
            transform=old.transform,
            locked=old.locked,
            text=self._new_prototype.text,
            font_family=self._new_prototype.font_family,
            font_size=self._new_prototype.font_size,
            bold=self._new_prototype.bold,
            italic=self._new_prototype.italic,
            color_rgba=self._new_prototype.color_rgba,
            alignment=self._new_prototype.alignment,
            direction=self._new_prototype.direction,
            letter_spacing=self._new_prototype.letter_spacing,
            line_spacing=self._new_prototype.line_spacing,
            background_color=self._new_prototype.background_color,
            buffer_id=new_buffer_id,
        )
        new_layers = tuple(new_layer if la.id == self._layer_id else la for la in doc.layers)
        session.replace(doc.changed(layers=new_layers))

    def undo(self, session: DocumentSession) -> None:
        if self._old_layer is None:
            return
        doc = session.document
        # Release the new buffer.
        if self._new_buffer_id:
            self._store.release(self._new_buffer_id)
        # Restore old buffer from snapshot.
        restored_buf_id: str | None = self._old_snapshot_id
        restored = TextLayer(
            id=self._old_layer.id,
            name=self._old_layer.name,
            visible=self._old_layer.visible,
            opacity=self._old_layer.opacity,
            mask_id=self._old_layer.mask_id,
            blend_mode=self._old_layer.blend_mode,
            transform=self._old_layer.transform,
            locked=self._old_layer.locked,
            text=self._old_layer.text,
            font_family=self._old_layer.font_family,
            font_size=self._old_layer.font_size,
            bold=self._old_layer.bold,
            italic=self._old_layer.italic,
            color_rgba=self._old_layer.color_rgba,
            alignment=self._old_layer.alignment,
            direction=self._old_layer.direction,
            letter_spacing=self._old_layer.letter_spacing,
            line_spacing=self._old_layer.line_spacing,
            background_color=self._old_layer.background_color,
            buffer_id=restored_buf_id,
        )
        new_layers = tuple(restored if la.id == self._old_layer.id else la for la in doc.layers)
        session.replace(doc.changed(layers=new_layers))
