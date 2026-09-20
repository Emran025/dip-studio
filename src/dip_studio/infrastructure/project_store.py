"""Versioned, atomic JSON project persistence adapter."""

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from dip_studio.core.errors import PersistenceError
from dip_studio.domain.model import DocumentId, ImageDocument, ImageSpec, Layer, LayerId


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
            },
        }

    def _from_payload(self, raw: dict[str, Any]) -> ImageDocument:
        image = self._as_dict(raw["image"])
        layers = raw["layers"]
        if not isinstance(layers, list):
            raise PersistenceError("Invalid layer payload")
        parsed_layers = tuple(self._layer_from_payload(self._as_dict(item)) for item in layers)
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
        )

    def _layer_from_payload(self, raw: dict[str, Any]) -> Layer:
        return Layer(
            LayerId(UUID(self._as_str(raw["id"]))),
            self._as_str(raw["name"]),
            self._as_bool(raw["visible"]),
            self._as_float(raw["opacity"]),
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
