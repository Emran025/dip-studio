"""Background processing worker that bridges application-layer callbacks to Qt's
thread pool without importing Qt into the application layer directly.

Architecture note
-----------------
This module lives in ``presentation/`` (not ``application/``) because it
requires ``QObject`` / ``QRunnable`` from PySide6.  The application layer
(``EditorController``) only receives plain Python callables; all Qt signal
machinery stays here.

Usage::

    worker = BackgroundWorker(parent=main_window)
    worker.submit(
        fn=lambda token, reporter: processing_engine.run(buf_id, request),
        on_done=lambda result_buf_id: controller.apply_result(result_buf_id, layer_id),
        on_error=lambda exc: show_error(str(exc)),
    )
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from dip_studio.core.cancellation import MutableCancellationToken, ProgressReporter


# ---------------------------------------------------------------------------
# Internal QRunnable task
# ---------------------------------------------------------------------------

class _TaskSignals(QObject):
    """Signals emitted by a background task (must live on a QObject)."""

    done = Signal(object)      # emits result
    error = Signal(Exception)  # emits exception
    progress = Signal(int)     # emits 0-100 progress percentage
    finished = Signal(object)  # emits the token for lifecycle cleanup


class _BackgroundTask(QRunnable):
    """A single callable executed on a QThreadPool worker thread."""

    def __init__(
        self,
        fn: Callable[[MutableCancellationToken, ProgressReporter], Any],
        token: MutableCancellationToken,
        signals: _TaskSignals,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._token = token
        self._signals = signals
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:  # type: ignore[override]
        class _Reporter:
            def __init__(self, sig: _TaskSignals) -> None:
                self._sig = sig

            def report(self, completed: int, total: int, message: str = "") -> None:
                percent = int(completed / max(total, 1) * 100)
                self._sig.progress.emit(max(0, min(100, percent)))

        try:
            reporter: ProgressReporter = _Reporter(self._signals)  # type: ignore[assignment]
            self._token.throw_if_cancelled()
            result = self._fn(self._token, reporter)
            self._token.throw_if_cancelled()
            self._signals.done.emit(result)
        except Exception as exc:
            self._signals.error.emit(exc)
        finally:
            self._signals.finished.emit(self._token)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class BackgroundWorker(QObject):
    """Submit callables to a shared QThreadPool; results arrive on the UI thread.

    Parameters
    ----------
    parent : QObject | None
        Parent Qt object (usually ``MainWindow``).
    max_thread_count : int
        Maximum parallel workers (default: QThreadPool global default).
    """

    def __init__(self, parent: QObject | None = None, max_thread_count: int = 0) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        if max_thread_count > 0:
            self._pool.setMaxThreadCount(max_thread_count)
        self._active_tokens: list[MutableCancellationToken] = []

    def submit(
        self,
        fn: Callable[[MutableCancellationToken, ProgressReporter], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> MutableCancellationToken:
        """Submit *fn* for background execution.

        Parameters
        ----------
        fn          : Callable receiving ``(token, reporter)``; must be thread-safe.
        on_done     : Called on the UI thread with the function's return value.
        on_error    : Called on the UI thread with any raised exception.
        on_progress : Called on the UI thread with progress percentage 0-100.

        Returns
        -------
        MutableCancellationToken
            Call ``.cancel()`` to request early termination of *fn*.
        """
        token = MutableCancellationToken()
        self._active_tokens.append(token)
        signals = _TaskSignals(self)
        signals.finished.connect(self._remove_token)

        if on_done is not None:
            signals.done.connect(on_done)
        if on_error is not None:
            signals.error.connect(on_error)
        if on_progress is not None:
            signals.progress.connect(on_progress)

        task = _BackgroundTask(fn, token, signals)
        self._pool.start(task)
        return token

    @Slot(object)
    def _remove_token(self, token: object) -> None:
        if isinstance(token, MutableCancellationToken):
            try:
                self._active_tokens.remove(token)
            except ValueError:
                pass

    def cancel_all(self) -> None:
        """Request cancellation of all currently running tasks."""
        for token in self._active_tokens:
            token.cancel()

    def wait_for_done(self, msec: int = 5000) -> None:
        """Block (on the calling thread) until all tasks finish or *msec* expires."""
        self._pool.waitForDone(msec)
