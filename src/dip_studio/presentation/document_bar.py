"""Compact document switcher shown in the main workspace chrome."""

from typing import Protocol

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QToolButton, QWidget


class DocumentTab(Protocol):
    id: object
    name: str
    is_dirty: bool


class DocumentBar(QWidget):
    """Shows the currently open document without duplicating editing tools."""

    newRequested = Signal()
    documentSelected = Signal(object)
    documentCloseRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("documentBar")
        self._tabs = QTabBar(self)
        self._tabs.setObjectName("documentTabs")
        self._tabs.setExpanding(False)
        self._tabs.setUsesScrollButtons(True)
        self._tabs.setDocumentMode(True)
        self._tabs.setDrawBase(False)
        self._tabs.setMinimumWidth(180)
        self._tabs.setTabsClosable(True)
        self._tabs.currentChanged.connect(self._document_selected)
        self._tabs.tabCloseRequested.connect(self._document_close_requested)

        new_button = QToolButton(self)
        new_button.setObjectName("newDocumentButton")
        new_button.setText("+")
        new_button.setToolTip("New project")
        new_button.setIconSize(QSize(14, 14))
        new_button.setFixedSize(28, 28)
        new_button.clicked.connect(self.newRequested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(new_button)

    def set_documents(
        self, documents: tuple[DocumentTab, ...], active_id: object
    ) -> None:
        """Synchronize tabs with the controller's open document sessions."""
        self._tabs.blockSignals(True)
        while self._tabs.count():
            self._tabs.removeTab(0)
        active_index = -1
        for index, document in enumerate(documents):
            label = f"{document.name}{'*' if document.is_dirty else ''}"
            tab_index = self._tabs.addTab(label)
            self._tabs.setTabData(tab_index, document.id)
            self._tabs.setTabToolTip(tab_index, "Active document")
            if str(document.id) == str(active_id):
                active_index = index
        if active_index >= 0:
            self._tabs.setCurrentIndex(active_index)
        self._tabs.blockSignals(False)

    def _document_selected(self, index: int) -> None:
        if index >= 0:
            self.documentSelected.emit(self._tabs.tabData(index))

    def _document_close_requested(self, index: int) -> None:
        if index >= 0:
            self.documentCloseRequested.emit(self._tabs.tabData(index))
