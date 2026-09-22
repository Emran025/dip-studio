from dip_studio.application.cv_tracking import track_collections
from dip_studio.domain.cv_model import BoundingBox, DetectedObject, ObjectCollection
from dip_studio.infrastructure.cv_export import trajectories_to_csv, trajectories_to_json


def _object(object_id: str, x: float, y: float) -> DetectedObject:
    return DetectedObject(
        object_id, "item", 1.0, BoundingBox(int(x), int(y), 10, 10), (x, y)
    )


def test_tracking_is_deterministic_and_uses_centroid() -> None:
    frames = (
        ObjectCollection(0, 0.0, (_object("a", 2, 2),), 30, 30),
        ObjectCollection(1, 1.0, (_object("b", 3, 2),), 30, 30),
    )

    trajectories = track_collections(frames, max_centroid_distance=2.0)

    assert len(trajectories) == 1
    assert [point.frame_index for point in trajectories[0].points] == [0, 1]


def test_trajectory_exports_are_versioned() -> None:
    frames = (ObjectCollection(0, 0.0, (_object("a", 2, 2),), 30, 30),)
    trajectory = track_collections(frames, max_centroid_distance=0.0)

    assert '"version": 1' in trajectories_to_json(trajectory, version=1)
    csv_output = trajectories_to_csv(trajectory, version=1)
    assert "dip-studio-trajectories" in csv_output
    assert ",version,1" in csv_output
