"""Theme-aware color swatch widgets and Photoshop-style dual color picker."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ColorSwatchButton(QPushButton):
    """Clickable color preview swatch button opening a QColorDialog."""

    colorChanged = Signal(QColor)

    def __init__(
        self,
        color: QColor | tuple[int, int, int, int] = (0, 0, 0, 255),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(*color) if isinstance(color, tuple) else QColor(color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._open_color_dialog)
        self.setFixedSize(28, 28)

    @property
    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor | tuple[int, int, int, int], emit: bool = True) -> None:
        new_color = QColor(*color) if isinstance(color, tuple) else QColor(color)
        if new_color != self._color:
            self._color = new_color
            self.update()
            if emit:
                self.colorChanged.emit(self._color)

    def _open_color_dialog(self) -> None:
        dialog = QColorDialog(self._color, self)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            self.set_color(dialog.currentColor())

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)

        # Draw checkerboard background for alpha transparency visual
        if self._color.alpha() < 255:
            painter.fillRect(rect, Qt.GlobalColor.white)
            half_w = rect.width() // 2
            half_h = rect.height() // 2
            painter.fillRect(rect.left(), rect.top(), half_w, half_h, Qt.GlobalColor.lightGray)
            painter.fillRect(rect.left() + half_w, rect.top() + half_h, half_w, half_h, Qt.GlobalColor.lightGray)

        # Fill color rectangle
        painter.fillRect(rect, self._color)

        # Border outline
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawRect(rect)


class DualColorSwatchWidget(QWidget):
    """Photoshop-style Foreground / Background dual overlapping color swatches.

    Features:
    - Foreground color swatch (top-left)
    - Background color swatch (bottom-right)
    - Swap colors button (⇄)
    - Default colors button (D: Black FG, White BG)
    """

    foregroundColorChanged = Signal(tuple)  # (r, g, b, a)
    backgroundColorChanged = Signal(tuple)  # (r, g, b, a)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dualColorSwatch")
        self.setFixedSize(50, 50)

        self._fg_color = QColor(0, 0, 0, 255)       # Default Black
        self._bg_color = QColor(255, 255, 255, 255) # Default White

        self._fg_button = ColorSwatchButton(self._fg_color, self)
        self._fg_button.setToolTip("Foreground color (Click to change)")
        self._fg_button.move(4, 4)
        self._fg_button.raise_()

        self._bg_button = ColorSwatchButton(self._bg_color, self)
        self._bg_button.setToolTip("Background color (Click to change)")
        self._bg_button.move(18, 18)
        self._fg_button.raise_()

        # Swap button (⇄)
        self._swap_btn = QToolButton(self)
        self._swap_btn.setText("⇄")
        self._swap_btn.setToolTip("Swap Foreground/Background colors (X)")
        self._swap_btn.setFixedSize(14, 14)
        self._swap_btn.move(32, 2)
        self._swap_btn.clicked.connect(self.swap_colors)

        # Reset button (D)
        self._reset_btn = QToolButton(self)
        self._reset_btn.setText("D")
        self._reset_btn.setToolTip("Reset to default colors (Black/White)")
        self._reset_btn.setFixedSize(14, 14)
        self._reset_btn.move(2, 32)
        self._reset_btn.clicked.connect(self.reset_default_colors)

        self._fg_button.colorChanged.connect(self._on_fg_changed)
        self._bg_button.colorChanged.connect(self._on_bg_changed)

    @property
    def foreground_rgba(self) -> tuple[int, int, int, int]:
        return (self._fg_color.red(), self._fg_color.green(), self._fg_color.blue(), self._fg_color.alpha())

    @property
    def background_rgba(self) -> tuple[int, int, int, int]:
        return (self._bg_color.red(), self._bg_color.green(), self._bg_color.blue(), self._bg_color.alpha())

    def set_foreground_color(self, color: QColor | tuple[int, int, int, int]) -> None:
        self._fg_button.set_color(color)

    def set_background_color(self, color: QColor | tuple[int, int, int, int]) -> None:
        self._bg_button.set_color(color)

    def swap_colors(self) -> None:
        old_fg = self._fg_color
        old_bg = self._bg_color
        self._fg_button.set_color(old_bg, emit=False)
        self._bg_button.set_color(old_fg, emit=False)
        self._fg_color = old_bg
        self._bg_color = old_fg
        self.foregroundColorChanged.emit(self.foreground_rgba)
        self.backgroundColorChanged.emit(self.background_rgba)

    def reset_default_colors(self) -> None:
        self.set_foreground_color((0, 0, 0, 255))
        self.set_background_color((255, 255, 255, 255))

    def _on_fg_changed(self, color: QColor) -> None:
        self._fg_color = color
        self.foregroundColorChanged.emit(self.foreground_rgba)

    def _on_bg_changed(self, color: QColor) -> None:
        self._bg_color = color
        self.backgroundColorChanged.emit(self.background_rgba)
