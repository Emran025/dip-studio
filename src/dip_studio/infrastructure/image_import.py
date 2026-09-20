"""Small image import boundary and the dependency-free PPM adapter."""

from pathlib import Path

from dip_studio.application.ports import ImportedImage, ImageImporter
from dip_studio.core.errors import PersistenceError
from dip_studio.domain.model import ImageSpec


class PpmImageImporter:
    extensions = (".ppm",)

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
            return ImportedImage(
                path.stem or "Imported image",
                ImageSpec(width, height, 3, 8, "sRGB", False),
                data,
            )
        except (OSError, ValueError, IndexError) as error:
            raise PersistenceError(f"Could not import image: {path}") from error


class ImageFormatRegistry:
    def __init__(self, importers: tuple[ImageImporter, ...] = (PpmImageImporter(),)) -> None:
        self._importers = {extension.lower(): importer for importer in importers for extension in importer.extensions}

    def importer_for(self, path: Path) -> ImageImporter:
        importer = self._importers.get(path.suffix.lower())
        if importer is None:
            raise PersistenceError(f"No image importer registered for: {path.suffix or path.name}")
        return importer

    def import_image(self, path: Path) -> ImportedImage:
        return self.importer_for(path).import_image(path)
