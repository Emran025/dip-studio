"""Deterministic object tracking over CV object collections."""
from __future__ import annotations

from dip_studio.domain.cv_model import (
    DetectedObject,
    ObjectCollection,
    Trajectory,
    TrajectoryPoint,
)


def track_collections(
    collections: tuple[ObjectCollection, ...],
    *,
    max_centroid_distance: float | None = None,
    minimum_iou: float | None = None,
) -> tuple[Trajectory, ...]:
    """Track objects frame-to-frame using deterministic greedy matching.

    At least one matching criterion must be supplied.  A candidate matches
    when it satisfies every supplied criterion.  Ties are resolved by source
    collection order, then object id, making repeated runs stable.
    """
    if max_centroid_distance is None and minimum_iou is None:
        raise ValueError("At least one tracking criterion is required")
    if max_centroid_distance is not None and max_centroid_distance < 0:
        raise ValueError("max_centroid_distance cannot be negative")
    if minimum_iou is not None and not 0.0 <= minimum_iou <= 1.0:
        raise ValueError("minimum_iou must be between zero and one")
    if not collections:
        return ()

    tracks: dict[str, list[TrajectoryPoint]] = {}
    classes: dict[str, str] = {}
    previous: list[tuple[str, DetectedObject]] = []
    next_id = 0
    first = collections[0]
    for obj in first.objects:
        track_id = obj.object_id
        tracks[track_id] = [_point(first, obj, track_id)]
        classes[track_id] = obj.class_name
        previous.append((track_id, obj))

    for collection in collections[1:]:
        unmatched = list(collection.objects)
        current: list[tuple[str, DetectedObject]] = []
        for track_id, old in previous:
            candidates = [
                (index, obj)
                for index, obj in enumerate(unmatched)
                if _matches(old, obj, max_centroid_distance, minimum_iou)
            ]
            if not candidates:
                continue
            index, obj = min(
                candidates,
                key=lambda item: (_distance(old, item[1]), item[1].object_id),
            )
            unmatched.pop(index)
            tracks[track_id].append(_point(collection, obj, track_id))
            classes[track_id] = obj.class_name
            current.append((track_id, obj))
        for obj in unmatched:
            track_id = obj.object_id
            while track_id in tracks:
                next_id += 1
                track_id = f"{obj.object_id}:{next_id}"
            tracks[track_id] = [_point(collection, obj, track_id)]
            classes[track_id] = obj.class_name
            current.append((track_id, obj))
        previous = current

    return tuple(
        Trajectory(track_id, classes[track_id], tuple(points))
        for track_id, points in tracks.items()
    )


def _point(collection: ObjectCollection, obj: DetectedObject, track_id: str) -> TrajectoryPoint:
    return TrajectoryPoint(
        collection.frame_index,
        collection.timestamp,
        obj.centroid[0],
        obj.centroid[1],
        track_id,
    )


def _distance(left: DetectedObject, right: DetectedObject) -> float:
    dx = left.centroid[0] - right.centroid[0]
    dy = left.centroid[1] - right.centroid[1]
    return (dx * dx + dy * dy) ** 0.5


def _matches(
    left: DetectedObject,
    right: DetectedObject,
    max_distance: float | None,
    minimum_iou: float | None,
) -> bool:
    if max_distance is not None and _distance(left, right) > max_distance:
        return False
    if minimum_iou is not None and _iou(left, right) < minimum_iou:
        return False
    return True


def _iou(left: DetectedObject, right: DetectedObject) -> float:
    lx = max(left.bbox.x, right.bbox.x)
    ly = max(left.bbox.y, right.bbox.y)
    rx = min(left.bbox.x + left.bbox.width, right.bbox.x + right.bbox.width)
    ry = min(left.bbox.y + left.bbox.height, right.bbox.y + right.bbox.height)
    intersection = max(0, rx - lx) * max(0, ry - ly)
    union = left.area + right.area - intersection
    return intersection / union if union else 0.0
