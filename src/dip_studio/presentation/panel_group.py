"""Detachable and regroupable panel tabs."""

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtWidgets import QTabBar, QTabWidget, QWidget


class _PanelTabBar(QTabBar):
    detachRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._press_position: QPoint | None = None
        self._press_index = -1
        self.installEventFilter(self)

    def eventFilter(self, watched: object, event: object) -> bool:
        if watched is self and event.type() == QEvent.Type.MouseButtonPress:
            index = self.tabAt(event.position().toPoint())
            if index >= 0 and event.button() == Qt.MouseButton.LeftButton:
                self._press_position = event.position().toPoint()
                self._press_index = index
        elif watched is self and event.type() == QEvent.Type.MouseMove:
            if self._press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
                current = event.position().toPoint()
                if (current - self._press_position).manhattanLength() >= 10:
                    index = self._press_index
                    self._press_position = None
                    self._press_index = -1
                    self.detachRequested.emit(index)
                    return True
        elif watched is self and event.type() == QEvent.Type.MouseButtonRelease:
            self._press_position = None
            self._press_index = -1
        return super().eventFilter(watched, event)


class PanelGroup(QTabWidget):
    """A panel stack whose tabs can be detached and attached again."""

    panelDetached = Signal(str, QWidget)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panelGroup")
        self.setTabPosition(QTabWidget.TabPosition.North)
        self.setDocumentMode(True)
        self.setMovable(True)
        tab_bar = _PanelTabBar(self)
        tab_bar.detachRequested.connect(self._detach_index)
        self.setTabBar(tab_bar)

    def add_panel(self, widget: QWidget, name: str) -> None:
        self.addTab(widget, name)

    def attach_panel(self, widget: QWidget, name: str) -> None:
        for index in range(self.count()):
            if self.widget(index) is widget:
                self.setCurrentIndex(index)
                return
        self.add_panel(widget, name)
        self.setCurrentWidget(widget)

    def _detach_index(self, index: int) -> None:
        if not 0 <= index < self.count():
            return
        widget = self.widget(index)
        name = self.tabText(index)
        self.removeTab(index)
        widget.setParent(None)
        widget.setVisible(True)
        widget.show()
        self.panelDetached.emit(name, widget)
