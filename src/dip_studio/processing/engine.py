"""Processing orchestration with no UI or image-library knowledge."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from dip_studio.core.cancellation import CancellationToken, ProgressReporter
from dip_studio.processing.contracts import (
    ProcessingContext,
    ProcessingRequest,
    Processor,
)

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore
    from dip_studio.infrastructure.processing_cache import ProcessingCache

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class ProcessingEngine[InputT, OutputT]:
    """Orchestrates processor dispatch with optional LRU result caching.

    Parameters
    ----------
    processors : dict[str, Processor]
        Initial processor map keyed by operation string.
    cache : ProcessingCache | None
        Optional LRU cache.  When provided and the engine operates on
        ``buffer_id`` strings (the common case), cache hits skip the
        processor entirely and return the previously computed buffer_id.
    data_store : ImageDataStore | None
        Required when *cache* is provided — used to read the buffer
        version for cache key construction.
    """

    def __init__(
        self,
        processors: dict[str, Processor[InputT, OutputT]],
        cache: ProcessingCache | None = None,
        data_store: ImageDataStore | None = None,
    ) -> None:
        self._processors = dict(processors)
        self._cache = cache
        self._data_store = data_store

    def run(
        self,
        image: InputT,
        request: ProcessingRequest,
        *,
        cancellation: CancellationToken | None = None,
        progress: ProgressReporter | None = None,
        metadata: dict[str, object] | None = None,
    ) -> OutputT:
        _validate_request_shape(request)
        processor = self._processors.get(request.operation)
        if processor is None:
            raise KeyError(f"Unknown processing operation: {request.operation}")
        processor.validate(request)
        if cancellation is not None:
            cancellation.throw_if_cancelled()

        context = ProcessingContext(
            image=image,
            mask=None,
            selection=None,
            color_space=None,
            resolution=None,
            preview_mode=False,
            cancellation=cancellation or _NoopCancellationToken(),
            progress=progress or _NoopProgressReporter(),
            metadata=metadata or {},
        )
        return self.run_context(
            image,
            request,
            context,
            processor=processor,
        )

    def run_context(
        self,
        image: InputT,
        request: ProcessingRequest,
        context: ProcessingContext,
        *,
        processor: Processor[InputT, OutputT] | None = None,
    ) -> OutputT:
        """Run a processor with an explicit, fully described context."""
        _validate_request_shape(request)
        active_processor = processor or self._processors.get(request.operation)
        if active_processor is None:
            raise KeyError(f"Unknown processing operation: {request.operation}")
        active_processor.validate(request)
        context.cancellation.throw_if_cancelled()

        # ── Cache probe (only when image is a buffer_id string) ──────────────
        if (
            not context.preview_mode
            and self._cache is not None
            and self._data_store is not None
            and isinstance(image, str)
        ):
            from dip_studio.infrastructure.processing_cache import CacheKey

            buf_ver = self._data_store.version(image)
            mask_ver = (
                self._data_store.version(context.mask)
                if context.mask is not None and self._data_store.has(context.mask)
                else None
            )
            selection_ver = (
                self._data_store.version(context.selection)
                if context.selection is not None and self._data_store.has(context.selection)
                else None
            )
            key = CacheKey.build(
                image,
                buf_ver,
                request.operation,
                request.parameters,
                operation_version=str(getattr(active_processor, "version", "1")),
                mask_id=context.mask,
                mask_version=mask_ver,
                selection_id=context.selection,
                selection_version=selection_ver,
                preview_mode=context.preview_mode,
            )
            cached = self._cache.get(key)
            if cached is not None:
                if self._data_store.has(cached):
                    return cached  # type: ignore[return-value]
                self._cache.invalidate_buffer(image)

            result = self._process(active_processor, image, request, context)
            context.cancellation.throw_if_cancelled()

            # Store result only when it is also a buffer_id string.
            if isinstance(result, str):
                self._cache.put(key, result)
            return result
        # ─────────────────────────────────────────────────────────────────────

        result = self._process(active_processor, image, request, context)
        context.cancellation.throw_if_cancelled()
        return result

    def preview(
        self,
        image: InputT,
        request: ProcessingRequest,
        *,
        mask: str | None = None,
        selection: str | None = None,
        color_space: str | None = None,
        resolution: tuple[int, int] | None = None,
        cancellation: CancellationToken | None = None,
        progress: ProgressReporter | None = None,
        metadata: dict[str, object] | None = None,
    ) -> OutputT:
        """Evaluate a request in preview mode without changing the document."""
        processor = self._processors.get(request.operation)
        if processor is None:
            raise KeyError(f"Unknown processing operation: {request.operation}")
        context = ProcessingContext(
            image=image,
            mask=mask,
            selection=selection,
            color_space=color_space,
            resolution=resolution,
            preview_mode=True,
            cancellation=cancellation or _NoopCancellationToken(),
            progress=progress or _NoopProgressReporter(),
            metadata=metadata or {},
        )
        return self.run_context(image, request, context, processor=processor)

    @staticmethod
    def _process(
        processor: Processor[InputT, OutputT],
        image: InputT,
        request: ProcessingRequest,
        context: ProcessingContext | None,
    ) -> OutputT:
        if context is not None:
            context.cancellation.throw_if_cancelled()
        context_processor = getattr(processor, "process_with_context", None)
        if context is not None and callable(context_processor):
            result = context_processor(image, request, context)
            context.cancellation.throw_if_cancelled()
            return result
        result = processor.process(image, request)
        if context is not None:
            context.cancellation.throw_if_cancelled()
        return result

    def register(self, processor: Processor[InputT, OutputT]) -> None:
        """Register or replace a processor by its operation id.

        Used by the plugin system to add processors at runtime.
        """
        self._processors[processor.operation] = processor

    def unregister(self, operation: str) -> None:
        """Remove a processor by its operation id (no-op if not registered)."""
        self._processors.pop(operation, None)

    @property
    def operations(self) -> tuple[str, ...]:
        """Return all currently registered operation ids."""
        return tuple(self._processors)


class _NoopCancellationToken:
    @property
    def is_cancelled(self) -> bool:
        return False

    def throw_if_cancelled(self) -> None:
        return None


class _NoopProgressReporter:
    def report(self, completed: int, total: int, message: str = "") -> None:
        return None


def _validate_request_shape(request: ProcessingRequest) -> None:
    """Reject malformed requests before dispatching to a processor."""
    if not request.operation.strip():
        raise ValueError("Processing operation cannot be empty")
    names = [name for name, _ in request.parameters]
    if any(not name.strip() for name in names):
        raise ValueError("Processing parameter names cannot be empty")
    if len(names) != len(set(names)):
        raise ValueError("Processing parameters cannot contain duplicate names")
