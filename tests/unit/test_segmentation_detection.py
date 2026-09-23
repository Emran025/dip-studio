from __future__ import annotations

import numpy as np
import pytest

from dip_studio.application.tool_registry import processing_tool_definitions
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.presentation.tool_panel import ToolPanel
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors.cv.object_detection import (
    HoughCirclesProcessor,
    HoughLinesProcessor,
    TemplateMatchProcessor,
)
from dip_studio.processing.processors.segmentation_advanced import (
    ConnectedComponentsProcessor,
    ContourExtractProcessor,
    RegionGrowingProcessor,
    WatershedProcessor,
)


def req(operation: str, **values: object) -> ProcessingRequest:
    return ProcessingRequest(operation, tuple((key, str(value)) for key, value in values.items()))


def test_segmentation_and_detection_are_exposed_in_properties_and_toolbar() -> None:
    definitions = {item.id: item for item in processing_tool_definitions()}
    assert {
        "watershed",
        "region_growing",
        "contour_extract",
        "hu_moments",
        "connected_components",
        "grabcut",
        "active_contours",
        "hough_circles",
        "hough_lines",
    } <= definitions.keys()
    groups = dict(ToolPanel._GROUPS)
    combined = groups["Segmentation & Detection"]
    assert combined[-3:] == ("template_match", "hough_circles", "hough_lines")
    assert "watershed" in combined
    assert "connected_components" in combined


def test_segmentation_processors_preserve_image_bounds_and_shape() -> None:
    store = ImageDataStore()
    image = np.zeros((32, 40, 3), dtype=np.uint8)
    image[5:27, 8:32] = 220
    image[12:20, 16:24] = 30
    buffer_id = store.allocate(image)

    for processor, operation, values in (
        (WatershedProcessor, "watershed", {"min_distance": 5, "threshold": 100}),
        (RegionGrowingProcessor, "region_growing", {"seed_x": 20, "seed_y": 10, "tolerance": 20}),
        (ContourExtractProcessor, "contour_extract", {"threshold": 100}),
        (ConnectedComponentsProcessor, "connected_components", {"threshold": 100}),
    ):
        result_id = processor(store).process(buffer_id, req(operation, **values))
        result = store.get(result_id)
        assert result.shape[:2] == image.shape[:2]
        assert result.dtype == np.uint8


@pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("cv2") is None,
    reason="OpenCV is optional",
)
def test_detection_outputs_keep_source_channel_count_and_template_methods() -> None:
    store = ImageDataStore()
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[20:44, 20:44] = 255
    image[8:56, 32:34] = 255
    source_id = store.allocate(image)
    template_id = store.allocate(image[20:28, 20:28])

    for processor, operation, values in (
        (HoughCirclesProcessor, "hough_circles", {"dp": 1, "min_dist": 10}),
        (HoughLinesProcessor, "hough_lines", {"threshold": 20, "min_length": 10}),
    ):
        result_id = processor(store).process(source_id, req(operation, **values))
        assert store.get(result_id).shape == image.shape

    for method in ("TM_CCOEFF_NORMED", "TM_SQDIFF_NORMED"):
        result_id = TemplateMatchProcessor(store).process(
            source_id, req("template_match", template_buffer_id=template_id, method=method)
        )
        assert store.get(result_id).shape == image.shape


def test_template_matching_rejects_template_larger_than_source() -> None:
    store = ImageDataStore()
    source_id = store.allocate(np.zeros((8, 8), dtype=np.uint8))
    template_id = store.allocate(np.zeros((12, 12), dtype=np.uint8))
    if __import__("importlib.util").util.find_spec("cv2") is None:
        pytest.skip("OpenCV is optional")
    from dip_studio.core.errors import ProcessingError

    with pytest.raises(ProcessingError, match="no larger"):
        TemplateMatchProcessor(store).process(
            source_id, req("template_match", template_buffer_id=template_id)
        )
