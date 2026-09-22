"""Interactive canvas preview widget for the editor presentation layer."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget


class CanvasView(QWidget):
    """Interactive preview surface: zoom, pan, space-drag, tool-event dispatch."""

    # Emitted on every mouse press/move/release: (event_type, event)
    # event_type = "press" | "move" | "release"
    toolMouseEvent = Signal(str, object)
    cropCommitted = Signal()
    cropRectChanged = Signal(object)
    selectionCleared = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(320, 240)
        self.setObjectName("canvas")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)  # receive move events without button held
        self._source_image: QImage | None = None
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._grid_enabled = False
        self._show_before = False
        self._pan = QPoint()
        self._drag_start: QPoint | None = None
        self._space_pan = False
        self._selection_rect: QRect | None = None
        self._selection_points: tuple[QPoint, ...] = ()
        self._is_crop_mode = False
        self._crop_handle: str | None = None
        self._crop_drag_origin: QPoint | None = None
        self._active_layer_rect: tuple[int, int, int, int, int, int] | None = None
        self._active_layer_rects: tuple[tuple[int, int, int, int, int, int], ...] = ()
        self._active_layer_name: str = ""
        # Optional Python callback: callback(event_type, event)
        self._tool_callback: Callable[[str, QMouseEvent], None] | None = None

    def set_active_layer_rect(
        self, x: int, y: int, width: int, height: int, name: str = "", doc_w: int = 1, doc_h: int = 1
    ) -> None:
        """Set the active layer's document-space bounding box for on-canvas highlighting."""
        self._active_layer_rect = (x, y, width, height, doc_w, doc_h)
        self._active_layer_rects = (self._active_layer_rect,)
        self._active_layer_name = name
        self.update()

    def clear_active_layer_rect(self) -> None:
        """Clear active layer highlight overlay."""
        self._active_layer_rect = None
        self._active_layer_rects = ()
        self._active_layer_name = ""
        self.update()

    def set_active_layer_rects(
        self,
        rects: tuple[tuple[int, int, int, int], ...],
        doc_w: int,
        doc_h: int,
    ) -> None:
        self._active_layer_rects = tuple(
            (*rect, doc_w, doc_h) for rect in rects
        )
        self._active_layer_rect = (
            self._active_layer_rects[0] if self._active_layer_rects else None
        )
        self.update()

    def active_layer_handle_at(self, pos: QPoint) -> str | None:
        """Return the resize handle under a widget-space point, if any."""
        if self._active_layer_rect is None:
            return None
        x, y, width, height, doc_w, doc_h = self._active_layer_rect
        image_rect = self._image_display_rect()
        sx = image_rect.width() / max(1, doc_w)
        sy = image_rect.height() / max(1, doc_h)
        rect = QRect(
            image_rect.left() + round(x * sx),
            image_rect.top() + round(y * sy),
            max(2, round(width * sx)),
            max(2, round(height * sy)),
        )
        handles = {
            "top_left": rect.topLeft(),
            "top_right": rect.topRight(),
            "bottom_left": rect.bottomLeft(),
            "bottom_right": rect.bottomRight(),
            "top": QPoint(rect.center().x(), rect.top()),
            "bottom": QPoint(rect.center().x(), rect.bottom()),
            "left": QPoint(rect.left(), rect.center().y()),
            "right": QPoint(rect.right(), rect.center().y()),
        }
        for name, center in handles.items():
            if QRect(center.x() - 7, center.y() - 7, 14, 14).contains(pos):
                return name
        return None

    def set_crop_mode(self, enabled: bool) -> None:
        """Activate or deactivate interactive Photoshop-style crop mode."""
        self._is_crop_mode = enabled
        if enabled:
            self.init_crop_rect()
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._selection_rect = None
            self._crop_handle = None
        self.update()

    def init_crop_rect(self) -> None:
        """Initialize the crop box to cover the entire current image display rect."""
        img_rect = self._image_display_rect()
        if img_rect is not None:
            self._selection_rect = QRect(img_rect)
            self.cropRectChanged.emit(self._selection_rect)
            self.update()

    def set_selection_rect(self, rect: QRect | None, kind: str = "rectangle") -> None:
        """Set or clear the on-canvas visual selection / crop rectangle."""
        self._selection_rect = rect
        self._selection_kind = kind
        if rect is None:
            self._selection_points = ()
        self.update()

    def set_selection_points(
        self, points: tuple[QPoint, ...], kind: str = "lasso"
    ) -> None:
        """Show a freehand or polygon selection path while it is being drawn."""
        self._selection_points = points
        self._selection_kind = kind
        if points:
            xs = [point.x() for point in points]
            ys = [point.y() for point in points]
            self._selection_rect = QRect(
                min(xs),
                min(ys),
                max(1, max(xs) - min(xs)),
                max(1, max(ys) - min(ys)),
            )
        else:
            self._selection_rect = None
        self.update()

    @staticmethod
    def compute_constrained_rect(
        origin: QPoint, current: QPoint, shift: bool = False, alt: bool = False
    ) -> QRect:
        """Calculate rect respecting Shift (1:1 aspect ratio) and Alt (center origin) modifiers."""
        dx = current.x() - origin.x()
        dy = current.y() - origin.y()

        if shift:
            side = max(abs(dx), abs(dy))
            dx = side if dx >= 0 else -side
            dy = side if dy >= 0 else -side

        if alt:
            left = origin.x() - abs(dx)
            top = origin.y() - abs(dy)
            width = max(1, 2 * abs(dx))
            height = max(1, 2 * abs(dy))
            return QRect(left, top, width, height)
        else:
            return QRect(origin, QPoint(origin.x() + dx, origin.y() + dy)).normalized()

    def set_crop_rect_from_image(
        self, x: int, y: int, width: int, height: int, image_width: int, image_height: int
    ) -> None:
        """Set the crop frame from document-space coordinates."""
        image_rect = self._image_display_rect()
        if image_rect is None:
            return
        scale_x = image_rect.width() / max(1, image_width)
        scale_y = image_rect.height() / max(1, image_height)
        rect = QRect(
            round(image_rect.left() + x * scale_x),
            round(image_rect.top() + y * scale_y),
            max(1, round(width * scale_x)),
            max(1, round(height * scale_y)),
        )
        self._selection_rect = rect.intersected(image_rect)
        self.cropRectChanged.emit(self._selection_rect)
        self.update()

    def current_selection_image_rect(
        self, img_w: int, img_h: int
    ) -> tuple[int, int, int, int] | None:
        """Return image-space (x, y, w, h) for current selection rect, if active."""
        image_rect = self._image_display_rect()
        if (
            image_rect is None
            or self._selection_rect is None
            or self._selection_rect.isNull()
        ):
            return None
        rect = self._selection_rect.normalized().intersected(image_rect)
        scale_x = img_w / max(1, image_rect.width())
        scale_y = img_h / max(1, image_rect.height())
        x1 = int((rect.left() - image_rect.left()) * scale_x)
        y1 = int((rect.top() - image_rect.top()) * scale_y)
        x2 = int((rect.right() - image_rect.left() + 1) * scale_x + 0.999999)
        y2 = int((rect.bottom() - image_rect.top() + 1) * scale_y + 0.999999)
        x1 = max(0, min(x1, img_w - 1))
        y1 = max(0, min(y1, img_h - 1))
        x2 = max(x1 + 1, min(x2, img_w))
        y2 = max(y1 + 1, min(y2, img_h))
        w = x2 - x1
        h = y2 - y1
        return (x1, y1, w, h)

    def _image_display_rect(self) -> QRect | None:
        if self._pixmap is None:
            return None
        # QPixmap stores device pixels after setDevicePixelRatio(). Mouse
        # events and QWidget geometry are in logical pixels. Using
        # pixmap.width() here therefore doubled the display size/offset on
        # high-DPI displays and broke every widget-to-image conversion.
        logical_size = self._pixmap.deviceIndependentSize()
        width = max(1, round(logical_size.width()))
        height = max(1, round(logical_size.height()))
        px_x = (self.width() - width) // 2 + self._pan.x()
        px_y = (self.height() - height) // 2 + self._pan.y()
        return QRect(px_x, px_y, width, height)

    def _hit_crop_handle(self, pos: QPoint) -> str | None:
        if self._selection_rect is None or self._selection_rect.isNull():
            return None
        rect = self._selection_rect.normalized()
        margin = 16
        # Handles are hit-tested inward from the boundary so the right and
        # bottom handles remain usable when the crop frame touches the widget
        # edge.
        left = rect.left()
        right = rect.right()
        top = rect.top()
        bottom = rect.bottom()
        near_left = abs(pos.x() - left) <= margin or left <= pos.x() <= left + margin
        near_right = abs(pos.x() - right) <= margin or right - margin <= pos.x() <= right
        near_top = abs(pos.y() - top) <= margin or top <= pos.y() <= top + margin
        near_bottom = abs(pos.y() - bottom) <= margin or bottom - margin <= pos.y() <= bottom
        near_x = left - margin <= pos.x() <= right + margin
        near_y = top - margin <= pos.y() <= bottom + margin

        if near_left and near_top:
            return "tl"
        if near_right and near_top:
            return "tr"
        if near_left and near_bottom:
            return "bl"
        if near_right and near_bottom:
            return "br"
        # Edges
        if near_top and near_x:
            return "top"
        if near_bottom and near_x:
            return "bottom"
        if near_left and near_y:
            return "left"
        if near_right and near_y:
            return "right"
        if rect.contains(pos):
            return "inside"
        return None

    def _update_crop_cursor(self, pos: QPoint) -> None:
        handle = self._hit_crop_handle(pos)
        if handle in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in ("top", "bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle == "inside":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _apply_crop_handle_drag(self, pos: QPoint) -> None:
        if self._crop_rect_start is None or self._crop_drag_origin is None:
            return
        img_rect = self._image_display_rect()
        if img_rect is None:
            return
        diff = pos - self._crop_drag_origin
        r = QRect(self._crop_rect_start)

        if self._crop_handle == "inside":
            new_x = max(img_rect.left(), min(img_rect.right() - r.width(), r.left() + diff.x()))
            new_y = max(img_rect.top(), min(img_rect.bottom() - r.height(), r.top() + diff.y()))
            r.moveTo(new_x, new_y)
        elif self._crop_handle == "tl":
            new_l = max(img_rect.left(), min(r.right() - 10, r.left() + diff.x()))
            new_t = max(img_rect.top(), min(r.bottom() - 10, r.top() + diff.y()))
            r.setLeft(new_l)
            r.setTop(new_t)
        elif self._crop_handle == "tr":
            new_r = min(img_rect.right(), max(r.left() + 10, r.right() + diff.x()))
            new_t = max(img_rect.top(), min(r.bottom() - 10, r.top() + diff.y()))
            r.setRight(new_r)
            r.setTop(new_t)
        elif self._crop_handle == "bl":
            new_l = max(img_rect.left(), min(r.right() - 10, r.left() + diff.x()))
            new_b = min(img_rect.bottom(), max(r.top() + 10, r.bottom() + diff.y()))
            r.setLeft(new_l)
            r.setBottom(new_b)
        elif self._crop_handle == "br":
            new_r = min(img_rect.right(), max(r.left() + 10, r.right() + diff.x()))
            new_b = min(img_rect.bottom(), max(r.top() + 10, r.bottom() + diff.y()))
            r.setRight(new_r)
            r.setBottom(new_b)
        elif self._crop_handle == "top":
            new_t = max(img_rect.top(), min(r.bottom() - 10, r.top() + diff.y()))
            r.setTop(new_t)
        elif self._crop_handle == "bottom":
            new_b = min(img_rect.bottom(), max(r.top() + 10, r.bottom() + diff.y()))
            r.setBottom(new_b)
        elif self._crop_handle == "left":
            new_l = max(img_rect.left(), min(r.right() - 10, r.left() + diff.x()))
            r.setLeft(new_l)
        elif self._crop_handle == "right":
            new_r = min(img_rect.right(), max(r.left() + 10, r.right() + diff.x()))
            r.setRight(new_r)
        elif self._crop_handle == "new":
            clamped_x = max(img_rect.left(), min(img_rect.right(), pos.x()))
            clamped_y = max(img_rect.top(), min(img_rect.bottom(), pos.y()))
            r = QRect(self._crop_drag_origin, QPoint(clamped_x, clamped_y)).normalized()

        self._selection_rect = r.normalized()
        self.cropRectChanged.emit(self._selection_rect)
        self.update()

    def set_active_tool_callback(
        self, callback: Callable[[str, QMouseEvent], None] | None
    ) -> None:
        """Register a callback for tool-specific mouse events.

        The callback receives (event_type: str, event: QMouseEvent) where
        event_type is one of ``"press"``, ``"move"``, ``"release"``.
        """
        self._tool_callback = callback

    def widget_to_image_pos(self, widget_pos: QPoint, img_w: int, img_h: int) -> tuple[int, int]:
        """Convert a widget pixel position to image pixel coordinates.

        Accounts for the current zoom level and canvas pan offset.
        """
        if self._pixmap is None or img_w == 0 or img_h == 0:
            return (0, 0)
        # Offset of the top-left corner of the pixmap inside the widget
        image_rect = self._image_display_rect()
        if image_rect is None:
            return (0, 0)
        px_x = image_rect.left()
        px_y = image_rect.top()
        # Relative position inside the pixmap
        rel_x = widget_pos.x() - px_x
        rel_y = widget_pos.y() - px_y
        # Scale from pixmap to image coordinates
        scale_x = img_w / max(1, image_rect.width())
        scale_y = img_h / max(1, image_rect.height())
        ix = int(rel_x * scale_x)
        iy = int(rel_y * scale_y)
        ix = max(0, min(ix, img_w - 1))
        iy = max(0, min(iy, img_h - 1))
        return (ix, iy)

    def image_to_widget_pos(self, x: int, y: int, img_w: int, img_h: int) -> QPoint:
        """Convert document-space coordinates to widget-space coordinates."""
        image_rect = self._image_display_rect()
        if image_rect is None:
            return QPoint()
        scale_x = image_rect.width() / max(1, img_w)
        scale_y = image_rect.height() / max(1, img_h)
        return QPoint(
            round(image_rect.left() + x * scale_x),
            round(image_rect.top() + y * scale_y),
        )

    def show_preview(self, data: bytes) -> None:
        image = QImage()
        if not image.loadFromData(data):
            raise ValueError("Renderer returned an invalid preview frame")
        self._source_image = image
        self._render_zoomed()

    def set_preview_array(self, arr: "np.ndarray") -> None:
        """Update the canvas from an RGBA uint8 NumPy array without encoding.

        The input is normalized to a contiguous ``(H, W, 4)`` ``uint8`` array
        before creating a ``QImage``. We explicitly convert and validate the
        buffer to avoid Qt holding a dangling pointer into a temporary view.
        """
        import numpy as np
        from PySide6.QtGui import QImage

        if not isinstance(arr, np.ndarray):
            raise TypeError("Preview array must be a NumPy array")

        arr = np.asarray(arr)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.full_like(arr, 255, dtype=np.uint8)], axis=-1)
        elif arr.ndim != 3:
            raise ValueError("Preview array must be 2D or 3D with shape (H, W) or (H, W, C)")

        if arr.shape[-1] == 3:
            alpha = np.full((*arr.shape[:2], 1), 255, dtype=np.uint8)
            arr = np.concatenate([arr, alpha], axis=-1)
        elif arr.shape[-1] != 4:
            raise ValueError("Preview array must have 3 or 4 channels; got shape %s" % (arr.shape,))

        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8, copy=False)

        arr_c = np.ascontiguousarray(arr, dtype=np.uint8)
        h, w, channels = arr_c.shape
        if channels != 4:
            raise ValueError("Preview array must be contiguous RGBA with shape (H, W, 4)")

        stride = arr_c.strides[0]
        if stride <= 0 or stride < w * 4:
            raise ValueError("Preview array is not a valid contiguous RGBA buffer")

        try:
            qimg = QImage(arr_c.data, w, h, stride, QImage.Format.Format_RGBA8888)
        except Exception as exc:  # pragma: no cover - Qt raises only for invalid buffer metadata.
            raise ValueError("Preview array could not be converted to a QImage") from exc

        self._source_image = qimg.copy()
        self._render_zoomed()

    def clear_preview(self) -> None:
        self._source_image = None
        self._pixmap = None
        self._pan = QPoint()
        self.update()

    def set_grid_enabled(self, enabled: bool) -> None:
        self._grid_enabled = enabled
        self.update()

    def set_before_after(self, show_before: bool) -> None:
        self._show_before = show_before
        self.update()

    # ──────────────────────────── mouse events ──────────────────────────────

    def mousePressEvent(self, event: Any) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if (
            self._is_crop_mode
            and not self._space_pan
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = event.position().toPoint()
            handle = self._hit_crop_handle(pos)
            self._crop_handle = handle or "new"
            self._crop_drag_origin = pos
            self._crop_rect_start = QRect(self._selection_rect) if self._selection_rect else QRect(pos, pos)
            if self._crop_handle == "new":
                self._selection_rect = QRect(pos, pos)
                self.update()
            event.accept()
            return

        # Dispatch to registered tool callback first
        if self._tool_callback is not None and not self._space_pan:
            self._tool_callback("press", event)
        self.toolMouseEvent.emit("press", event)

        if event.button() == Qt.MouseButton.LeftButton and self._space_pan:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self._is_crop_mode and not self._space_pan:
            pos = event.position().toPoint()
            if event.buttons() & Qt.MouseButton.LeftButton and self._crop_drag_origin is not None:
                self._apply_crop_handle_drag(pos)
                event.accept()
                return
            else:
                self._update_crop_cursor(pos)

        # Dispatch to registered tool callback
        if self._tool_callback is not None:
            self._tool_callback("move", event)
        self.toolMouseEvent.emit("move", event)

        if self._drag_start is not None:
            current = event.position().toPoint()
            self._pan += current - self._drag_start
            self._drag_start = current
            self._clamp_pan()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if self._is_crop_mode:
            self._crop_handle = None
            self._crop_drag_origin = None
            self._crop_rect_start = None
            self._update_crop_cursor(event.position().toPoint())

        # Dispatch to registered tool callback
        if self._tool_callback is not None and not self._space_pan:
            self._tool_callback("release", event)
        self.toolMouseEvent.emit("release", event)

        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            if self._space_pan:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if self._is_crop_mode and self._selection_rect is not None:
            if self._selection_rect.contains(event.position().toPoint()):
                self.cropCommitted.emit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_in()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoom_out()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if (
                self._is_crop_mode
                and self._selection_rect is not None
                and not self._selection_rect.isNull()
            ):
                self.cropCommitted.emit()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape:
            if self._selection_rect is not None:
                self.set_selection_rect(None)
                self.selectionCleared.emit()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def wheelEvent(self, event: Any) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    # ──────────────────────────── zoom / pan ──────────────────────────────

    @property
    def zoom(self) -> float:
        return self._zoom

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    def fit_to_view(self) -> None:
        if self._source_image is None:
            return
        width_ratio = max(0.1, (self.width() - 24) / self._source_image.width())
        height_ratio = max(0.1, (self.height() - 24) / self._source_image.height())
        self.set_zoom(min(width_ratio, height_ratio))

    def set_zoom(self, zoom: float) -> None:
        self._zoom = min(8.0, max(0.1, zoom))
        self._clamp_pan()
        self._render_zoomed()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if self._source_image is not None:
            self._render_zoomed()

    # ──────────────────────────── internal ──────────────────────────────

    def _render_zoomed(self) -> None:
        if self._source_image is None:
            return
        dpr = self.devicePixelRatioF()
        target_w = max(1, round(self._source_image.width() * self._zoom * dpr))
        target_h = max(1, round(self._source_image.height() * self._zoom * dpr))
        scaled_img = self._source_image.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap = QPixmap.fromImage(scaled_img)
        pixmap.setDevicePixelRatio(dpr)
        self._pixmap = pixmap
        self._clamp_pan()
        self.update()

    def _clamp_pan(self) -> None:
        if self._pixmap is None:
            self._pan = QPoint()
            return
        image_rect = self._image_display_rect()
        if image_rect is None:
            self._pan = QPoint()
            return
        max_x = max(0, (image_rect.width() - self.width()) // 2)
        max_y = max(0, (image_rect.height() - self.height()) // 2)
        self._pan.setX(max(-max_x, min(max_x, self._pan.x())))
        self._pan.setY(max(-max_y, min(max_y, self._pan.y())))

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.darkGray)
        if self._grid_enabled:
            painter.setPen(Qt.GlobalColor.gray)
            for x in range(0, self.width(), 16):
                painter.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), 16):
                painter.drawLine(0, y, self.width(), y)
        if self._pixmap is None:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Create a document to start",
            )
            return
        img_rect = self._image_display_rect()
        if img_rect is None:
            return
        if self._show_before:
            painter.setOpacity(0.45)
        painter.drawPixmap(img_rect.topLeft(), self._pixmap)

        if self._selection_rect is not None and not self._selection_rect.isNull():
            if self._is_crop_mode:
                c_rect = self._selection_rect.normalized().intersected(img_rect)
                if not c_rect.isEmpty():
                    # 1. Darkened Photoshop Shield outside crop box
                    shield_color = QColor(0, 0, 0, 160)
                    if c_rect.top() > img_rect.top():
                        painter.fillRect(QRect(img_rect.left(), img_rect.top(), img_rect.width(), c_rect.top() - img_rect.top()), shield_color)
                    if c_rect.bottom() < img_rect.bottom():
                        painter.fillRect(QRect(img_rect.left(), c_rect.bottom() + 1, img_rect.width(), img_rect.bottom() - c_rect.bottom()), shield_color)
                    if c_rect.left() > img_rect.left():
                        painter.fillRect(QRect(img_rect.left(), c_rect.top(), c_rect.left() - img_rect.left(), c_rect.height()), shield_color)
                    if c_rect.right() < img_rect.right():
                        painter.fillRect(QRect(c_rect.right() + 1, c_rect.top(), img_rect.right() - c_rect.right(), c_rect.height()), shield_color)

                    # 2. Rule of thirds grid lines
                    grid_pen = QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine)
                    painter.setPen(grid_pen)
                    gx1 = c_rect.left() + c_rect.width() / 3.0
                    gx2 = c_rect.left() + 2.0 * c_rect.width() / 3.0
                    gy1 = c_rect.top() + c_rect.height() / 3.0
                    gy2 = c_rect.top() + 2.0 * c_rect.height() / 3.0
                    painter.drawLine(int(gx1), c_rect.top(), int(gx1), c_rect.bottom())
                    painter.drawLine(int(gx2), c_rect.top(), int(gx2), c_rect.bottom())
                    painter.drawLine(c_rect.left(), int(gy1), c_rect.right(), int(gy1))
                    painter.drawLine(c_rect.left(), int(gy2), c_rect.right(), int(gy2))

                    # 3. Crop boundary border
                    painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5, Qt.PenStyle.SolidLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(c_rect)

                    # 4. Photoshop handles (thick corner Ls & edge marks)
                    h_pen = QPen(QColor(255, 255, 255, 255), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
                    painter.setPen(h_pen)
                    hl = 14
                    cl = max(0, c_rect.left())
                    cr = min(self.width() - 2, c_rect.right())
                    ct = max(0, c_rect.top())
                    cb = min(self.height() - 2, c_rect.bottom())
                    cx = c_rect.center().x()
                    cy = c_rect.center().y()
                    # Corners
                    painter.drawLine(cl, ct, cl + hl, ct)
                    painter.drawLine(cl, ct, cl, ct + hl)
                    painter.drawLine(cr - hl, ct, cr, ct)
                    painter.drawLine(cr, ct, cr, ct + hl)
                    painter.drawLine(cl, cb, cl + hl, cb)
                    painter.drawLine(cl, cb - hl, cl, cb)
                    painter.drawLine(cr - hl, cb, cr, cb)
                    painter.drawLine(cr, cb - hl, cr, cb)
                    # Edge centers
                    painter.drawLine(cx - 7, ct, cx + 7, ct)
                    painter.drawLine(cx - 7, cb, cx + 7, cb)
                    painter.drawLine(cl, cy - 7, cl, cy + 7)
                    painter.drawLine(cr, cy - 7, cr, cy + 7)
            else:
                # Selection marquee rendering based on kind
                pen = QPen(QColor(0, 150, 255), 1.5, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(QColor(0, 150, 255, 40))
                kind = getattr(self, "_selection_kind", "rectangle")
                if kind == "ellipse":
                    painter.drawEllipse(self._selection_rect)
                elif kind == "line":
                    painter.drawLine(
                        self._selection_rect.topLeft(),
                        self._selection_rect.bottomRight(),
                    )
                elif kind in {"lasso", "polygon"} and len(self._selection_points) >= 2:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPolyline(QPolygonF(self._selection_points))
                    if kind == "polygon" and len(self._selection_points) >= 3:
                        painter.drawLine(
                            self._selection_points[-1],
                            self._selection_points[0],
                        )
                else:
                    painter.drawRect(self._selection_rect)

        if (
            self._active_layer_rects
            and not self._is_crop_mode
        ):
            border_pen = QPen(QColor(0, 122, 255, 230), 1.5, Qt.PenStyle.SolidLine)
            painter.setPen(border_pen)
            painter.setBrush(QColor(0, 122, 255, 20))
            for lx, ly, lw, lh, doc_w, doc_h in self._active_layer_rects:
                scale_x = img_rect.width() / max(1, doc_w)
                scale_y = img_rect.height() / max(1, doc_h)
                l_rect = QRect(
                    img_rect.left() + round(lx * scale_x),
                    img_rect.top() + round(ly * scale_y),
                    max(2, round(lw * scale_x)),
                    max(2, round(lh * scale_y)),
                )
                painter.drawRect(l_rect)

            # Resize handles belong to the primary selected layer only.
            lx, ly, lw, lh, doc_w, doc_h = self._active_layer_rects[0]
            scale_x = img_rect.width() / max(1, doc_w)
            scale_y = img_rect.height() / max(1, doc_h)
            l_rect = QRect(
                img_rect.left() + round(lx * scale_x),
                img_rect.top() + round(ly * scale_y),
                max(2, round(lw * scale_x)),
                max(2, round(lh * scale_y)),
            )
            handle_size = 6
            h_half = handle_size // 2
            h_positions = [
                l_rect.topLeft(),
                l_rect.topRight(),
                l_rect.bottomLeft(),
                l_rect.bottomRight(),
                QPoint(l_rect.center().x(), l_rect.top()),
                QPoint(l_rect.center().x(), l_rect.bottom()),
                QPoint(l_rect.left(), l_rect.center().y()),
                QPoint(l_rect.right(), l_rect.center().y()),
            ]
            h_pen = QPen(QColor(0, 122, 255, 255), 1.5)
            h_brush = QColor(255, 255, 255, 255)
            painter.setPen(h_pen)
            painter.setBrush(h_brush)
            for pt in h_positions:
                painter.drawRect(
                    QRect(pt.x() - h_half, pt.y() - h_half, handle_size, handle_size)
                )

            if self._active_layer_name:
                badge_text = f" {self._active_layer_name} "
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(badge_text) + 8
                th = fm.height() + 4
                badge_rect = QRect(l_rect.left(), max(0, l_rect.top() - th - 2), tw, th)
                painter.fillRect(badge_rect, QColor(0, 122, 255, 220))
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
