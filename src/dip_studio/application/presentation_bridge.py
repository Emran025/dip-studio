"""Application factories used by presentation without exposing domain imports."""
from __future__ import annotations

from dip_studio.domain.model import Layer, SelectionRect, TextLayer


def is_text_layer(layer: Layer) -> bool:
    return isinstance(layer, TextLayer)


def make_selection(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    kind: str,
    mask_buffer_id: str | None = None,
) -> SelectionRect:
    return SelectionRect(
        x=x,
        y=y,
        width=width,
        height=height,
        kind=kind,
        mask_buffer_id=mask_buffer_id,
    )


def make_text_layer(**kwargs: object) -> TextLayer:
    return TextLayer(**kwargs)  # type: ignore[arg-type]


def rasterise_ellipse(
    width: int,
    height: int,
    center_x: int,
    center_y: int,
    radius_x: int,
    radius_y: int,
):
    from dip_studio.infrastructure.selection_geometry import rasterise_ellipse as rasterise
    return rasterise(width, height, center_x, center_y, radius_x, radius_y)


def rasterise_lasso(width: int, height: int, points: list[tuple[int, int]]):
    from dip_studio.infrastructure.selection_geometry import rasterise_lasso as rasterise
    return rasterise(width, height, points)


def rasterise_polygon(width: int, height: int, points: list[tuple[int, int]]):
    from dip_studio.infrastructure.selection_geometry import rasterise_polygon as rasterise
    return rasterise(width, height, points)


def rasterise_color_selection(arr: object, seed_x: int, seed_y: int, tolerance: int = 15):
    from dip_studio.infrastructure.selection_geometry import rasterise_color_selection as rasterise
    return rasterise(arr, seed_x, seed_y, tolerance)


def is_group_layer(layer: object) -> bool:
    from dip_studio.domain.model import GroupLayer
    return isinstance(layer, GroupLayer)


def parse_doc_directory(docs_dir: object) -> tuple[object, ...]:
    from pathlib import Path
    from dip_studio.infrastructure.doc_parser import DocParser
    return DocParser.parse_directory(Path(str(docs_dir)))
