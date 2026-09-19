"""Processing orchestration with no UI or image-library knowledge."""

from dip_studio.processing.contracts import ProcessingRequest, Processor


class ProcessingEngine[InputT, OutputT]:
    def __init__(self, processors: dict[str, Processor[InputT, OutputT]]) -> None:
        self._processors = processors

    def run(self, image: InputT, request: ProcessingRequest) -> OutputT:
        processor = self._processors.get(request.operation)
        if processor is None:
            raise KeyError(f"Unknown processing operation: {request.operation}")
        processor.validate(request)
        return processor.process(image, request)
