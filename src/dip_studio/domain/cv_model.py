"""Computer Vision domain objects — pure dataclasses, no NumPy or Qt.

All types are frozen + slotted (CoW-safe, hashable, immutable) following
the same conventions as ``dip_studio.domain.model``.

Architecture: doc-12 specifies the CV object model.
"""

from __future__ import annotations

from dataclasses import dataclass

from dip_studio.core.errors import ValidationError


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned bounding rectangle in image pixel coordinates."""

    x: int  # left edge
    y: int  # top edge
    width: int
    height: int

    def __post_init__(self) -> None:
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise ValidationError("BoundingBox coordinates must be integers")
        if self.width < 0 or self.height < 0:
            raise ValidationError("BoundingBox width and height cannot be negative")

    @property
    def cx(self) -> float:
        """Centroid x."""
        return self.x + self.width / 2.0

    @property
    def cy(self) -> float:
        """Centroid y."""
        return self.y + self.height / 2.0

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class DetectedObject:
    """Single detected object produced by a detector or feature extractor.

    Fields per doc-12 object model:
    ``class_name``   — human-readable detection class label.
    ``confidence``   — detector confidence in [0.0, 1.0].
    ``bbox``         — bounding box in image coords.
    ``centroid``     — (cx, cy) in float image coords.
    ``contour_points``— ordered (x, y) boundary points (empty if unavailable).
    ``features``     — compact feature descriptor vector (e.g. 128-dim SIFT).
    ``metadata``     — arbitrary string key→value pairs for extra fields.
    """

    object_id: str  # UUID string
    class_name: str
    confidence: float  # 0.0–1.0
    bbox: BoundingBox
    centroid: tuple[float, float]
    contour_points: tuple[tuple[int, int], ...] = ()
    features: tuple[float, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValidationError("DetectedObject.object_id cannot be empty")
        if not self.class_name.strip():
            raise ValidationError("DetectedObject.class_name cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValidationError("DetectedObject.confidence must be between 0.0 and 1.0")
        if not isinstance(self.bbox, BoundingBox):
            raise ValidationError("DetectedObject.bbox must be a BoundingBox")
        if len(self.centroid) != 2:
            raise ValidationError("DetectedObject.centroid must contain exactly two values")
        for point in self.contour_points:
            if len(point) != 2:
                raise ValidationError("DetectedObject.contour_points must be (x, y) tuples")
        for value in self.features:
            if not isinstance(value, (int, float)):
                raise ValidationError("DetectedObject.features must be numeric")

    @property
    def area(self) -> int:
        return self.bbox.area

    @property
    def aspect_ratio(self) -> float:
        return self.bbox.width / max(1, self.bbox.height)


@dataclass(frozen=True, slots=True)
class ObjectCollection:
    """Set of detected objects for a single frame / image.

    ``frame_index`` and ``timestamp`` allow time-series use; both are 0
    for single-image processing.
    """

    frame_index: int
    timestamp: float  # seconds since sequence start (0.0 for stills)
    objects: tuple[DetectedObject, ...]
    image_width: int
    image_height: int

    def by_class(self, class_name: str) -> ObjectCollection:
        """Return a new collection with only objects of the given class."""
        filtered = tuple(o for o in self.objects if o.class_name == class_name)
        return ObjectCollection(
            self.frame_index,
            self.timestamp,
            filtered,
            self.image_width,
            self.image_height,
        )

    def __post_init__(self) -> None:
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValidationError("ObjectCollection dimensions must be positive")
        for obj in self.objects:
            if not isinstance(obj, DetectedObject):
                raise ValidationError("ObjectCollection.objects must contain DetectedObject values")
            if obj.bbox.x < 0 or obj.bbox.y < 0:
                raise ValidationError("DetectedObject bbox coordinates must be non-negative")
            if (
                obj.bbox.x + obj.bbox.width > self.image_width
                or obj.bbox.y + obj.bbox.height > self.image_height
            ):
                raise ValidationError("DetectedObject bbox falls outside image bounds")

    def __len__(self) -> int:
        return len(self.objects)


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    """Single point in a tracked object's trajectory."""

    frame_index: int
    timestamp: float  # seconds
    x: float  # image-space x of centroid
    y: float  # image-space y of centroid
    object_id: str

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValidationError("TrajectoryPoint.frame_index cannot be negative")
        if self.timestamp < 0.0:
            raise ValidationError("TrajectoryPoint.timestamp cannot be negative")
        if not self.object_id.strip():
            raise ValidationError("TrajectoryPoint.object_id cannot be empty")


@dataclass(frozen=True, slots=True)
class Trajectory:
    """Complete motion path of one tracked object across frames.

    ``points`` are ordered chronologically by ``frame_index``.
    Export formats: JSON (``to_json_dict()``) or CSV rows (``to_csv_rows()``).
    """

    object_id: str
    class_name: str
    points: tuple[TrajectoryPoint, ...]

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValidationError("Trajectory.object_id cannot be empty")
        if not self.class_name.strip():
            raise ValidationError("Trajectory.class_name cannot be empty")
        for point in self.points:
            if not isinstance(point, TrajectoryPoint):
                raise ValidationError("Trajectory.points must contain TrajectoryPoint values")

    def to_json_dict(self) -> dict:
        return {
            "object_id": self.object_id,
            "class_name": self.class_name,
            "points": [
                {
                    "frame": p.frame_index,
                    "timestamp": p.timestamp,
                    "x": p.x,
                    "y": p.y,
                }
                for p in self.points
            ],
        }

    def to_csv_rows(self) -> list[list]:
        """Return list-of-lists suitable for ``csv.writer.writerows()``."""
        rows = [["object_id", "class_name", "frame", "timestamp", "x", "y"]]
        for p in self.points:
            rows.append([self.object_id, self.class_name, p.frame_index, p.timestamp, p.x, p.y])
        return rows

    def __len__(self) -> int:
        return len(self.points)
