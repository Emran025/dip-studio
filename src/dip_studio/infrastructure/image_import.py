"""Image import adapters: PPM (zero-dependency) and Pillow (full format support)."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from dip_studio.application.ports import ImageImporter, ImportedImage
from dip_studio.core.errors import PersistenceError
from dip_studio.domain.model import ImageSpec
from dip_studio.infrastructure.data_store import ImageDataStore

SUPPORTED_IMPORT_FORMATS = (
    ("ppm", "PPM"),
    ("png", "PNG"),
    ("jpg", "JPEG"),
    ("jpeg", "JPEG"),
    ("bmp", "BMP"),
    ("tiff", "TIFF"),
    ("tif", "TIFF"),
    ("webp", "WebP"),
    ("gif", "GIF"),
)

_PILLOW_AVAILABLE = False
try:
    import importlib.util

    _PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None
except Exception:
    pass


class PpmImageImporter:
    """Dependency-free PPM reader (P3/P6)."""

    extensions = (".ppm",)

    def __init__(self, data_store: ImageDataStore | None = None) -> None:
        self._store = data_store

    def import_image(self, path: Path) -> ImportedImage:
        try:
            data = path.read_bytes()
            tokens = data.split()
            if len(tokens) < 4 or tokens[0] not in (b"P3", b"P6"):
                raise PersistenceError("Unsupported or invalid PPM image")
            width, height, maximum = (int(value) for value in tokens[1:4])
            if maximum <= 0 or maximum > 65535:
                raise PersistenceError("Invalid PPM color range")
            if width <= 0 or height <= 0:
                raise PersistenceError("Invalid PPM dimensions")
            spec = ImageSpec(width, height, 3, 8, "sRGB", False)
            # Store buffer if data_store provided
            buffer_id: str | None = None
            if self._store is not None and _PILLOW_AVAILABLE:
                try:
                    from PIL import Image as PilImage  # type: ignore[import-untyped]

                    img = PilImage.open(path).convert("RGB")
                    arr = np.array(img, dtype=np.uint8)
                    buffer_id = self._store.allocate(arr)
                except Exception:
                    pass
            return ImportedImage(
                path.stem or "Imported image",
                spec,
                data,
                buffer_id,
            )
        except (OSError, ValueError, IndexError) as error:
            raise PersistenceError(f"Could not import image: {path}") from error


class PillowImageImporter:
    """Full-format importer using Pillow: PNG, JPEG, BMP, TIFF, WebP, GIF."""

    extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif")

    def __init__(self, data_store: ImageDataStore) -> None:
        self._store = data_store

    def import_image(self, path: Path) -> ImportedImage:
        if not _PILLOW_AVAILABLE:
            raise PersistenceError("Pillow is not installed. Install it with: pip install Pillow")
        try:
            from PIL import Image as PilImage  # type: ignore[import-untyped]
            from PIL import ImageOps

            img = PilImage.open(path)
            img = ImageOps.exif_transpose(img)
            # Convert to RGBA for uniform 4-channel handling
            mode = img.mode
            has_alpha = mode in ("RGBA", "LA", "PA")
            target_mode = "RGBA" if has_alpha else "RGB"
            img = img.convert(target_mode)
            channels = 4 if has_alpha else 3
            arr = np.array(img, dtype=np.uint8)
            buffer_id = self._store.allocate(arr)

            # Keep the preview at the source resolution. The editor uses these
            # bytes for the initial canvas display, so downscaling here would
            # permanently limit the visible detail until another render.
            preview_buffer = io.BytesIO()
            img.save(preview_buffer, format="PNG")
            preview = preview_buffer.getvalue()

            spec = ImageSpec(
                img.width,
                img.height,
                channels,
                8,
                "sRGB",
                has_alpha,
            )
            return ImportedImage(
                path.stem or "Imported image",
                spec,
                preview,
                buffer_id,
            )
        except (OSError, ValueError, TypeError) as error:
            raise PersistenceError(f"Could not import image: {path}") from error


class ImageFormatRegistry:
    """Routes import calls to the correct importer by file extension."""

    def __init__(
        self,
        importers: tuple[ImageImporter, ...] | None = None,
        data_store: ImageDataStore | None = None,
    ) -> None:
        self._data_store = data_store or ImageDataStore()
        if importers is None:
            importers = _default_importers(self._data_store)
        self._importers = {
            ext.lower(): importer for importer in importers for ext in importer.extensions
        }
        self.set_data_store(self._data_store)

    def set_data_store(self, data_store: ImageDataStore) -> None:
        self._data_store = data_store
        for importer in self._importers.values():
            if hasattr(importer, "_store"):
                importer._store = data_store

    @property
    def supported_formats(self) -> tuple[tuple[str, str], ...]:
        return SUPPORTED_IMPORT_FORMATS

    def importer_for(self, path: Path) -> ImageImporter:
        importer = self._importers.get(path.suffix.lower())
        if importer is None:
            raise PersistenceError(f"No image importer registered for: {path.suffix or path.name}")
        return importer

    def import_image(self, path: Path) -> ImportedImage:
        return self.importer_for(path).import_image(path)


def _default_importers(store: ImageDataStore) -> tuple[ImageImporter, ...]:
    importers: list[ImageImporter] = [PpmImageImporter(store)]
    if _PILLOW_AVAILABLE:
        importers.append(PillowImageImporter(store))
    return tuple(importers)
