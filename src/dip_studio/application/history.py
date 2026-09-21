"""Undo/redo history for a single document session with jumping support."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dip_studio.application.commands import Command
    from dip_studio.application.session import DocumentSession


class UndoRedoHistory:
    """Command stack with label tracking and arbitrary state jumping."""

    def __init__(self) -> None:
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._labels: list[str] = ["Original"]
        self._current_index: int = 0

    def execute(self, command: Command, session: DocumentSession) -> None:
        command.execute(session)
        self._undo_stack.append(command)
        self._redo_stack.clear()
        label = getattr(command, "label", None) or type(command).__name__
        # Truncate any redone labels beyond the current point
        self._labels = self._labels[: self._current_index + 1]
        self._labels.append(str(label))
        self._current_index = len(self._labels) - 1

    def undo(self, session: DocumentSession) -> None:
        if not self._undo_stack:
            return
        command = self._undo_stack.pop()
        command.undo(session)
        self._redo_stack.append(command)
        self._current_index = max(0, self._current_index - 1)

    def redo(self, session: DocumentSession) -> None:
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        command.execute(session)
        self._undo_stack.append(command)
        self._current_index = min(len(self._labels) - 1, self._current_index + 1)

    def jump_to(self, target_index: int, session: DocumentSession) -> None:
        """Jump to the state at target_index by performing the necessary undo/redo steps."""
        if target_index < 0 or target_index >= len(self._labels):
            return
        current = self._current_index
        if target_index < current:
            for _ in range(current - target_index):
                self.undo(session)
        elif target_index > current:
            for _ in range(target_index - current):
                self.redo(session)

    def labels(self) -> list[str]:
        """Return all history state labels, oldest first."""
        return list(self._labels)

    def current_index(self) -> int:
        """Return the 0-based index of the currently active state."""
        return self._current_index
