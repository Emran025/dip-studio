"""Unit tests for DocParser, DocViewerDialog, and DocSidebarWidget."""

from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
import pytest

from dip_studio.infrastructure.doc_parser import DocPage, DocParser
from dip_studio.presentation.doc_viewer import DocSidebarWidget, DocViewerDialog


@pytest.fixture(autouse=True)
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_doc_parser_arabic_and_english() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Arabic test file
        ar_file = tmp_path / "01-arabic.md"
        ar_file.write_text(
            "---\ntitle: دليل المساعدة\norder: 1\ncategory: User Guide\n---\n"
            "# دليل المساعدة والمعالجة\n"
            "هذا النص باللغة العربية للاختبار.\n"
            "> [!NOTE] هذا تنبيه مفيد.\n"
            "![صورة توضيحية](images/tool.png)\n",
            encoding="utf-8",
        )

        # English test file
        en_file = tmp_path / "02-english.md"
        en_file.write_text(
            "---\ntitle: Getting Started\norder: 2\ncategory: User Guide\n---\n"
            "# Getting Started Guide\n"
            "This is English text for testing.\n",
            encoding="utf-8",
        )

        pages = DocParser.parse_directory(tmp_path)
        assert len(pages) == 2

        ar_page = next(p for p in pages if "arabic" in p.file_path.name)
        assert ar_page.is_rtl is True
        assert ar_page.metadata.title == "دليل المساعدة"
        assert "Cairo" in ar_page.html_content
        assert "file:///" in ar_page.html_content

        en_page = next(p for p in pages if "english" in p.file_path.name)
        assert en_page.is_rtl is False
        assert en_page.metadata.title == "Getting Started"


def test_doc_viewer_dialog_and_sidebar_toggle() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        doc_file = tmp_path / "guide.md"
        doc_file.write_text("# Test User Guide\nSample content here.", encoding="utf-8")

        dialog = DocViewerDialog(docs_dir=tmp_path)
        assert len(dialog._pages) == 1
        assert not dialog._sidebar.isHidden()

        # Toggle sidebar collapse
        dialog.toggle_sidebar()
        assert dialog._sidebar.isHidden()
        dialog.toggle_sidebar()
        assert not dialog._sidebar.isHidden()
