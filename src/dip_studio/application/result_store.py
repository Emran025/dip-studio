"""Application-owned storage for typed, non-pixel processing results."""

from __future__ import annotations

from collections.abc import Mapping

from dip_studio.processing.contracts import (
    ContourResult,
    FeatureResult,
    ImageResult,
    MaskResult,
    ObjectCollectionResult,
    ProcessingResult,
    SelectionResult,
    TrajectoryResult,
)


class ProcessingResultStore:
    """Keeps typed results separate from pixel buffers and document history."""

    _VALID_RESULT_TYPES = (
        ImageResult,
        MaskResult,
        SelectionResult,
        ContourResult,
        FeatureResult,
        ObjectCollectionResult,
        TrajectoryResult,
    )

    def __init__(self) -> None:
        self._results: dict[str, dict[str, ProcessingResult]] = {}

    def put(self, document_id: object, result_id: str, result: ProcessingResult) -> None:
        if document_id is None or str(document_id).strip() == "":
            raise ValueError("Document id cannot be empty")
        if not result_id.strip():
            raise ValueError("Result id cannot be empty")
        if not isinstance(result, self._VALID_RESULT_TYPES):
            raise TypeError(
                "Processing result must be one of the typed processing result dataclasses"
            )
        self._results.setdefault(str(document_id), {})[result_id] = result

    def get(self, document_id: object, result_id: str) -> ProcessingResult:
        try:
            return self._results[str(document_id)][result_id]
        except KeyError as exc:
            raise KeyError(f"Processing result not found: {result_id}") from exc

    def snapshot(self, document_id: object) -> Mapping[str, ProcessingResult]:
        return dict(self._results.get(str(document_id), {}))

    def remove_document(self, document_id: object) -> None:
        self._results.pop(str(document_id), None)

    def clear(self) -> None:
        self._results.clear()
