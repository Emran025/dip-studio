"""Processing orchestration with no UI or image-library knowledge."""

from typing import Generic, TypeVar

from dip_studio.processing.contracts import ProcessingRequest, Processor

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class ProcessingEngine(Generic[InputT, OutputT]):
    def __init__(self, processors: dict[str, Processor[InputT, OutputT]]) -> None:
        self._processors = dict(processors)

    def run(self, image: InputT, request: ProcessingRequest) -> OutputT:
        processor = self._processors.get(request.operation)
        if processor is None:
            raise KeyError(f"Unknown processing operation: {request.operation}")
        processor.validate(request)
        return processor.process(image, request)

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
