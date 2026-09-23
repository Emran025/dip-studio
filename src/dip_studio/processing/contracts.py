"""Pure processing contracts; concrete algorithms live behind these ports."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from dip_studio.core.cancellation import CancellationToken, ProgressReporter
from dip_studio.domain.cv_model import DetectedObject, Trajectory

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    operation: str
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessingContext:
    """Immutable processing inputs and runtime services."""

    image: object
    mask: str | None
    selection: str | None
    color_space: str | None
    resolution: tuple[int, int] | None
    preview_mode: bool
    cancellation: CancellationToken
    progress: ProgressReporter
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ImageResult:
    buffer_id: str


@dataclass(frozen=True, slots=True)
class MaskResult:
    buffer_id: str


@dataclass(frozen=True, slots=True)
class SelectionResult:
    mask_buffer_id: str


@dataclass(frozen=True, slots=True)
class ContourResult:
    contours: tuple[tuple[tuple[float, float], ...], ...]

    def __post_init__(self) -> None:
        for contour in self.contours:
            if not isinstance(contour, tuple):
                raise TypeError("ContourResult.contours must be a tuple of contour tuples")


@dataclass(frozen=True, slots=True)
class FeatureResult:
    features: Mapping[str, float | int | str]

    def __post_init__(self) -> None:
        if not isinstance(self.features, Mapping):
            raise TypeError("FeatureResult.features must be a mapping")


@dataclass(frozen=True, slots=True)
class ObjectCollectionResult:
    objects: tuple[DetectedObject, ...]

    def __post_init__(self) -> None:
        for obj in self.objects:
            if not isinstance(obj, DetectedObject):
                raise TypeError("ObjectCollectionResult.objects must contain DetectedObject values")


@dataclass(frozen=True, slots=True)
class TrajectoryResult:
    trajectories: tuple[Trajectory, ...]

    def __post_init__(self) -> None:
        for trajectory in self.trajectories:
            if not isinstance(trajectory, Trajectory):
                raise TypeError("TrajectoryResult.trajectories must contain Trajectory values")


type ProcessingResult = (
    ImageResult
    | MaskResult
    | SelectionResult
    | ContourResult
    | FeatureResult
    | ObjectCollectionResult
    | TrajectoryResult
)


class ContextProcessor(Protocol[InputT, OutputT]):
    """Optional extension for processors that support runtime context."""

    operation: str

    def process_with_context(
        self,
        image: InputT,
        request: ProcessingRequest,
        context: ProcessingContext,
    ) -> OutputT: ...


class Processor(Protocol[InputT, OutputT]):
    operation: str

    def validate(self, request: ProcessingRequest) -> None: ...
    def process(self, image: InputT, request: ProcessingRequest) -> OutputT: ...
