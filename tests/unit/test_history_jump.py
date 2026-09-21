"""Tests for history jumping and history navigation in UndoRedoHistory and EditorController."""
from __future__ import annotations

from uuid import uuid4

from dip_studio.application.commands import ReplaceDocument
from dip_studio.application.editor import EditorController
from dip_studio.application.history import UndoRedoHistory
from dip_studio.application.session import DocumentSession
from dip_studio.domain.model import DocumentId, ImageDocument, ImageSpec, Layer, LayerId
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.rendering.ports import BlankDocumentRenderer


def _make_doc(name: str) -> ImageDocument:
    return ImageDocument(
        id=DocumentId(uuid4()),
        name=name,
        image=ImageSpec(10, 10, 3, 8, "RGB", False),
        layers=(Layer(id=LayerId(uuid4()), name="L1"),),
    )


class TestUndoRedoHistoryJump:
    def test_jump_back_and_forward(self) -> None:
        doc0 = _make_doc("State0")
        session = DocumentSession(doc0)
        history = UndoRedoHistory()

        doc1 = doc0.changed(name="State1")
        cmd1 = ReplaceDocument(doc1)
        history.execute(cmd1, session)

        doc2 = doc0.changed(name="State2")
        cmd2 = ReplaceDocument(doc2)
        history.execute(cmd2, session)

        doc3 = doc0.changed(name="State3")
        cmd3 = ReplaceDocument(doc3)
        history.execute(cmd3, session)

        assert session.document.name == "State3"
        assert history.current_index() == 3
        assert len(history.labels()) == 4

        # Jump back to State1 (index 1)
        history.jump_to(1, session)
        assert session.document.name == "State1"
        assert history.current_index() == 1

        # Jump forward to State3 (index 3)
        history.jump_to(3, session)
        assert session.document.name == "State3"
        assert history.current_index() == 3

        # Jump back to Original (index 0)
        history.jump_to(0, session)
        assert session.document.name == "State0"
        assert history.current_index() == 0

    def test_jump_out_of_bounds_is_noop(self) -> None:
        doc = _make_doc("Init")
        session = DocumentSession(doc)
        history = UndoRedoHistory()

        history.jump_to(-1, session)
        assert session.document.name == "Init"

        history.jump_to(99, session)
        assert session.document.name == "Init"


class TestEditorControllerHistoryJump:
    def test_controller_history_jump(self) -> None:
        store = ImageDataStore()
        controller = EditorController(
            renderer=BlankDocumentRenderer(),
            data_store=store,
        )
        controller.create_document("Doc", 10, 10)
        assert controller.history_current_index() == 0

        controller.add_layer()
        assert controller.history_current_index() == 1
        assert len(controller.document.layers) == 2

        controller.add_layer()
        assert controller.history_current_index() == 2
        assert len(controller.document.layers) == 3

        # Jump back to initial state
        controller.history_jump_to(0)
        assert controller.history_current_index() == 0
        assert len(controller.document.layers) == 1

        # Jump forward to state 2
        controller.history_jump_to(2)
        assert controller.history_current_index() == 2
        assert len(controller.document.layers) == 3
