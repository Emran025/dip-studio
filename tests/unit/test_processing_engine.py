from dataclasses import dataclass

import pytest

from dip_studio.core.cancellation import MutableCancellationToken
from dip_studio.core.errors import CancellationError
from dip_studio.processing.contracts import ProcessingContext, ProcessingRequest
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.processing_cache import ProcessingCache
import numpy as np
from dip_studio.processing.engine import ProcessingEngine


@dataclass
class UppercaseProcessor:
    operation: str = "uppercase"

    def validate(self, request: ProcessingRequest) -> None:
        if request.operation != self.operation:
            raise ValueError("operation mismatch")

    def process(self, image: str, request: ProcessingRequest) -> str:
        return image.upper()


def test_processing_engine_delegates_without_owning_algorithm() -> None:
    engine = ProcessingEngine({"uppercase": UppercaseProcessor()})
    assert engine.run("dip", ProcessingRequest("uppercase")) == "DIP"


def test_processing_engine_rejects_unknown_operation() -> None:
    try:
        ProcessingEngine({}).run("dip", ProcessingRequest("missing"))
    except KeyError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("unknown operations must fail")


@pytest.mark.parametrize(
    "processing_request, message",
    [
        (ProcessingRequest(""), "operation"),
        (ProcessingRequest("uppercase", (("", "1"),)), "parameter names"),
        (ProcessingRequest("uppercase", (("value", "1"), ("value", "2"))), "duplicate"),
    ],
)
def test_processing_engine_rejects_malformed_request_shape(
    processing_request: ProcessingRequest, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProcessingEngine({"uppercase": UppercaseProcessor()}).run(
            "dip", processing_request
        )


@dataclass
class ContextProcessor:
    operation: str = "context"
    seen_context: ProcessingContext | None = None

    def validate(self, request: ProcessingRequest) -> None:
        return None

    def process(self, image: str, request: ProcessingRequest) -> str:
        raise AssertionError("context-aware processors must use their context method")

    def process_with_context(
        self,
        image: str,
        request: ProcessingRequest,
        context: ProcessingContext,
    ) -> str:
        self.seen_context = context
        context.progress.report(1, 1, "done")
        context.cancellation.throw_if_cancelled()
        return image + "!"


def test_processing_engine_passes_context_to_context_aware_processor() -> None:
    processor = ContextProcessor()
    token = MutableCancellationToken()
    progress: list[tuple[int, int, str]] = []

    class Reporter:
        def report(self, completed: int, total: int, message: str = "") -> None:
            progress.append((completed, total, message))

    result = ProcessingEngine({"context": processor}).run(
        "dip",
        ProcessingRequest("context"),
        cancellation=token,
        progress=Reporter(),
        metadata={"source": "test"},
    )

    assert result == "dip!"
    assert processor.seen_context is not None
    assert processor.seen_context.image == "dip"
    assert processor.seen_context.preview_mode is False
    assert processor.seen_context.mask is None
    assert processor.seen_context.metadata == {"source": "test"}
    assert progress == [(1, 1, "done")]


def test_processing_engine_checks_cancellation_before_processing() -> None:
    token = MutableCancellationToken()
    token.cancel()

    with pytest.raises(CancellationError):
        ProcessingEngine({"uppercase": UppercaseProcessor()}).run(
            "dip",
            ProcessingRequest("uppercase"),
            cancellation=token,
        )


def test_processing_engine_checks_cancellation_after_context_processor_returns() -> None:
    class CancelAfterReturnProcessor:
        operation = "late-cancel"

        def validate(self, request: ProcessingRequest) -> None:
            return None

        def process_with_context(
            self,
            image: str,
            request: ProcessingRequest,
            context: ProcessingContext,
        ) -> str:
            context.cancellation.cancel()
            return image

    token = MutableCancellationToken()
    with pytest.raises(CancellationError):
        ProcessingEngine({"late-cancel": CancelAfterReturnProcessor()}).run(
            "dip",
            ProcessingRequest("late-cancel"),
            cancellation=token,
        )


def test_processing_engine_preview_builds_context_without_mutation() -> None:
    processor = ContextProcessor()
    result = ProcessingEngine({"context": processor}).preview(
        "dip",
        ProcessingRequest("context"),
        mask="mask-1",
        selection="selection-1",
        color_space="sRGB",
        resolution=(640, 480),
    )

    assert result == "dip!"
    assert processor.seen_context is not None
    assert processor.seen_context.preview_mode is True
    assert processor.seen_context.mask == "mask-1"
    assert processor.seen_context.selection == "selection-1"
    assert processor.seen_context.resolution == (640, 480)


def test_processing_cache_separates_context_dimensions() -> None:
    class CountingProcessor:
        operation = "count"

        def __init__(self) -> None:
            self.calls = 0

        def validate(self, request: ProcessingRequest) -> None:
            return None

        def process(self, image: str, request: ProcessingRequest) -> str:
            self.calls += 1
            return f"{image}-{self.calls}"

    store = ImageDataStore()
    source = store.allocate(np.zeros((2, 2), dtype=np.uint8))
    processor = CountingProcessor()
    engine = ProcessingEngine(
        {"count": processor},
        cache=ProcessingCache(),
        data_store=store,
    )
    request = ProcessingRequest("count")

    class Reporter:
        def report(self, completed: int, total: int, message: str = "") -> None:
            return None

    first = engine.run_context(
        source,
        request,
        ProcessingContext(
            image=source,
            mask="mask-a",
            selection="selection-a",
            color_space=None,
            resolution=None,
            preview_mode=False,
            cancellation=MutableCancellationToken(),
            progress=Reporter(),
            metadata={},
        ),
    )
    second = engine.run_context(
        source,
        request,
        ProcessingContext(
            image=source,
            mask="mask-b",
            selection="selection-a",
            color_space=None,
            resolution=None,
            preview_mode=False,
            cancellation=MutableCancellationToken(),
            progress=Reporter(),
            metadata={},
        ),
    )
    assert first != second
    assert processor.calls == 2


def test_processing_cache_invalidates_when_context_buffer_changes() -> None:
    class CountingProcessor:
        operation = "count"

        def __init__(self) -> None:
            self.calls = 0

        def validate(self, request: ProcessingRequest) -> None:
            return None

        def process(self, image: str, request: ProcessingRequest) -> str:
            self.calls += 1
            return store.allocate(np.full((2, 2), self.calls, dtype=np.uint8))

    store = ImageDataStore()
    source = store.allocate(np.zeros((2, 2), dtype=np.uint8))
    mask = store.allocate(np.ones((2, 2), dtype=np.uint8))
    selection = store.allocate(np.ones((2, 2), dtype=np.uint8))
    processor = CountingProcessor()
    cache = ProcessingCache()
    engine = ProcessingEngine(
        {"count": processor},
        cache=cache,
        data_store=store,
    )
    request = ProcessingRequest("count")

    context = ProcessingContext(
        image=source,
        mask=mask,
        selection=selection,
        color_space=None,
        resolution=None,
        preview_mode=False,
        cancellation=MutableCancellationToken(),
        progress=type("Reporter", (), {"report": lambda *_args: None})(),
        metadata={},
    )
    first = engine.run_context(source, request, context)
    assert engine.run_context(source, request, context) == first
    assert processor.calls == 1

    store.touch(mask)
    second = engine.run_context(source, request, context)
    assert second != first
    assert processor.calls == 2
    assert cache.statistics() == (1, 2)


def test_cache_key_normalizes_parameter_order_and_operation_version() -> None:
    from dip_studio.infrastructure.processing_cache import CacheKey

    first = CacheKey.build(
        "source",
        0,
        "blur",
        (("radius", "2"), ("sigma", "1")),
        operation_version="1",
    )
    reordered = CacheKey.build(
        "source",
        0,
        "blur",
        (("sigma", "1"), ("radius", "2")),
        operation_version="1",
    )
    upgraded = CacheKey.build(
        "source",
        0,
        "blur",
        (("radius", "2"), ("sigma", "1")),
        operation_version="2",
    )

    assert first == reordered
    assert first != upgraded


def test_cache_invalidates_entries_referencing_mask_or_selection() -> None:
    from dip_studio.infrastructure.processing_cache import CacheKey

    cache = ProcessingCache()
    mask_key = CacheKey.build(
        "source", 0, "op", (), mask_id="mask", mask_version=0
    )
    selection_key = CacheKey.build(
        "source", 0, "op", (), selection_id="selection", selection_version=0
    )
    cache.put(mask_key, "mask-result")
    cache.put(selection_key, "selection-result")

    cache.invalidate_buffer("mask")
    assert cache.get(mask_key) is None
    assert cache.get(selection_key) == "selection-result"

    cache.invalidate_buffer("selection")
    assert cache.get(selection_key) is None
