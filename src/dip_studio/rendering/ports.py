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


class BlankDocumentRenderer:
    """Small first-slice renderer producing a valid white PPM preview."""

    def render(self, request: RenderRequest) -> bytes:
        if request.viewport_width <= 0 or request.viewport_height <= 0:
            raise ValueError("Viewport dimensions must be positive")
        width = max(1, round(request.viewport_width * request.zoom))
        height = max(1, round(request.viewport_height * request.zoom))
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        return header + b"\xff\xff\xff" * (width * height)
