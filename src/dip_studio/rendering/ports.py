"""Rendering port; processing produces data, rendering produces a view."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RenderRequest:
    document_id: str
    viewport_width: int
    viewport_height: int
    zoom: float = 1.0


class RenderEngine(Protocol):
    def render(self, request: RenderRequest) -> bytes: ...
