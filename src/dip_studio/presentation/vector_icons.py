"""Small, consistent vector icon set for the editor chrome."""

import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from dip_studio.presentation.theme import DARK

_ICON_SIZE = 64
_STROKE = 3.0
_APP_ICON_NAME = "image-processing-icon.svg"


_QTAWESOME_NAMES = {
    "select": "mdi6.cursor-default-outline",
    "selection": "mdi6.select-drag",
    "ellipse_selection": "mdi6.selection-ellipse",
    "lasso": "mdi6.vector-polyline",
    "polygon_selection": "mdi6.vector-polygon",
    "color_selection": "mdi6.format-color-fill",
    "crop": "mdi6.crop-free",
    "move": "mdi6.cursor-move",
    "transform": "mdi6.vector-combine",
    "rotate": "mdi6.rotate-right",
    "blur": "mdi6.blur",
    "edge": "mdi6.chart-line",
    "gradient": "mdi6.tune-vertical",
    "brush": "mdi6.brush-outline",
    "pencil": "mdi6.pencil-outline",
    "eraser": "mdi6.eraser",
    "fill": "mdi6.format-color-fill",
    "clone": "mdi6.content-duplicate",
    "hand": "mdi6.hand-back-right-outline",
    "zoom": "mdi6.magnify",
    "eyedropper": "mdi6.eyedropper",
    "text": "mdi6.format-text",
    "shape": "mdi6.shape-outline",
    "shape_rectangle": "mdi6.rectangle-outline",
    "shape_ellipse": "mdi6.ellipse-outline",
    "shape_line": "mdi6.vector-line",
    "shape_polygon": "mdi6.vector-polygon",
    "histogram": "mdi6.chart-histogram",
    "threshold": "mdi6.tune-vertical",
    "morphology": "mdi6.blur",
    "segment": "mdi6.vector-difference",
    # Processing tools are displayed in the dynamically-created final group.
    # Keep explicit names here so they do not fall through to the generic
    # circular placeholder when QtAwesome is unavailable.
    "negative": "mdi6.invert-colors",
    "gamma": "mdi6.tune-vertical",
    "log_transform": "mdi6.chart-line",
    "brightness_contrast": "mdi6.contrast-box",
    "gaussian_blur": "mdi6.blur",
    "median_blur": "mdi6.blur-linear",
    "bilateral_filter": "mdi6.blur-radial",
    "sobel": "mdi6.chart-line",
    "canny": "mdi6.chart-bell-curve",
    "laplacian": "mdi6.chart-line",
    "histogram_equalization": "mdi6.chart-histogram",
    "clahe": "mdi6.chart-histogram",
    "erode": "mdi6.shape-outline",
    "dilate": "mdi6.shape-outline",
    "morph_open": "mdi6.blur",
    "morph_close": "mdi6.blur",
    "grayscale": "mdi6.gradient-horizontal",
    "hue_saturation": "mdi6.palette",
    "layer.add": "fa5s.layer-group",
    "layer.remove": "fa5s.trash-alt",
    "layer.duplicate": "fa5s.clone",
    "layer.up": "fa5s.arrow-up",
    "layer.down": "fa5s.arrow-down",
    "layer.lock": "mdi6.lock-outline",
    "layer.unlock": "mdi6.lock-open-outline",
    "layer.merge": "mdi6.call-merge",
    "layer.group": "mdi6.folder-multiple-outline",
    "layer.ungroup": "mdi6.folder-remove-outline",
    "sidebar": "mdi6.view-sidebar-outline",
    "layer.visible": "mdi6.eye-outline",
    "layer.hidden": "mdi6.eye-off-outline",
    "file.new": "fa5s.file",
    "app": "mdi6.image-edit-outline",
    "command": "fa5s.terminal",
    "undo": "fa5s.undo",
    "redo": "fa5s.redo",
    "zoom.in": "fa5s.search-plus",
    "zoom.out": "fa5s.search-minus",
    "fit": "fa5s.expand",
    "grid": "fa5s.th",
}


