"""Theme-aware standalone User Documentation Viewer dialog.

Features:
- Collapsible navigation sidebar (☰) for small screens.
- Bi-directional language support (Arabic RTL with Cairo font vs English LTR).
- Relative image rendering and rich HTML typography.
- Search filter and Prev/Next page navigation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dip_studio.application.presentation_bridge import parse_doc_directory
from dip_studio.presentation.vector_icons import icon_for


class DocPage(Protocol):
    """Presentation-facing page contract supplied by the application bridge."""

    file_path: Any
    metadata: Any
    markdown_text: str
    html_content: str
    is_rtl: bool


class DocSidebarWidget(QWidget):
    """Collapsible table-of-contents navigation sidebar."""

    pageSelected = Signal(object)  # DocPage

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)
        self._pages: tuple[DocPage, ...] = ()
        self._filtered_pages: tuple[DocPage, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Search box
        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("البحث في الدليل / Search docs…")
        self._search_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._search_edit.textChanged.connect(self._filter_pages)
        layout.addWidget(self._search_edit)

        # List widget
        self._list_widget = QListWidget(self)
        self._list_widget.setObjectName("docSidebarList")
        self._list_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list_widget)

    def set_pages(self, pages: tuple[DocPage, ...]) -> None:
        self._pages = pages
        self._filter_pages(self._search_edit.text())

    def _filter_pages(self, query: str) -> None:
        query = query.strip().lower()
        self._list_widget.clear()
        matching: list[DocPage] = []

        for page in self._pages:
            if not query or query in page.metadata.title.lower() or query in page.markdown_text.lower():
                matching.append(page)
                item = QListWidgetItem(page.metadata.title)
                item.setData(Qt.ItemDataRole.UserRole, page)
                if page.is_rtl:
                    item.setFont(QFont("Cairo", 10))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._list_widget.addItem(item)

        self._filtered_pages = tuple(matching)
        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)

    def _on_selection_changed(self) -> None:
        items = self._list_widget.selectedItems()
        if items:
            page = items[0].data(Qt.ItemDataRole.UserRole)
            self.pageSelected.emit(page)


class DocViewerDialog(QDialog):
    """Standalone User Documentation Viewer Window."""

    def __init__(
        self,
        docs_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("دليل المستخدم — User Guide")
        self.setMinimumSize(860, 580)
        self.resize(980, 640)

        default_docs = Path("docs/user_guide")
        self._docs_dir = docs_dir if docs_dir and docs_dir.exists() else default_docs
        self._pages: tuple[DocPage, ...] = ()
        self._current_index: int = 0
        self._sidebar_collapsed: bool = False
        self._is_rtl = True

        self._build_ui()
        self.reload_docs()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Toolbar
        header_bar = QWidget(self)
        header_bar.setFixedHeight(44)
        header_bar.setStyleSheet(
            "QWidget { background-color: #1e293b; border-bottom: 1px solid #334155; }"
            "QPushButton, QToolButton { color: #e2e8f0; background: #334155;"
            " border: 1px solid #475569; border-radius: 4px; padding: 4px 10px;"
            " font-family: Cairo, 'Segoe UI', sans-serif; }"
            "QPushButton:hover, QToolButton:hover { background: #475569; }"
            "QPushButton:disabled { color: #64748b; background: #1e293b; }"
        )
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(8, 4, 8, 4)

        # Collapse toggle button (☰)
        self._toggle_btn = QToolButton(header_bar)
        self._toggle_btn.setObjectName("toggleDocsSidebar")
        self._toggle_btn.setIcon(icon_for("sidebar"))
        self._toggle_btn.setIconSize(QSize(18, 18))
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setToolTip("إظهار أو إخفاء الشريط الجانبي")
        self._toggle_btn.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self._toggle_btn)

        # Document Title Label
        self._title_label = QLabel("دليل المستخدم", header_bar)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #f8fafc;")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        # Prev / Next Navigation Buttons
        self._prev_btn = QPushButton("← السابق", header_bar)
        self._prev_btn.setObjectName("previousDocPage")
        self._prev_btn.setMinimumWidth(92)
        self._prev_btn.clicked.connect(self._goto_prev)
        header_layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton("التالي →", header_bar)
        self._next_btn.setObjectName("nextDocPage")
        self._next_btn.setMinimumWidth(92)
        self._next_btn.clicked.connect(self._goto_next)
        header_layout.addWidget(self._next_btn)

        main_layout.addWidget(header_bar)

        # 2. Main Content Splitter (Sidebar + Text Browser)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)

        self._sidebar = DocSidebarWidget(self._splitter)
        self._sidebar.pageSelected.connect(self._display_page)
        self._splitter.addWidget(self._sidebar)

        self._browser = QTextBrowser(self._splitter)
        self._browser.setOpenExternalLinks(True)
        self._browser.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._browser.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._splitter.addWidget(self._browser)

        self._splitter.setSizes([220, 760])
        main_layout.addWidget(self._splitter)

    def reload_docs(self) -> None:
        self._pages = cast(tuple[DocPage, ...], parse_doc_directory(self._docs_dir))
        self._sidebar.set_pages(self._pages)
        if self._pages:
            self._display_page(self._pages[0])

    def toggle_sidebar(self) -> None:
        self._sidebar_collapsed = not self._sidebar_collapsed
        self._sidebar.setVisible(not self._sidebar_collapsed)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._update_sidebar_toggle_button()

    def _update_sidebar_toggle_button(self) -> None:
        compact = self.width() < 900
        self._toggle_btn.setIcon(icon_for("sidebar"))
        self._toggle_btn.setToolTip(
            "إظهار أو إخفاء الشريط الجانبي"
            if self._is_rtl
            else "Show or hide the sidebar"
        )

    def _display_page(self, page: DocPage) -> None:
        if page not in self._pages:
            return
        self._current_index = self._pages.index(page)
        self._title_label.setText(page.metadata.title)

        # Update language-aware fonts & navigation labels
        if page.is_rtl:
            self._is_rtl = True
            self._title_label.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
            self._prev_btn.setFont(QFont("Cairo", 10))
            self._next_btn.setFont(QFont("Cairo", 10))
            self._title_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self._sidebar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self._browser.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self._browser.setAlignment(Qt.AlignmentFlag.AlignRight)
            self._prev_btn.setText("← السابق")
            self._next_btn.setText("التالي →")
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self._is_rtl = False
            self._title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            self._prev_btn.setFont(QFont("Segoe UI", 10))
            self._next_btn.setFont(QFont("Segoe UI", 10))
            self._title_label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._sidebar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._browser.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._browser.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._prev_btn.setText("← Previous")
            self._next_btn.setText("Next →")
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self._browser.setHtml(page.html_content)
        self._update_sidebar_toggle_button()
        self._update_nav_buttons()

    def _goto_prev(self) -> None:
        if self._current_index > 0:
            target = self._pages[self._current_index - 1]
            self._sidebar._list_widget.setCurrentRow(self._current_index - 1)

    def _goto_next(self) -> None:
        if self._current_index < len(self._pages) - 1:
            target = self._pages[self._current_index + 1]
            self._sidebar._list_widget.setCurrentRow(self._current_index + 1)

    def _update_nav_buttons(self) -> None:
        self._prev_btn.setEnabled(self._current_index > 0)
        self._next_btn.setEnabled(self._current_index < len(self._pages) - 1)
