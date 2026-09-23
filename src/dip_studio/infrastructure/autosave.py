"""Periodic autosave worker — saves a recovery .dip file every N seconds.

The worker uses a ``QTimer`` (Qt-based, fires on the UI thread) to trigger
a background save via ``BackgroundWorker``. Recovery files are written to
``%APPDATA%\\DIP Studio\\recovery\\`` on Windows or ``~/.dip_studio/recovery/``
on Linux/macOS.

Architecture: doc-12 Phase 6 Professionalization — autosave/recovery.

The composition root in ``composition.py`` creates one instance and calls
``start()`` after the main window is ready.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dip_studio.application.editor import EditorController

try:
    from PySide6.QtCore import QObject, QTimer, Signal

    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False


def _recovery_dir() -> Path:
    """Return the platform-appropriate recovery directory, creating it if needed."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "DIP Studio" / "recovery"
    else:
        base = Path.home() / ".dip_studio" / "recovery"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_recovery_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return sanitized or "document"


def _recovery_files_for(
    document_name: str | None = None,
    *,
    recovery_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Return all recovery candidates in a directory, newest first."""
    base = recovery_dir or _recovery_dir()
    if not base.exists():
        return ()
    target_prefix = _safe_recovery_name(document_name) if document_name else None
    paths: list[Path] = []
    for candidate in sorted(
        base.iterdir(),
        key=lambda item: item.stat().st_mtime_ns if item.is_file() else 0,
        reverse=True,
    ):
        if not candidate.is_file():
            continue
        lower = candidate.name.lower()
        if not (lower.endswith(".dip") or (lower.endswith(".tmp") and ".dip" in lower)):
            continue
        if target_prefix is not None and not candidate.name.startswith(f"{target_prefix}_recovery"):
            continue
        paths.append(candidate)
    return tuple(paths)


def discover_recovery_files(
    document_name: str | None = None,
    *,
    recovery_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Return recovery snapshots discovered on disk, ignoring partial writes."""
    base = recovery_dir or _recovery_dir()
    base.mkdir(parents=True, exist_ok=True)
    return tuple(
        path
        for path in _recovery_files_for(document_name, recovery_dir=base)
        if not path.name.endswith(".tmp")
    )


def _validate_recovery_file(path: Path, project_store: Any | None = None) -> bool:
    """Return True when the recovery artifact is readable and structurally valid."""
    if path.name.endswith(".tmp"):
        return False
    try:
        if project_store is not None:
            project_store.load(path)
            return True
        if path.suffix.lower() != ".dip":
            return False
        import json
        import zipfile

        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as zf:
                if "metadata.json" not in zf.namelist():
                    return False
                payload = json.loads(zf.read("metadata.json").decode("utf-8"))
                return isinstance(payload, dict) and "document" in payload

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return isinstance(payload, dict) and "document" in payload
    except Exception:
        return False


def cleanup_recovery_files(
    *,
    document_name: str | None = None,
    recovery_dir: Path | None = None,
    max_generations: int = 8,
    project_store: Any | None = None,
) -> tuple[Path, ...]:
    """Delete stale temp files and keep only the newest bounded recovery generations.

    The retention policy is filename-based for the recovery family, while deeper
    document validation is left to ``find_latest_recovery_file()`` when a restore
    decision is actually required.
    """
    base = recovery_dir or _recovery_dir()
    base.mkdir(parents=True, exist_ok=True)
    if max_generations <= 0:
        raise ValueError("max_generations must be positive")

    stale_paths: list[Path] = []
    valid_paths: list[Path] = []
    document_prefix = _safe_recovery_name(document_name) if document_name else None
    recovery_pattern = re.compile(r".*_recovery(?:_\d+)?\.dip$")
    for candidate in sorted(
        base.iterdir(),
        key=lambda item: item.stat().st_mtime_ns if item.is_file() else 0,
        reverse=True,
    ):
        if not candidate.is_file():
            continue
        if candidate.name.endswith(".tmp"):
            stale_paths.append(candidate)
            continue
        if candidate.suffix.lower() != ".dip":
            continue
        if document_prefix is not None:
            if not candidate.name.startswith(f"{document_prefix}_recovery"):
                continue
        if not recovery_pattern.match(candidate.name):
            stale_paths.append(candidate)
            continue
        valid_paths.append(candidate)

    kept = valid_paths[:max_generations]
    for path in set(stale_paths) | set(valid_paths[max_generations:]):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return tuple(sorted(kept, key=lambda item: item.stat().st_mtime_ns, reverse=True))


def find_latest_recovery_file(
    *,
    document_name: str | None = None,
    recovery_dir: Path | None = None,
    project_store: Any | None = None,
) -> Path | None:
    """Return the newest valid recovery snapshot for the given document."""
    base = recovery_dir or _recovery_dir()
    base.mkdir(parents=True, exist_ok=True)
    candidates = discover_recovery_files(document_name, recovery_dir=base)
    if not candidates:
        return None
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime_ns, reverse=True):
        if _validate_recovery_file(path, project_store=project_store):
            return path
    return None