def icon_for(
    name: str,
    color: str = "#E8EEF8",
    *,
    prefer_vector: bool = False,
) -> QIcon:
    """Return a local QtAwesome icon, with the built-in vector fallback."""
    if name == "app":
        app_icon = _application_icon()
        if not app_icon.isNull():
            return app_icon
    if prefer_vector:
        return _vector_icon_for(name, color)
    try:
        qtawesome = import_module("qtawesome")
    except ModuleNotFoundError:
        return _vector_icon_for(name, color)
    icon_name = _QTAWESOME_NAMES.get(name)
    if icon_name is None:
        return _vector_icon_for(name, color)
    try:
        return qtawesome.icon(icon_name, color=color)
    except Exception:
        # QtAwesome's installed font set can lag behind its Python package.
        # Keep the UI usable by falling back to the built-in icon.
        return _vector_icon_for(name, color)


def _application_icon() -> QIcon:
    """Load the supplied high-resolution icon in source and frozen builds."""
    if getattr(sys, "frozen", False):
        asset_root = Path(getattr(sys, "_MEIPASS", Path.cwd())) / "dip_studio" / "assets"
    else:
        asset_root = Path(__file__).resolve().parents[1] / "assets"
    return QIcon(str(asset_root / _APP_ICON_NAME))


def _vector_icon_for(name: str, color: str) -> QIcon:
    """Render a local fallback when optional QtAwesome assets are unavailable."""
    painters: dict[str, Callable[[QPainter, QColor], None]] = {
        "select": _select,
        "selection": _selection,
        "ellipse_selection": _selection,
        "lasso": _lasso,
        "polygon_selection": _lasso,
        "color_selection": _gradient,
        "crop": _crop,
        "move": _select,
        "transform": _shape,
        "rotate": _shape,
        "blur": _blur,
        "edge": _edge,
        "gradient": _gradient,
        "brush": _gradient,
        "pencil": _gradient,
        "eraser": _fallback,
        "fill": _gradient,
        "clone": _shape,
        "hand": _hand,
        "zoom": _zoom,
        "eyedropper": _eyedropper,
        "text": _text,
        "shape": _shape,
        "shape_rectangle": _shape,
        "shape_ellipse": _selection,
        "shape_line": _edge,
        "shape_polygon": _lasso,
        "sidebar": _sidebar,
        "histogram": _edge,
        "threshold": _gradient,
        "morphology": _blur,
        "segment": _selection,
        "negative": _gradient,
        "gamma": _gradient,
        "log_transform": _edge,
        "brightness_contrast": _gradient,
        "gaussian_blur": _blur,
        "median_blur": _blur,
        "bilateral_filter": _blur,
        "sobel": _edge,
        "canny": _edge,
        "laplacian": _edge,
        "histogram_equalization": _edge,
        "clahe": _edge,
        "erode": _shape,
        "dilate": _shape,
        "morph_open": _blur,
        "morph_close": _blur,
        "grayscale": _gradient,
        "hue_saturation": _gradient,
        "layer.add": _add,
        "layer.remove": _remove,
        "layer.duplicate": _duplicate,
        "layer.up": _up,
        "layer.down": _down,
        "layer.lock": _lock,
        "layer.unlock": _unlock,
        "layer.merge": _merge,
        "layer.group": _shape,
        "layer.ungroup": _remove,
        "layer.visible": _eye,
        "layer.hidden": _eye_off,
        "file.new": _file,
        "app": _shape,
        "command": _command,
        "undo": _undo,
        "redo": _redo,
        "zoom.in": _zoom_in,
        "zoom.out": _zoom_out,
        "fit": _fit,
        "grid": _grid,
    }
    painter_fn = painters.get(name, _fallback)
    pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter_fn(painter, QColor(color))
    painter.end()
    return QIcon(pixmap)


