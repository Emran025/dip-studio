import numpy as np
import pytest

from dip_studio.core.errors import OptionalBackendError, ProcessingError
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors.cv.object_detection import (
    HoughCirclesProcessor,
    TemplateMatchProcessor,
)


def test_template_match_rejects_missing_template_buffer() -> None:
    store = ImageDataStore()
    source = store.allocate(np.zeros((4, 4), dtype=np.uint8))

    with pytest.raises(ProcessingError, match="template_buffer_id"):
        TemplateMatchProcessor(store).process(source, ProcessingRequest("template_match"))


def test_optional_backend_error_is_distinct_from_processing_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dip_studio.processing.processors.cv.object_detection as module

    store = ImageDataStore()
    source = store.allocate(np.zeros((4, 4), dtype=np.uint8))
    template = store.allocate(np.zeros((2, 2), dtype=np.uint8))
    monkeypatch.setattr(module, "_CV2", False)

    with pytest.raises(OptionalBackendError, match="OpenCV"):
        TemplateMatchProcessor(store).process(
            source,
            ProcessingRequest(
                "template_match",
                (("template_buffer_id", template),),
            ),
        )


def test_hough_circle_does_not_report_success_without_opencv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dip_studio.processing.processors.cv.object_detection as module

    store = ImageDataStore()
    source = store.allocate(np.zeros((4, 4), dtype=np.uint8))
    monkeypatch.setattr(module, "_CV2", False)

    with pytest.raises(OptionalBackendError, match="OpenCV"):
        HoughCirclesProcessor(store).process(source, ProcessingRequest("hough_circles"))
