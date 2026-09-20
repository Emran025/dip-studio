from dip_studio.application.commands import Command
from dip_studio.application.session import DocumentSession


class UndoRedoHistory:
    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def execute(self, command: Command, session: DocumentSession) -> None:
        command.execute(session)
        self._undo.append(command)
        self._redo.clear()

    def undo(self, session: DocumentSession) -> None:
        if self._undo:
            command = self._undo.pop()
            command.undo(session)
            self._redo.append(command)

    def redo(self, session: DocumentSession) -> None:
        if self._redo:
            command = self._redo.pop()
            command.execute(session)
            self._undo.append(command)
