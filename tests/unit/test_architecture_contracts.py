from pathlib import Path

import pytest

from dip_studio.application.commands import ReplaceDocument
from dip_studio.application.history import UndoRedoHistory
from dip_studio.application.session import DocumentSession
from dip_studio.core.cancellation import MutableCancellationToken
from dip_studio.core.errors import CancellationError, PersistenceError, ValidationError
from dip_studio.core.result import Result
from dip_studio.domain.factories import new_document
from dip_studio.domain.model import ImageSpec, Layer
from dip_studio.infrastructure.project_store import JsonProjectStore
from dip_studio.presentation.theme import DARK, LIGHT


def test_document_invariants_and_revision() -> None:
    document = new_document("sample", 32, 24)
    assert not document.is_dirty
    changed = document.changed(name="edited")
    assert changed.is_dirty
    assert changed.revision == 1
    assert changed.marked_saved().saved_revision == 1
    with pytest.raises(ValidationError):
        ImageSpec(0, 10)
    with pytest.raises(ValidationError):
        Layer(document.layers[0].id, "", opacity=1.0)


def test_session_and_command_history_round_trip() -> None:
    first = new_document("first", 10, 10)
    second = first.changed(name="second")
    session = DocumentSession(first)
    history = UndoRedoHistory()
    history.execute(ReplaceDocument(second), session)
    assert session.document.name == "second"
    history.undo(session)
    assert session.document.name == "first"
    history.redo(session)
    assert session.document.name == "second"


def test_session_rejects_different_identity() -> None:
    session = DocumentSession(new_document("one", 10, 10))
    with pytest.raises(ValueError):
        session.replace(new_document("two", 10, 10))


def test_cancellation_and_result_contracts() -> None:
    token = MutableCancellationToken()
    token.cancel()
    with pytest.raises(CancellationError):
        token.throw_if_cancelled()
    success = Result.ok("done")
    failure = Result.failure(ValueError("bad"))
    assert success.is_ok and success.value == "done"
    assert not failure.is_ok and failure.error is not None


def test_project_store_round_trip_and_invalid_version(tmp_path: Path) -> None:
    document = new_document("round-trip", 64, 48)
    path = tmp_path / "sample.dip"
    store = JsonProjectStore()
    store.save(document, path)
    loaded = store.load(path)
    assert loaded.id == document.id
    assert loaded.image == document.image
    assert loaded.layers == document.layers
    path.write_text('{"format_version": 99}', encoding="utf-8")
    with pytest.raises(PersistenceError):
        store.load(path)


def test_project_store_rejects_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.dip"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(PersistenceError):
        JsonProjectStore().load(path)


def test_theme_tokens_are_distinct_and_semantic() -> None:
    assert LIGHT.surface != DARK.surface
    assert LIGHT.accent != DARK.accent
    assert LIGHT.foreground
