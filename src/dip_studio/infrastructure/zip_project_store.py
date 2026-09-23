"""Zip-based project store that persists both metadata and pixel buffers.

Format version 2: a ``.dip`` file is a ZIP archive containing:

    metadata.json          — JSON document metadata
    buffers/<uuid>.npy     — one NumPy ``.npy`` file per layer ``buffer_id``
    masks/<uuid>.npy       — one NumPy ``.npy`` file per mask ``buffer_id``

Legacy version-1 ``.dip`` files (plain JSON) are detected and loaded via the
fallback ``JsonProjectStore`` so no data is ever lost on upgrade.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import numpy as np

from dip_studio.core.errors import PersistenceError
from dip_studio.domain.model import (
    AdjustmentLayer,
    AppliedOperation,
    DocumentId,
    FilterLayer,
    GroupLayer,
    ImageDocument,
    ImageSpec,
    Layer,
    LayerId,
    Mask,
    SelectionRect,
    ShapeLayer,
    TextLayer,
    Transform,
)

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _transform_to_dict(t: Transform | None) -> dict[str, float] | None:
    if t is None:
        return None
    return {
        "tx": t.tx,
        "ty": t.ty,
        "sx": t.sx,
        "sy": t.sy,
        "rotation": t.rotation,
        "skew_x": t.skew_x,
        "skew_y": t.skew_y,
    }


def _dict_to_transform(raw: dict[str, Any] | None) -> Transform | None:
    if raw is None:
        return None
    return Transform(
        tx=float(raw.get("tx", 0.0)),
        ty=float(raw.get("ty", 0.0)),
        sx=float(raw.get("sx", 1.0)),
        sy=float(raw.get("sy", 1.0)),
        rotation=float(raw.get("rotation", 0.0)),
        skew_x=float(raw.get("skew_x", 0.0)),
        skew_y=float(raw.get("skew_y", 0.0)),
    )


def _layer_to_dict(layer: Layer) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "layer_type": type(layer).__name__,
        "id": str(layer.id),
        "name": layer.name,
        "visible": layer.visible,
        "opacity": layer.opacity,
        "buffer_id": layer.buffer_id,
        "mask_id": layer.mask_id,
        "blend_mode": layer.blend_mode,
        "transform": _transform_to_dict(layer.transform),
        "locked": layer.locked,
    }
    if isinstance(layer, TextLayer):
        raw.update(
            {
                "text": layer.text,
                "font_family": layer.font_family,
                "font_size": layer.font_size,
                "bold": layer.bold,
                "italic": layer.italic,
                "color_rgba": list(layer.color_rgba),
                "alignment": layer.alignment,
                "direction": layer.direction,
                "letter_spacing": layer.letter_spacing,
                "line_spacing": layer.line_spacing,
                "background_color": list(layer.background_color),
            }
        )
    elif isinstance(layer, ShapeLayer):
        raw.update(
            {
                "shape_type": layer.shape_type,
                "stroke_color": list(layer.stroke_color),
                "fill_color": list(layer.fill_color),
                "stroke_width": layer.stroke_width,
                "vertices": list(layer.vertices),
            }
        )
    elif isinstance(layer, AdjustmentLayer):
        raw.update(
            {
                "adjustment_type": layer.adjustment_type,
                "adjustment_params": list(layer.adjustment_params),
            }
        )
        if isinstance(layer, FilterLayer):
            raw.update(
                {
                    "filter_type": layer.filter_type,
                    "filter_params": list(layer.filter_params),
                }
            )
    elif isinstance(layer, GroupLayer):
        raw.update(
            {
                "children": [str(child) for child in layer.children],
                "pass_through": layer.pass_through,
            }
        )
    return raw


def _mask_to_dict(mask: Mask) -> dict[str, Any]:
    return {
        "id": mask.id,
        "name": mask.name,
        "width": mask.width,
        "height": mask.height,
        "mode": mask.mode,
        "buffer_id": mask.buffer_id,
        "enabled": mask.enabled,
    }


def _selection_to_dict(selection: SelectionRect) -> dict[str, Any]:
    return {
        "x": selection.x,
        "y": selection.y,
        "width": selection.width,
        "height": selection.height,
        "feather": selection.feather,
        "kind": selection.kind,
        "mask_buffer_id": selection.mask_buffer_id,
    }


def _rgba(raw: Any, field_name: str) -> tuple[int, int, int, int]:
    values = tuple(int(value) for value in raw)
    if len(values) != 4:
        raise PersistenceError(f"{field_name} must contain four channels")
    return values


def _layer_from_dict(raw: dict[str, Any]) -> Layer:
    """Reconstruct a Layer (or subclass) from its serialised dictionary.

    The ``buffer_id`` stored here is the *original* UUID string; the caller is
    responsible for remapping it to the new ID allocated in ``ImageDataStore``.
    """
    common = dict(
        id=LayerId(UUID(raw["id"])),
        name=raw["name"],
        visible=bool(raw.get("visible", True)),
        opacity=float(raw.get("opacity", 1.0)),
        buffer_id=raw.get("buffer_id"),  # may be None or old UUID string
        mask_id=raw.get("mask_id"),
        blend_mode=str(raw.get("blend_mode", "normal")),
        transform=_dict_to_transform(raw.get("transform")),
        locked=bool(raw.get("locked", False)),
    )
    layer_type = raw.get("layer_type", "Layer")
    if layer_type == "TextLayer":
        return TextLayer(
            **common,
            text=str(raw.get("text", "")),
            font_family=str(raw.get("font_family", "Arial")),
            font_size=int(raw.get("font_size", 24)),
            bold=bool(raw.get("bold", False)),
            italic=bool(raw.get("italic", False)),
            color_rgba=_rgba(raw.get("color_rgba", (0, 0, 0, 255)), "color_rgba"),
            alignment=str(raw.get("alignment", "left")),
            direction=str(raw.get("direction", "ltr")),
            letter_spacing=float(raw.get("letter_spacing", 0.0)),
            line_spacing=float(raw.get("line_spacing", 1.2)),
            background_color=_rgba(
                raw.get("background_color", (0, 0, 0, 0)),
                "background_color",
            ),
        )
    if layer_type == "ShapeLayer":
        return ShapeLayer(
            **common,
            shape_type=str(raw.get("shape_type", "rectangle")),
            stroke_color=_rgba(raw.get("stroke_color", (0, 0, 0, 255)), "stroke_color"),
            fill_color=_rgba(raw.get("fill_color", (0, 0, 0, 0)), "fill_color"),
            stroke_width=float(raw.get("stroke_width", 1.0)),
            vertices=tuple(float(value) for value in raw.get("vertices", ())),
        )
    if layer_type == "AdjustmentLayer":
        return AdjustmentLayer(
            **common,
            adjustment_type=str(raw.get("adjustment_type", "")),
            adjustment_params=tuple(
                (str(item[0]), str(item[1])) for item in raw.get("adjustment_params", ())
            ),
        )
    if layer_type == "FilterLayer":
        return FilterLayer(
            **common,
            adjustment_type=str(raw.get("adjustment_type", "")),
            adjustment_params=tuple(
                (str(item[0]), str(item[1])) for item in raw.get("adjustment_params", ())
            ),
            filter_type=str(raw.get("filter_type", "")),
            filter_params=tuple(
                (str(item[0]), str(item[1])) for item in raw.get("filter_params", ())
            ),
        )
    if layer_type == "GroupLayer":
        return GroupLayer(
            **common,
            children=tuple(LayerId(UUID(child)) for child in raw.get("children", ())),
            pass_through=bool(raw.get("pass_through", True)),
        )
    return Layer(**common)


# ---------------------------------------------------------------------------
# ZipProjectStore
# ---------------------------------------------------------------------------


class ZipProjectStore:
    """Saves and loads ``.dip`` projects as ZIP archives (format version 2).

    Args:
        data_store: The shared ``ImageDataStore`` used to read pixel buffers on
            save and to allocate new buffers on load.
    """

    format_version = 2
    max_archive_members = 2048
    max_archive_expanded_size = 512 * 1024 * 1024

    def __init__(self, data_store: ImageDataStore) -> None:
        self._store = data_store

    @staticmethod
    def _manifest_checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _manifest_file_name(path: Path) -> str:
        return f"{path.stem}.manifest.json"

    @staticmethod
    def _ensure_safe_member_name(name: str) -> str:
        candidate = name.replace("\\", "/")
        if not candidate or candidate.startswith("/"):
            raise PersistenceError("Project archive contains unsafe members")
        if re.match(r"^[A-Za-z]:", candidate):
            raise PersistenceError("Project archive contains unsafe members")
        parts = candidate.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise PersistenceError("Project archive contains unsafe members")
        if candidate.startswith("./"):
            raise PersistenceError("Project archive contains unsafe members")
        return candidate

    @classmethod
    def _validate_archive_members(cls, zf: zipfile.ZipFile) -> None:
        seen: set[str] = set()
        total_expanded_size = 0
        for info in zf.infolist():
            member_name = cls._ensure_safe_member_name(info.filename)
            if member_name in seen:
                raise PersistenceError("Project archive contains duplicate members")
            seen.add(member_name)
            if info.is_dir():
                continue
            total_expanded_size += info.file_size
            if total_expanded_size > cls.max_archive_expanded_size:
                raise PersistenceError("Project archive exceeds allowable expanded size")
        if len(seen) > cls.max_archive_members:
            raise PersistenceError("Project archive contains too many members")
        if "metadata.json" not in seen:
            raise PersistenceError("Project archive is missing metadata.json")

    @staticmethod
    def _require_member(zf: zipfile.ZipFile, archive_path: str, context: str) -> None:
        try:
            zf.getinfo(archive_path)
        except KeyError as exc:
            raise PersistenceError(
                f"Missing archive member '{archive_path}' for {context}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API (matches ``ProjectStore`` Protocol)
    # ------------------------------------------------------------------

    def save(self, document: ImageDocument, path: Path) -> None:
        """Atomically save *document* (metadata + pixel buffers) to *path*."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            buf = io.BytesIO()
            payload = json.dumps(self._to_payload(document), ensure_ascii=False, indent=2).encode(
                "utf-8"
            )
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                # 1. Metadata JSON
                zf.writestr("metadata.json", payload)
                zf.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format_version": self.format_version,
                            "created_at": datetime.now(UTC).isoformat(),
                            "sha256": self._manifest_checksum(payload),
                            "document_id": str(document.id),
                            "revision": document.revision,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
                # 2. Layer pixel buffers
                written_buffers: set[str] = set()
                written_masks: set[str] = set()
                for layer in document.layers:
                    if layer.buffer_id is not None:
                        if not self._store.has(layer.buffer_id):
                            raise PersistenceError(
                                f"Missing pixel buffer '{layer.buffer_id}' for layer '{layer.name}'"
                            )
                        if layer.buffer_id not in written_buffers:
                            arr = self._store.get(layer.buffer_id)
                            npy_buf = io.BytesIO()
                            np.save(npy_buf, arr)
                            zf.writestr(
                                f"buffers/{layer.buffer_id}.npy",
                                npy_buf.getvalue(),
                            )
                            written_buffers.add(layer.buffer_id)
                    # 3. Mask buffers
                    if layer.mask_id is not None:
                        if not self._store.has(layer.mask_id):
                            raise PersistenceError(
                                f"Missing mask buffer '{layer.mask_id}' for layer '{layer.name}'"
                            )
                        if layer.mask_id not in written_masks:
                            arr = self._store.get(layer.mask_id)
                            npy_buf = io.BytesIO()
                            np.save(npy_buf, arr)
                            zf.writestr(
                                f"masks/{layer.mask_id}.npy",
                                npy_buf.getvalue(),
                            )
                            written_masks.add(layer.mask_id)
                for mask in document.masks:
                    if mask.buffer_id is None:
                        continue
                    if not self._store.has(mask.buffer_id):
                        raise PersistenceError(
                            f"Missing mask buffer '{mask.buffer_id}' for mask '{mask.name}'"
                        )
                    if mask.buffer_id in written_masks:
                        continue
                    npy_buf = io.BytesIO()
                    np.save(npy_buf, self._store.get(mask.buffer_id))
                    zf.writestr(f"masks/{mask.buffer_id}.npy", npy_buf.getvalue())
                    written_masks.add(mask.buffer_id)
                for selection in document.selections:
                    if selection.mask_buffer_id is None:
                        continue
                    if not self._store.has(selection.mask_buffer_id):
                        raise PersistenceError(
                            f"Missing selection mask buffer '{selection.mask_buffer_id}'"
                        )
                    if selection.mask_buffer_id in written_masks:
                        continue
                    npy_buf = io.BytesIO()
                    np.save(npy_buf, self._store.get(selection.mask_buffer_id))
                    zf.writestr(f"masks/{selection.mask_buffer_id}.npy", npy_buf.getvalue())
                    written_masks.add(selection.mask_buffer_id)
            # Atomic write via temp file + rename.
            tmp.write_bytes(buf.getvalue())
            os.replace(tmp, path)
        except OSError as exc:
            raise PersistenceError(f"Could not save project: {path}") from exc
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def load(self, path: Path) -> ImageDocument:
        """Load a ``.dip`` ZIP archive from *path* into an ``ImageDocument``.

        All pixel buffers are allocated fresh in ``self._store``.  The new
        ``buffer_id`` values are threaded into the returned document so all
        layer references remain consistent.
        """
        try:
            with zipfile.ZipFile(path, mode="r") as zf:
                self._validate_archive_members(zf)
                self._require_member(zf, "metadata.json", "project metadata")
                raw = json.loads(zf.read("metadata.json").decode("utf-8"))
                if int(raw.get("format_version", 0)) != self.format_version:
                    raise PersistenceError(
                        f"Unsupported project format version: {raw.get('format_version')}"
                    )
                manifest_name = self._manifest_file_name(path)
                if manifest_name in zf.namelist():
                    manifest = json.loads(zf.read(manifest_name).decode("utf-8"))
                    actual = self._manifest_checksum(zf.read("metadata.json"))
                    expected = manifest.get("sha256")
                    if expected is not None and actual != expected:
                        raise PersistenceError("Project archive manifest checksum mismatch")
                doc_raw = raw["document"]
                # Build image spec
                img = doc_raw["image"]
                image_spec = ImageSpec(
                    width=int(img["width"]),
                    height=int(img["height"]),
                    channels=int(img.get("channels", 4)),
                    bit_depth=int(img.get("bit_depth", 8)),
                    color_space=str(img.get("color_space", "sRGB")),
                    has_alpha=bool(img.get("has_alpha", True)),
                )
                # Reconstruct layers with remapped buffer IDs
                layers = []
                buffer_id_map: dict[str, str] = {}
                for layer_raw in doc_raw.get("layers", []):
                    layer = _layer_from_dict(layer_raw)
                    old_buf_id = layer.buffer_id
                    new_buf_id: str | None = None
                    if old_buf_id is not None:
                        archive_path = f"buffers/{old_buf_id}.npy"
                        if archive_path not in zf.namelist():
                            raise PersistenceError(
                                f"Missing pixel buffer '{old_buf_id}' for layer '{layer.name}'"
                            )
                        arr = np.load(io.BytesIO(zf.read(archive_path)), allow_pickle=False)
                        self._validate_buffer_array(arr, image_spec, old_buf_id, layer.name)
                        new_buf_id = self._store.allocate(arr)
                        buffer_id_map[str(old_buf_id)] = new_buf_id
                    old_mask_id = layer.mask_id
                    new_mask_id: str | None = None
                    if old_mask_id is not None:
                        archive_path = f"masks/{old_mask_id}.npy"
                        if archive_path not in zf.namelist():
                            raise PersistenceError(
                                f"Missing mask buffer '{old_mask_id}' for layer '{layer.name}'"
                            )
                        arr = np.load(io.BytesIO(zf.read(archive_path)), allow_pickle=False)
                        self._validate_mask_array(arr, old_mask_id, layer.name)
                        new_mask_id = self._store.allocate(arr)
                    layers.append(
                        replace(
                            layer,
                            buffer_id=new_buf_id,
                            mask_id=new_mask_id,
                        )
                    )
                # Operations
                ops = tuple(
                    AppliedOperation(
                        str(op["operation"]),
                        tuple((str(p[0]), str(p[1])) for p in op.get("parameters", [])),
                    )
                    for op in doc_raw.get("operations", [])
                )
                remapped_masks: list[Mask] = []
                mask_ids: dict[str, str] = {}
                for mask_raw in doc_raw.get("masks", []):
                    old_mask_id = mask_raw.get("buffer_id")
                    new_mask_id = None
                    if old_mask_id is not None:
                        archive_path = f"masks/{old_mask_id}.npy"
                        if archive_path not in zf.namelist():
                            raise PersistenceError(
                                f"Missing mask buffer '{old_mask_id}' for mask "
                                f"'{mask_raw.get('name', '')}'"
                            )
                        arr = np.load(io.BytesIO(zf.read(archive_path)), allow_pickle=False)
                        self._validate_mask_array(
                            arr, str(old_mask_id), str(mask_raw.get("name", ""))
                        )
                        new_mask_id = self._store.allocate(arr)
                        mask_ids[str(old_mask_id)] = new_mask_id
                    remapped_masks.append(
                        Mask(
                            id=str(mask_raw["id"]),
                            name=str(mask_raw["name"]),
                            width=int(mask_raw["width"]),
                            height=int(mask_raw["height"]),
                            mode=str(mask_raw.get("mode", "reveal")),
                            buffer_id=new_mask_id,
                            enabled=bool(mask_raw.get("enabled", True)),
                        )
                    )
                selection_values: list[SelectionRect] = []
                for item in doc_raw.get("selections", []):
                    old_selection_mask = item.get("mask_buffer_id")
                    if old_selection_mask is not None and str(old_selection_mask) not in mask_ids:
                        archive_path = f"masks/{old_selection_mask}.npy"
                        if archive_path not in zf.namelist():
                            raise PersistenceError(
                                f"Missing selection mask buffer '{old_selection_mask}'"
                            )
                        arr = np.load(io.BytesIO(zf.read(archive_path)), allow_pickle=False)
                        self._validate_mask_array(arr, str(old_selection_mask), "selection")
                        mask_ids[str(old_selection_mask)] = self._store.allocate(arr)
                    selection_values.append(
                        SelectionRect(
                            x=int(item["x"]),
                            y=int(item["y"]),
                            width=int(item["width"]),
                            height=int(item["height"]),
                            feather=float(item.get("feather", 0.0)),
                            kind=str(item.get("kind", "rectangle")),
                            mask_buffer_id=(
                                mask_ids.get(str(old_selection_mask))
                                if old_selection_mask is not None
                                else None
                            ),
                        )
                    )
                selections = tuple(selection_values)
                metadata_raw = dict(doc_raw.get("metadata", {}))
                workspace_raw = dict(doc_raw.get("workspace_metadata", metadata_raw))
                buffer_metadata_raw = {
                    str(key): dict(value)
                    for key, value in dict(doc_raw.get("buffer_metadata", {})).items()
                }
                cv_objects_raw = [dict(item) for item in doc_raw.get("cv_objects", [])]
                remapped_buffer_metadata = []
                for raw_key, raw_value in buffer_metadata_raw.items():
                    resolved_key = buffer_id_map.get(str(raw_key), str(raw_key))
                    if self._store.has(resolved_key):
                        remapped_buffer_metadata.append((resolved_key, dict(raw_value)))
                    elif raw_key in buffer_id_map:
                        remapped_buffer_metadata.append(
                            (buffer_id_map[str(raw_key)], dict(raw_value))
                        )
                return ImageDocument(
                    id=DocumentId(UUID(doc_raw["id"])),
                    name=str(doc_raw["name"]),
                    image=image_spec,
                    layers=tuple(layers),
                    revision=int(doc_raw.get("revision", 0)),
                    saved_revision=int(doc_raw.get("revision", 0)),
                    operations=ops,
                    masks=tuple(remapped_masks),
                    selections=selections,
                    metadata=tuple((str(key), str(value)) for key, value in metadata_raw.items()),
                    workspace_metadata=tuple(
                        (str(key), str(value)) for key, value in workspace_raw.items()
                    ),
                    buffer_metadata=tuple(remapped_buffer_metadata),
                    cv_objects=tuple(cv_objects_raw),
                )
        except PersistenceError:
            raise
        except (zipfile.BadZipFile, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PersistenceError(f"Could not load project: {path}") from exc
        except OSError as exc:
            raise PersistenceError(f"Could not open project file: {path}") from exc

    @staticmethod
    def _validate_buffer_array(
        array: np.ndarray,
        image_spec: ImageSpec,
        buffer_id: str,
        layer_name: str,
    ) -> None:
        if array.ndim not in (2, 3):
            raise PersistenceError(
                f"Invalid pixel buffer '{buffer_id}' for layer '{layer_name}': expected 2-D or 3-D"
            )
        if array.ndim == 3 and not 1 <= array.shape[2] <= 4:
            raise PersistenceError(
                f"Invalid pixel buffer '{buffer_id}' for layer '{layer_name}': invalid channel count"  # noqa: E501
            )
        if array.shape[0] > image_spec.height or array.shape[1] > image_spec.width:
            raise PersistenceError(f"Pixel buffer '{buffer_id}' exceeds document dimensions")
        if array.dtype.kind not in "uibf":
            raise PersistenceError(
                f"Pixel buffer '{buffer_id}' has unsupported dtype {array.dtype}"
            )

    @staticmethod
    def _validate_mask_array(array: np.ndarray, buffer_id: str, layer_name: str) -> None:
        if array.ndim not in (2, 3) or array.size == 0:
            raise PersistenceError(f"Invalid mask buffer '{buffer_id}' for layer '{layer_name}'")
        if array.ndim == 3 and array.shape[2] not in (1, 4):
            raise PersistenceError(f"Invalid mask buffer '{buffer_id}' for layer '{layer_name}'")
        if array.dtype.kind not in "uibf":
            raise PersistenceError(f"Mask buffer '{buffer_id}' has unsupported dtype {array.dtype}")

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _to_payload(self, document: ImageDocument) -> dict[str, Any]:
        buffer_metadata = {}
        for buffer_id, meta in document.buffer_metadata:
            if meta:
                buffer_metadata[str(buffer_id)] = dict(meta)
        return {
            "format_version": self.format_version,
            "document": {
                "id": str(document.id),
                "name": document.name,
                "revision": document.revision,
                "image": {
                    "width": document.image.width,
                    "height": document.image.height,
                    "channels": document.image.channels,
                    "bit_depth": document.image.bit_depth,
                    "color_space": document.image.color_space,
                    "has_alpha": document.image.has_alpha,
                },
                "layers": [_layer_to_dict(la) for la in document.layers],
                "operations": [
                    {
                        "operation": op.operation,
                        "parameters": list(op.parameters),
                    }
                    for op in document.operations
                ],
                "masks": [_mask_to_dict(mask) for mask in document.masks],
                "selections": [_selection_to_dict(selection) for selection in document.selections],
                "metadata": dict(document.metadata),
                "workspace_metadata": dict(document.workspace_metadata or document.metadata),
                "buffer_metadata": buffer_metadata,
                "cv_objects": [dict(obj) for obj in document.cv_objects],
            },
        }


# ---------------------------------------------------------------------------
# Auto-detect loader
# ---------------------------------------------------------------------------


def load_project(path: Path, data_store: ImageDataStore) -> ImageDocument:
    """Load a ``.dip`` project, auto-detecting format version.

    * If the file is a valid ZIP with ``format_version == 2``, delegates to
      :class:`ZipProjectStore`.
    * Otherwise falls back to :class:`~dip_studio.infrastructure.project_store.JsonProjectStore`
      for backwards-compatible loading of version-1 JSON files.
    """
    if zipfile.is_zipfile(path):
        return ZipProjectStore(data_store).load(path)
    # Fallback to legacy JSON store (version 1).
    from dip_studio.infrastructure.project_store import JsonProjectStore

    return JsonProjectStore().load(path)
