"""Image export adapters: save flattened composite to PNG/JPEG/BMP/TIFF/PPM."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from dip_studio.core.errors import PersistenceError

_PILLOW_AVAILABLE = False
try:
    import importlib.util

    _PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None
except Exception:
    pass


class ImageExporter:
    """Export a rendered numpy RGBA array to disk in the requested format."""

    SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".ppm")

    def export(
        self,
        composite: np.ndarray,
        path: Path,
        quality: int = 85,
    ) -> None:
        """Write *composite* (H, W, 3 or 4 uint8) to *path*.

        Raises:
            PersistenceError: if writing fails or format is unsupported.
        """
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise PersistenceError(
                f"Unsupported export format: '{ext}'. "
                f"Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        # Ensure RGB or RGBA uint8
        arr = composite.astype(np.uint8)

        if ext == ".ppm":
            self._write_ppm(arr, path)
            return

        if not _PILLOW_AVAILABLE:
            if ext == ".ppm":
                self._write_ppm(arr, path)
                return
            raise PersistenceError(
                f"Pillow is required to export '{ext}'. Install it with: conda install pillow"
            )

        self._write_pillow(arr, path, ext, quality)

    # ──────────────────────────── helpers ────────────────────────────

    @staticmethod
    def _write_ppm(arr: np.ndarray, path: Path) -> None:
        rgb = arr[:, :, :3] if arr.ndim == 3 and arr.shape[2] >= 3 else arr
        h, w = rgb.shape[:2]
        header = f"P6\n{w} {h}\n255\n".encode("ascii")
        try:
            path.write_bytes(header + rgb.tobytes())
        except OSError as exc:
            raise PersistenceError(f"Could not write PPM: {path}") from exc

    @staticmethod
    def _write_pillow(
        arr: np.ndarray,
        path: Path,
        ext: str,
        quality: int,
    ) -> None:
        from PIL import Image as PilImage  # type: ignore[import-untyped]

        has_alpha = arr.ndim == 3 and arr.shape[2] == 4
        jpeg_exts = {".jpg", ".jpeg"}

        if ext in jpeg_exts and has_alpha:
            # JPEG does not support transparency → drop alpha channel
            arr = arr[:, :, :3]
            has_alpha = False

        mode = "RGBA" if has_alpha else "RGB"
        if arr.ndim == 2:
            mode = "L"

        img = PilImage.fromarray(arr, mode)

        save_kwargs: dict[str, object] = {}
        if ext in jpeg_exts:
            save_kwargs["quality"] = quality
            save_kwargs["subsampling"] = 0  # 4:4:4 for best quality
        elif ext == ".png":
            save_kwargs["optimize"] = True
        elif ext in (".tiff", ".tif"):
            save_kwargs["compression"] = "lzw"

        try:
            img.save(path, **save_kwargs)
        except (OSError, ValueError) as exc:
            raise PersistenceError(f"Could not export image to {path}") from exc


class CompositeExporter:
    """Export a Document by compositing all visible layers first."""

    def __init__(self, exporter: ImageExporter | None = None) -> None:
        self._exporter = exporter or ImageExporter()

    def export_document(
        self,
        composite_bytes: bytes,
        path: Path,
        quality: int = 85,
    ) -> None:
        """Decode JPEG/PPM composite bytes and write to *path*.

        *composite_bytes* is the raw bytes produced by the compositor (JPEG or PPM).
        """
        if not _PILLOW_AVAILABLE:
            # Only PPM passthrough works without Pillow
            ext = path.suffix.lower()
            if ext == ".ppm":
                path.write_bytes(composite_bytes)
                return
            raise PersistenceError(
                "Pillow is required to convert JPEG composite for export. "
                "Install it with: conda install pillow"
            )

        from PIL import Image as PilImage  # type: ignore[import-untyped]

        try:
            img = PilImage.open(io.BytesIO(composite_bytes))
            arr = np.array(img.convert("RGB"), dtype=np.uint8)
        except Exception as exc:
            raise PersistenceError("Could not decode composite for export") from exc

        self._exporter.export(arr, path, quality)
