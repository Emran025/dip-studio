from __future__ import annotations

import numpy as np

from dip_studio.application.processing_graph import OperationNode, ProcessingGraph
from dip_studio.domain.model import (
    AdjustmentLayer,
    FilterLayer,
    ImageDocument,
    ImageSpec,
    Layer,
    LayerId,
)
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.engine import ProcessingEngine
from dip_studio.rendering.compositor import NumpyDocumentRenderer


class _AppendProcessor:
    operation = "append"

    def validate(self, request: ProcessingRequest) -> None:
        return None

    def process(self, image: str, request: ProcessingRequest) -> str:
        suffix = dict(request.parameters)["suffix"]
        return image + suffix


def test_processing_graph_evaluates_enabled_nodes_in_order() -> None:
    graph = (
        ProcessingGraph()
        .add(OperationNode("first", ProcessingRequest("append", (("suffix", "-a"),))))
        .add(OperationNode("disabled", ProcessingRequest("append", (("suffix", "-x"),)), False))
        .add(OperationNode("second", ProcessingRequest("append", (("suffix", "-b"),))))
    )
    progress: list[tuple[int, int, str]] = []

    result = graph.evaluate(
        "source",
        ProcessingEngine({"append": _AppendProcessor()}),
        progress=type(
            "Reporter",
            (),
            {
                "report": lambda _, completed, total, message="": progress.append(
                    (completed, total, message)
                )
            },
        )(),
    )

    assert result == "source-a-b"
    assert progress == [(0, 2, "append"), (1, 2, "append"), (2, 2, "complete")]


def test_processing_graph_rejects_duplicate_nodes_and_unknown_toggle() -> None:
    node = OperationNode("one", ProcessingRequest("append"))
    graph = ProcessingGraph().add(node)

    try:
        graph.add(node)
        raise AssertionError("duplicate node was accepted")
    except ValueError:
        pass

    try:
        graph.set_enabled("missing", False)
        raise AssertionError("unknown node was accepted")
    except KeyError:
        pass


def test_processing_graph_accepts_destructive_mode_flag() -> None:
    graph = ProcessingGraph().add(
        OperationNode("brightness", ProcessingRequest("append", (("suffix", "-x"),)))
    )

    result = graph.evaluate(
        "base",
        ProcessingEngine({"append": _AppendProcessor()}),
        destructive=True,
    )

    assert result == "base-x"


def test_nested_group_pass_through_is_evaluated_in_order() -> None:
    from dip_studio.application.layer_evaluation import LayerEvaluationService
    from dip_studio.domain.model import GroupLayer

    base = Layer(
        id=LayerId("00000000-0000-0000-0000-000000000021"),
        name="base",
        buffer_id="base",
    )
    inner = Layer(
        id=LayerId("00000000-0000-0000-0000-000000000022"),
        name="inner",
        buffer_id="inner",
    )
    nested = GroupLayer(
        id=LayerId("00000000-0000-0000-0000-000000000023"),
        name="nested",
        children=(inner.id,),
        pass_through=True,
    )
    top = Layer(
        id=LayerId("00000000-0000-0000-0000-000000000024"),
        name="top",
        buffer_id="top",
    )

    def read(buffer_id: str) -> np.ndarray:
        payload = {
            "base": np.full((2, 2, 4), 10, dtype=np.uint8),
            "inner": np.full((2, 2, 4), 20, dtype=np.uint8),
            "top": np.full((2, 2, 4), 30, dtype=np.uint8),
        }
        return payload[buffer_id]

    result = LayerEvaluationService(read).evaluate((base, nested, top))

    assert result is not None
    assert result[0, 0, 0] > 20
    assert result[0, 0, 0] < 30
    assert result[0, 0, 1] > 20
    assert result[0, 0, 1] < 30
    assert result[0, 0, 2] > 20
    assert result[0, 0, 2] < 30


def test_adjustment_layer_is_applied_to_lower_stack() -> None:
    class _DummyController:
        document = ImageDocument(
            id="doc",
            name="doc",
            image=ImageSpec(width=2, height=2),
            layers=(
                Layer(
                    id=LayerId("00000000-0000-0000-0000-000000000001"),
                    name="base",
                    buffer_id="base",
                ),
                AdjustmentLayer(
                    id=LayerId("00000000-0000-0000-0000-000000000002"),
                    name="brightness",
                    buffer_id=None,
                    adjustment_type="brightness_contrast",
                    adjustment_params=(("alpha", "1.0"), ("beta", "50.0")),
                ),
                Layer(
                    id=LayerId("00000000-0000-0000-0000-000000000003"), name="top", buffer_id="top"
                ),
            ),
        )
        data_store = type(
            "Store",
            (),
            {
                "get": lambda self, key: {
                    "base": np.stack(
                        [
                            np.full((2, 2), 20, dtype=np.uint8),
                            np.full((2, 2), 20, dtype=np.uint8),
                            np.full((2, 2), 20, dtype=np.uint8),
                            np.full((2, 2), 255, dtype=np.uint8),
                        ],
                        axis=-1,
                    ),
                    "top": np.stack(
                        [
                            np.full((2, 2), 240, dtype=np.uint8),
                            np.full((2, 2), 240, dtype=np.uint8),
                            np.full((2, 2), 240, dtype=np.uint8),
                            np.full((2, 2), 0, dtype=np.uint8),
                        ],
                        axis=-1,
                    ),
                }[key],
            },
        )()

    controller = _DummyController()
    result = NumpyDocumentRenderer(controller)._evaluate(controller.document, controller.data_store)

    assert result is not None
    assert result.shape == (2, 2, 4)
    assert result[0, 0, 0] == 70
    assert result[0, 0, 1] == 70
    assert result[0, 0, 2] == 70


def test_filter_layer_uses_filter_operation_in_stack() -> None:
    class _DummyController:
        document = ImageDocument(
            id="doc",
            name="doc",
            image=ImageSpec(width=2, height=2),
            layers=(
                Layer(
                    id=LayerId("00000000-0000-0000-0000-000000000011"),
                    name="base",
                    buffer_id="base",
                ),
                FilterLayer(
                    id=LayerId("00000000-0000-0000-0000-000000000012"),
                    name="filter",
                    filter_type="grayscale",
                    filter_params=(),
                ),
            ),
        )
        data_store = type(
            "Store",
            (),
            {
                "get": lambda self, key: (
                    np.stack(
                        [
                            np.full((2, 2), 100, dtype=np.uint8),
                            np.full((2, 2), 100, dtype=np.uint8),
                            np.full((2, 2), 100, dtype=np.uint8),
                            np.full((2, 2), 255, dtype=np.uint8),
                        ],
                        axis=-1,
                    )
                    if key == "base"
                    else None
                )
            },
        )()

    controller = _DummyController()
    result = NumpyDocumentRenderer(controller)._evaluate(controller.document, controller.data_store)

    assert result is not None
    assert result[0, 0, 0] == 100
    assert result[0, 0, 1] == 100
    assert result[0, 0, 2] == 100
