"""Adobe-style dock grip embedded at the top of each panel."""

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class DockPanel(QWidget):
    """Panel content with a small draggable grip and no visible title."""

    def __init__(
        self,
        dock: QWidget,
        content: QWidget,
        main_window: QWidget,
        panel_group: object | None = None,
        panel_name: str | None = None,
    ) -> None:
        super().__init__()
        self._dock = dock
        self._main_window = main_window
        self._panel_group = panel_group
        self._panel_name = panel_name
        self._drag_start: QPoint | None = None
        self._drag_offset = QPoint()
        self._dragging = False
        self._collapsed = False
        self._grip: QLabel | None = None
        self.setObjectName("dockPanel")

        header = QWidget(self)
        header.setObjectName("dockPanelHeader")
        header.setFixedHeight(16)
        header.setCursor(Qt.CursorShape.SizeAllCursor)
        header.installEventFilter(self)
        self._header = header

        grip = QLabel("......", header)
        grip.setObjectName("dockGrip")
        grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grip.setFixedSize(QSize(38, 16))
        grip.installEventFilter(self)
        self._grip = grip
        self._content = content

        collapse_button = QToolButton(header)
        collapse_button.setObjectName("dockCollapseButton")
        collapse_button.setText("»")
        collapse_button.setToolTip("Collapse panel")
        collapse_button.setAutoRaise(True)
        collapse_button.setFixedSize(QSize(16, 16))
        collapse_button.clicked.connect(self._toggle_collapsed)
        self._collapse_button = collapse_button

        close_button = QToolButton(header)
        close_button.setObjectName("dockCloseButton")
        close_button.setText("x")
        close_button.setToolTip("Close floating panel")
        close_button.setAutoRaise(True)
        close_button.setFixedSize(QSize(16, 16))
        close_button.clicked.connect(self._dock.close)
        close_button.hide()
        self._close_button = close_button

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(1)
        header_layout.addWidget(collapse_button)
        header_layout.addWidget(grip)
        header_layout.addStretch(1)
        header_layout.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(content)

        dock.topLevelChanged.connect(self._update_floating_controls)
        self._drop_indicator = QFrame(main_window)
        self._drop_indicator.setObjectName("dockDropIndicator")
        self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drop_indicator.hide()
        self._drop_preview_visible = False
        self._update_floating_controls(dock.isFloating())

    def _update_floating_controls(self, floating: bool) -> None:
        self._close_button.setVisible(floating)

    def _toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._collapse_button.setText("«" if self._collapsed else "»")
        self._collapse_button.setToolTip("Expand panel" if self._collapsed else "Collapse panel")

    def eventFilter(self, watched: object, event: object) -> bool:
        if watched not in (self._header, self._grip) or not isinstance(event, QMouseEvent):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = event.globalPosition().toPoint()
                self._drag_offset = self._drag_start - self._dock.mapToGlobal(QPoint(0, 0))
                self._dragging = False
            return True
        if event.type() == QEvent.Type.MouseMove and self._drag_start is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                current = event.globalPosition().toPoint()
                if (current - self._drag_start).manhattanLength() >= 4:
                    self._dragging = True
                    self._dock.setFloating(True)
                    self._dock.move(current - self._drag_offset)
                    self._update_drop_preview(current)
                    return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            if self._dragging and self._dock.isFloating():
                self._redock_if_dropped_on_workspace(event.globalPosition().toPoint())
            self._drop_indicator.hide()
            self._drag_start = None
            self._dragging = False
            return True
        return super().eventFilter(watched, event)

    def _redock_if_dropped_on_workspace(self, position: QPoint) -> None:
        window_position = self._main_window.mapFromGlobal(position)
        if not self._main_window.rect().contains(window_position):
            return
        merge = getattr(self._main_window, "_merge_dock_at_position", None)
        if merge is not None and merge(self._dock, position):
            return
        margins = 180
        if window_position.x() <= 260:
            area = Qt.DockWidgetArea.LeftDockWidgetArea
        elif window_position.x() >= self._main_window.width() - 300:
            area = Qt.DockWidgetArea.RightDockWidgetArea
        elif window_position.y() >= self._main_window.height() - margins:
            area = Qt.DockWidgetArea.BottomDockWidgetArea
        else:
            return
        self._dock.setFloating(False)
        self._main_window.addDockWidget(area, self._dock)
        self._update_floating_controls(False)

    def _update_drop_preview(self, position: QPoint) -> None:
        window_position = self._main_window.mapFromGlobal(position)
        if not self._main_window.rect().contains(window_position):
            self._set_drop_preview_visible(False)
            return
        width = self._main_window.width()
        height = self._main_window.height()
        if window_position.x() <= 260:
            geometry = (0, 0, 8, height)
        elif window_position.x() >= width - 300:
            geometry = (width - 8, 0, 8, height)
        elif window_position.y() >= height - 180:
            geometry = (0, height - 8, width, 8)
        else:
            self._set_drop_preview_visible(False)
            return
        self._drop_indicator.setGeometry(*geometry)
        self._set_drop_preview_visible(True)

    def _set_drop_preview_visible(self, visible: bool) -> None:
        if visible == self._drop_preview_visible:
            return
        self._drop_preview_visible = visible
        self._drop_indicator.setVisible(visible)