def _pen(color: QColor, width: float = _STROKE) -> QPen:
    pen = QPen(
        color,
        width * 0.68,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    return pen


def _select(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(c)
    p.drawPolygon(
        QPolygonF(
            (
                QPointF(15, 9),
                QPointF(21, 54),
                QPointF(31, 43),
                QPointF(40, 57),
                QPointF(47, 53),
                QPointF(38, 39),
                QPointF(53, 37),
            )
        )
    )


def _selection(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(13, 15, 38, 34))
    p.setPen(QPen(c, 3, Qt.PenStyle.DashLine))
    p.drawLine(19, 22, 45, 22)


def _lasso(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(18, 43))
    path.cubicTo(8, 24, 23, 10, 40, 15)
    path.cubicTo(57, 20, 52, 42, 35, 47)
    path.cubicTo(25, 50, 18, 45, 18, 43)
    p.drawPath(path)
    p.drawLine(18, 43, 10, 54)
    p.drawEllipse(QPointF(10, 55), 3, 3)


def _crop(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.drawLine(14, 24, 14, 14)
    p.drawLine(14, 14, 24, 14)
    p.drawLine(40, 14, 50, 14)
    p.drawLine(50, 14, 50, 24)
    p.drawLine(14, 40, 14, 50)
    p.drawLine(14, 50, 24, 50)
    p.drawLine(40, 50, 50, 50)
    p.drawLine(50, 50, 50, 40)
    p.drawLine(22, 42, 42, 22)


def _blur(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3))
    for radius, alpha in ((18, 70), (12, 130), (6, 230)):
        fill = QColor(c)
        fill.setAlpha(alpha)
        p.setBrush(fill)
        p.drawEllipse(QPointF(32, 32), radius, radius)


def _edge(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(10, 45))
    path.lineTo(20, 30)
    path.lineTo(28, 39)
    path.lineTo(38, 17)
    path.lineTo(54, 28)
    p.drawPath(path)


def _gradient(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(12, 12, 40, 40), 5, 5)
    for i in range(5):
        alpha = 50 + i * 45
        line = QColor(c)
        line.setAlpha(alpha)
        p.setPen(QPen(line, 6))
        p.drawLine(20 + i * 7, 20, 20 + i * 7, 44)


def _hand(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(21, 31))
    path.lineTo(21, 17)
    path.cubicTo(21, 12, 28, 12, 28, 17)
    path.lineTo(28, 31)
    path.lineTo(28, 13)
    path.cubicTo(28, 8, 35, 9, 35, 14)
    path.lineTo(35, 31)
    path.lineTo(35, 17)
    path.cubicTo(35, 12, 42, 13, 42, 18)
    path.lineTo(42, 34)
    path.lineTo(45, 29)
    path.cubicTo(49, 24, 55, 29, 52, 35)
    path.lineTo(43, 49)
    path.cubicTo(39, 55, 26, 54, 22, 48)
    path.lineTo(15, 38)
    path.cubicTo(12, 33, 18, 29, 21, 31)
    p.drawPath(path)


def _zoom(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(28, 28), 15, 15)
    p.drawLine(39, 39, 53, 53)


def _eyedropper(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.drawLine(17, 49, 45, 21)
    p.drawLine(13, 53, 22, 44)
    p.drawLine(39, 15, 49, 25)
    p.drawLine(43, 12, 52, 21)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(18, 49), 4, 4)


def _text(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.drawLine(15, 15, 49, 15)
    p.drawLine(32, 15, 32, 50)
    p.drawLine(22, 50, 42, 50)


def _shape(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(11, 12, 23, 23))
    p.drawEllipse(QPointF(43, 43), 12, 12)


def _sidebar(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(10, 12, 44, 40))
    p.drawLine(24, 12, 24, 52)
    p.drawLine(30, 22, 48, 22)
    p.drawLine(30, 32, 48, 32)
    p.drawLine(30, 42, 44, 42)


def _add(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.drawLine(32, 12, 32, 52)
    p.drawLine(12, 32, 52, 32)


def _remove(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(18, 19, 28, 34), 3, 3)
    p.drawLine(15, 15, 49, 15)
    p.drawLine(26, 10, 38, 10)
    p.drawLine(27, 27, 27, 45)
    p.drawLine(37, 27, 37, 45)


def _duplicate(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(20, 13, 29, 34), 3, 3)
    p.drawRoundedRect(QRectF(13, 20, 29, 34), 3, 3)


def _up(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.drawLine(32, 51, 32, 14)
    p.drawLine(32, 14, 17, 29)
    p.drawLine(32, 14, 47, 29)


def _down(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.drawLine(32, 13, 32, 50)
    p.drawLine(32, 50, 17, 35)
    p.drawLine(32, 50, 47, 35)


def _fallback(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.drawEllipse(QRectF(14, 14, 36, 36))


def _file(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(16, 10, 32, 44), 3, 3)
    p.drawLine(24, 22, 40, 22)
    p.drawLine(24, 31, 40, 31)
    p.drawLine(24, 40, 35, 40)


def _command(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(11, 14, 42, 36), 5, 5)
    p.drawLine(20, 25, 27, 32)
    p.drawLine(27, 32, 20, 39)
    p.drawLine(33, 40, 44, 40)


def _undo(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(18, 28))
    path.cubicTo(28, 14, 48, 18, 48, 35)
    path.cubicTo(48, 46, 39, 51, 29, 50)
    p.drawPath(path)
    p.drawLine(18, 28, 30, 20)
    p.drawLine(18, 28, 30, 36)


def _redo(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(46, 28))
    path.cubicTo(36, 14, 16, 18, 16, 35)
    path.cubicTo(16, 46, 25, 51, 35, 50)
    p.drawPath(path)
    p.drawLine(46, 28, 34, 20)
    p.drawLine(46, 28, 34, 36)


def _zoom_in(p: QPainter, c: QColor) -> None:
    _zoom(p, c)
    p.setPen(_pen(c, 3))
    p.drawLine(24, 28, 32, 28)
    p.drawLine(28, 24, 28, 32)


def _zoom_out(p: QPainter, c: QColor) -> None:
    _zoom(p, c)
    p.setPen(_pen(c, 3))
    p.drawLine(24, 28, 32, 28)


def _fit(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 4))
    p.drawLine(13, 24, 13, 13)
    p.drawLine(13, 13, 24, 13)
    p.drawLine(40, 13, 51, 13)
    p.drawLine(51, 13, 51, 24)
    p.drawLine(13, 40, 13, 51)
    p.drawLine(13, 51, 24, 51)
    p.drawLine(40, 51, 51, 51)
    p.drawLine(51, 51, 51, 40)


def _grid(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3))
    for x in (17, 32, 47):
        p.drawLine(x, 14, x, 50)
    for y in (14, 32, 50):
        p.drawLine(17, y, 47, y)


def _lock(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Shackle
    path = QPainterPath(QPointF(22, 28))
    path.lineTo(22, 20)
    path.cubicTo(22, 10, 42, 10, 42, 20)
    path.lineTo(42, 28)
    p.drawPath(path)
    # Body
    p.setBrush(c)
    p.drawRoundedRect(QRectF(16, 27, 32, 25), 4, 4)
    # Keyhole
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(DARK.field))
    p.drawEllipse(QPointF(32, 36), 3, 3)
    p.drawRect(QRectF(30.5, 36, 3, 7))


def _unlock(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Open shackle
    path = QPainterPath(QPointF(22, 28))
    path.lineTo(22, 16)
    path.cubicTo(22, 6, 42, 6, 42, 16)
    path.lineTo(42, 20)
    p.drawPath(path)
    # Body
    p.setBrush(c)
    p.drawRoundedRect(QRectF(16, 27, 32, 25), 4, 4)
    # Keyhole
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(DARK.field))
    p.drawEllipse(QPointF(32, 36), 3, 3)
    p.drawRect(QRectF(30.5, 36, 3, 7))


def _merge(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Upper layer
    p.drawRoundedRect(QRectF(14, 11, 36, 14), 3, 3)
    # Lower layer
    p.drawRoundedRect(QRectF(14, 39, 36, 14), 3, 3)
    # Arrow down in center
    p.setPen(_pen(c, 3.5))
    p.drawLine(32, 27, 32, 35)
    p.drawLine(27, 30, 32, 35)
    p.drawLine(37, 30, 32, 35)


def _eye(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 3.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Eye contour
    path = QPainterPath(QPointF(12, 32))
    path.cubicTo(20, 18, 44, 18, 52, 32)
    path.cubicTo(44, 46, 20, 46, 12, 32)
    p.drawPath(path)
    # Pupil
    p.setBrush(c)
    p.drawEllipse(QPointF(32, 32), 6, 6)


def _eye_off(p: QPainter, c: QColor) -> None:
    _eye(p, c)
    p.setPen(_pen(c, 3.5))
    p.drawLine(14, 46, 50, 18)
