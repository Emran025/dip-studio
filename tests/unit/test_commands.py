import pytest

from dip_studio.application.commands import CommandHandler, ReplaceDocument
from dip_studio.application.session import DocumentSession
from dip_studio.domain.factories import new_document


def test_command_handler_dispatches_registered_command() -> None:
    first = new_document("first", 10, 10)
    second = first.changed(name="second")
    session = DocumentSession(first)
    handler = CommandHandler(session)
    handler.register("rename", lambda: ReplaceDocument(second))

    command = handler.execute("rename")

    assert isinstance(command, ReplaceDocument)
    assert session.document.name == "second"


def test_command_handler_rejects_unknown_command() -> None:
    handler = CommandHandler(DocumentSession(new_document("sample", 10, 10)))

    with pytest.raises(KeyError, match="Unknown command"):
        handler.execute("missing")
