import pytest

from dip_studio.application.result_store import ProcessingResultStore
from dip_studio.core.errors import ValidationError
from dip_studio.domain.cv_model import (
    BoundingBox,
    DetectedObject,
    ObjectCollection,
    Trajectory,
    TrajectoryPoint,
)
from dip_studio.processing.contracts import FeatureResult, ObjectCollectionResult, TrajectoryResult


def test_processing_result_store_keeps_typed_results_per_document() -> None:
    store = ProcessingResultStore()
    result = FeatureResult({"mean": 12.5})

    store.put("doc-a", "features-1", result)

    assert store.get("doc-a", "features-1") == result
    assert store.snapshot("doc-b") == {}
    snapshot = store.snapshot("doc-a")
    assert snapshot == {"features-1": result}


def test_processing_result_store_rejects_unknown_or_empty_ids() -> None:
    store = ProcessingResultStore()
    with pytest.raises(ValueError):
        store.put("doc-a", " ", FeatureResult({}))
    with pytest.raises(ValueError):
        store.put("", "features-1", FeatureResult({}))
    with pytest.raises(KeyError, match="not found"):
        store.get("doc-a", "missing")


def test_cv_result_types_validate_and_match_document_store() -> None:
    obj = DetectedObject(
        object_id="obj-1",
        class_name="cat",
        confidence=0.91,
        bbox=BoundingBox(2, 4, 10, 12),
        centroid=(7.0, 10.0),
    )
    ObjectCollection(0, 0.0, (obj,), 100, 100)
    trajectory = Trajectory("obj-1", "cat", (TrajectoryPoint(0, 0.0, 7.0, 10.0, "obj-1"),))

    store = ProcessingResultStore()
    store.put("doc-a", "objects-1", ObjectCollectionResult((obj,)))
    store.put("doc-a", "trajectory-1", TrajectoryResult((trajectory,)))

    assert store.get("doc-a", "objects-1") == ObjectCollectionResult((obj,))
    assert store.get("doc-a", "trajectory-1") == TrajectoryResult((trajectory,))

    with pytest.raises(ValidationError):
        BoundingBox(0, 0, -1, 2)
    with pytest.raises(ValidationError):
        DetectedObject("obj-2", "cat", 1.5, BoundingBox(0, 0, 3, 3), (1.0, 1.0))
