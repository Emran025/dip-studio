"""Interactive canvas preview widget for the editor presentation layer."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class CanvasView(QWidget):
    """Read-only preview surface fed by rendered bytes."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(320, 240)
        self.setObjectName("canvas")
        self._source_image: QImage | None = None
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._grid_enabled = False
        self._show_before = False
        self._pan = QPoint()
        self._drag_start: QPoint | None = None
        self._space_pan = False

    def show_preview(self, data: bytes) -> None:
        image = QImage()
        if not image.loadFromData(data, "PPM"):
            raise ValueError("Renderer returned an invalid preview frame")
        self._source_image = image
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

    def mousePressEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton and (
            self._space_pan or event.button() == Qt.MouseButton.LeftButton
        ):
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        if self._drag_start is not None:
            current = event.position().toPoint()
            self._pan += current - self._drag_start
            self._drag_start = current
            self._clamp_pan()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: object) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: object) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def wheelEvent(self, event: object) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

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

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if self._source_image is not None:
            self._render_zoomed()

    def _render_zoomed(self) -> None:
        if self._source_image is None:
            return
        size = self._source_image.size()
        size.setWidth(max(1, round(size.width() * self._zoom)))
        size.setHeight(max(1, round(size.height() * self._zoom)))
        pixmap = QPixmap.fromImage(self._source_image).scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._pixmap = pixmap
        self._clamp_pan()
        self.update()

    def _clamp_pan(self) -> None:
        if self._pixmap is None:
            self._pan = QPoint()
            return
        max_x = max(0, (self._pixmap.width() - self.width()) // 2)
        max_y = max(0, (self._pixmap.height() - self.height()) // 2)
        self._pan.setX(max(-max_x, min(max_x, self._pan.x())))
        self._pan.setY(max(-max_y, min(max_y, self._pan.y())))

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
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
        x = (self.width() - self._pixmap.width()) // 2 + self._pan.x()
        y = (self.height() - self._pixmap.height()) // 2 + self._pan.y()
        if self._show_before:
            painter.setOpacity(0.45)
        painter.drawPixmap(x, y, self._pixmap)
