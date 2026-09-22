"""Versioned, atomic JSON project persistence adapter."""

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from dip_studio.core.errors import PersistenceError
from dip_studio.domain.model import (
    AppliedOperation,
    DocumentId,
    ImageDocument,
    ImageSpec,
    Layer,
    LayerId,
)


class JsonProjectStore:
    format_version = 1

    def save(self, document: ImageDocument, path: Path) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self._to_payload(document), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError as error:
            raise PersistenceError(f"Could not save project: {path}") from error

    def load(self, path: Path) -> ImageDocument:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if self._as_int(data["format_version"]) != self.format_version:
                raise PersistenceError("Unsupported project format version")
            return self._from_payload(self._as_dict(data["document"]))
        except PersistenceError:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PersistenceError(f"Could not load project: {path}") from error

    def _to_payload(self, document: ImageDocument) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "document": {
                "id": str(document.id),
                "name": document.name,
                "revision": document.revision,
                "saved_revision": document.revision,
                "image": {
                    "width": document.image.width,
                    "height": document.image.height,
                    "channels": document.image.channels,
                    "bit_depth": document.image.bit_depth,
                    "color_space": document.image.color_space,
                    "has_alpha": document.image.has_alpha,
                },
                "layers": [
                    {
                        "id": str(layer.id),
                        "name": layer.name,
                        "visible": layer.visible,
                        "opacity": layer.opacity,
                    }
                    for layer in document.layers
                ],
                "operations": [
                    {"operation": operation.operation, "parameters": list(operation.parameters)}
                    for operation in document.operations
                ],
                "masks": [
                    {
                        "id": str(mask.id),
                        "name": mask.name,
                        "width": mask.width,
                        "height": mask.height,
                        "mode": mask.mode,
                        "buffer_id": mask.buffer_id,
                        "enabled": mask.enabled,
                    }
                    for mask in document.masks
                ],
                "selections": [
                    {
                        "x": selection.x,
                        "y": selection.y,
                        "width": selection.width,
                        "height": selection.height,
                        "feather": selection.feather,
                        "kind": selection.kind,
                        "mask_buffer_id": selection.mask_buffer_id,
                    }
                    for selection in document.selections
                ],
                "metadata": dict(document.metadata),
                "workspace_metadata": dict(document.workspace_metadata),
                "buffer_metadata": {key: value for key, value in document.buffer_metadata},
                "cv_objects": [dict(obj) for obj in document.cv_objects],
            },
        }

    def _from_payload(self, raw: dict[str, Any]) -> ImageDocument:
        image = self._as_dict(raw["image"])
        layers = raw["layers"]
        if not isinstance(layers, list):
            raise PersistenceError("Invalid layer payload")
        parsed_layers = tuple(self._layer_from_payload(self._as_dict(item)) for item in layers)
        operations = raw.get("operations", [])
        if not isinstance(operations, list):
            raise PersistenceError("Invalid operation payload")
        parsed_operations = tuple(
            AppliedOperation(
                self._as_str(item["operation"]),
                tuple((self._as_str(pair[0]), self._as_str(pair[1])) for pair in item["parameters"]),
            )
            for item in (self._as_dict(value) for value in operations)
        )
        masks = tuple(
            self._mask_from_payload(self._as_dict(item))
            for item in (self._as_dict(value) for value in raw.get("masks", []))
        )
        selections = tuple(
            self._selection_from_payload(self._as_dict(item))
            for item in (self._as_dict(value) for value in raw.get("selections", []))
        )
        metadata = tuple((self._as_str(k), self._as_str(v)) for k, v in self._as_dict(raw.get("metadata", {})).items())
        workspace_metadata = tuple((self._as_str(k), self._as_str(v)) for k, v in self._as_dict(raw.get("workspace_metadata", {})).items())
        buffer_metadata = tuple((self._as_str(key), self._as_dict(value)) for key, value in self._as_dict(raw.get("buffer_metadata", {})).items())
        cv_objects = tuple(self._as_dict(item) for item in raw.get("cv_objects", []))
        return ImageDocument(
            DocumentId(UUID(self._as_str(raw["id"]))),
            self._as_str(raw["name"]),
            ImageSpec(
                width=self._as_int(image["width"]),
                height=self._as_int(image["height"]),
                channels=self._as_int(image["channels"]),
                bit_depth=self._as_int(image["bit_depth"]),
                color_space=self._as_str(image["color_space"]),
                has_alpha=self._as_bool(image["has_alpha"]),
            ),
            parsed_layers,
            self._as_int(raw["revision"]),
            self._as_int(raw["saved_revision"]),
            parsed_operations,
            masks,
            selections,
            metadata,
            workspace_metadata,
            buffer_metadata,
            cv_objects,
        )

    def _layer_from_payload(self, raw: dict[str, Any]) -> Layer:
        return Layer(
            LayerId(UUID(self._as_str(raw["id"]))),
            self._as_str(raw["name"]),
            self._as_bool(raw["visible"]),
            self._as_float(raw["opacity"]),
        )

    def _mask_from_payload(self, raw: dict[str, Any]):
        from dip_studio.domain.model import Mask

        return Mask(
            id=self._as_str(raw["id"]),
            name=self._as_str(raw["name"]),
            width=self._as_int(raw["width"]),
            height=self._as_int(raw["height"]),
            mode=self._as_str(raw.get("mode", "reveal")),
            buffer_id=raw.get("buffer_id"),
            enabled=self._as_bool(raw.get("enabled", True)),
        )

    def _selection_from_payload(self, raw: dict[str, Any]):
        from dip_studio.domain.model import SelectionRect

        return SelectionRect(
            x=self._as_int(raw["x"]),
            y=self._as_int(raw["y"]),
            width=self._as_int(raw["width"]),
            height=self._as_int(raw["height"]),
            feather=self._as_float(raw.get("feather", 0.0)),
            kind=self._as_str(raw.get("kind", "rectangle")),
            mask_buffer_id=raw.get("mask_buffer_id"),
        )

    @staticmethod
    def _as_dict(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise PersistenceError("Expected an object in project payload")
        return value

    @staticmethod
    def _as_str(value: object) -> str:
        if not isinstance(value, str):
            raise PersistenceError("Expected a string in project payload")
        return value

    @staticmethod
    def _as_int(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise PersistenceError("Expected an integer in project payload")
        return value

    @staticmethod
    def _as_float(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PersistenceError("Expected a number in project payload")
        return float(value)

    @staticmethod
    def _as_bool(value: object) -> bool:
        if not isinstance(value, bool):
            raise PersistenceError("Expected a boolean in project payload")
        return value