if _QT_AVAILABLE:

    class AutosaveWorker(QObject):
        """Periodically saves the active document to a recovery .dip file.

        Parameters
        ----------
        controller : EditorController
            The application controller — used to access the current document
            and the project store.
        interval_seconds : int
            How often to trigger an autosave (default: 120 s = 2 minutes).
        """

        saved = Signal(str)
        failed = Signal(str)

        def __init__(
            self,
            controller: EditorController,
            interval_seconds: int = 120,
            parent: QObject | None = None,
            max_generations: int = 8,
        ) -> None:
            super().__init__(parent)
            self._controller = controller
            if interval_seconds <= 0:
                raise ValueError("interval_seconds must be positive")
            self._interval_ms = interval_seconds * 1_000
            self._max_generations = max_generations
            from dip_studio.presentation.background_worker import BackgroundWorker

            self._worker = BackgroundWorker(self)
            self._saving = False
            self._timer = QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._on_timer)

        @property
        def max_generations(self) -> int:
            return self._max_generations

        def start(self) -> None:
            """Begin the autosave cycle."""
            self._timer.start()

        def stop(self) -> None:
            """Stop the autosave cycle."""
            self._timer.stop()
            if self._worker is not None:
                self._worker.cancel_all()

        def discover_recovery_files(self, document_name: str | None = None) -> tuple[Path, ...]:
            return discover_recovery_files(document_name=document_name)

        def restore_latest_recovery(self, document_name: str | None = None) -> Any | None:
            path = find_latest_recovery_file(
                document_name=document_name, project_store=self._controller._project_store
            )
            if path is None:
                return None
            return (
                self._controller._project_store.load(path)
                if self._controller._project_store is not None
                else None
            )

        def cleanup_recovery_files(
            self,
            document_name: str | None = None,
            *,
            recovery_dir: Path | None = None,
        ) -> tuple[Path, ...]:
            return cleanup_recovery_files(
                document_name=document_name,
                recovery_dir=recovery_dir,
                max_generations=self._max_generations,
                project_store=self._controller._project_store,
            )

        def _next_recovery_path(self, document_name: str) -> Path:
            safe_name = _safe_recovery_name(document_name)
            base = _recovery_dir()
            path = base / f"{safe_name}_recovery.dip"
            current = discover_recovery_files(document_name=document_name)
            if len(current) >= self._max_generations:
                for stale in current[self._max_generations - 1 :]:
                    try:
                        stale.unlink(missing_ok=True)
                    except OSError:
                        pass
            return path

        def _on_timer(self) -> None:
            """Called on the UI thread every ``interval_seconds``."""
            if self._saving:
                return
            doc = self._controller.document
            if doc is None:
                return
            recovery_path = self._next_recovery_path(doc.name)
            try:
                self._saving = True
                self._worker.submit(
                    fn=lambda _token, _reporter: self._controller.save_document_snapshot(
                        doc, recovery_path
                    ),
                    on_done=lambda saved: (
                        self._on_saved(recovery_path) if saved else self._on_stale_snapshot()
                    ),
                    on_error=self._on_error,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                self._saving = False
                self._on_error(exc)

        def _on_saved(self, path: Path) -> None:
            self._saving = False
            cleanup_recovery_files(
                document_name=path.stem.replace("_recovery", ""),
                max_generations=self._max_generations,
            )
            self.saved.emit(str(path))

        def _on_stale_snapshot(self) -> None:
            self._saving = False

        def _on_error(self, error: Exception) -> None:
            self._saving = False
            self.failed.emit(str(error))

else:
    # Headless / test stub — does nothing.
    class AutosaveWorker:  # type: ignore[no-redef]
        """No-op autosave stub (PySide6 unavailable)."""

        def __init__(
            self,
            controller: EditorController,
            interval_seconds: int = 120,
            parent: object = None,
            max_generations: int = 8,
        ) -> None:
            self.saved = None
            self.failed = None
            self._saving = False
            self._max_generations = max_generations

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def discover_recovery_files(self, document_name: str | None = None) -> tuple[Path, ...]:
            return discover_recovery_files(document_name=document_name)

        def restore_latest_recovery(self, document_name: str | None = None) -> Any | None:
            return None

        def cleanup_recovery_files(
            self,
            document_name: str | None = None,
            *,
            recovery_dir: Path | None = None,
        ) -> tuple[Path, ...]:
            return cleanup_recovery_files(
                document_name=document_name,
                recovery_dir=recovery_dir,
                max_generations=self._max_generations,
            )
