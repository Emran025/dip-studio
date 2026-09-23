"""Unit tests for DocParser, DocViewerDialog, and DocSidebarWidget."""

import tempfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from dip_studio.infrastructure.doc_parser import DocParser
from dip_studio.presentation.doc_viewer import DocViewerDialog
from dip_studio.presentation.vector_icons import icon_for


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
            "---\n"
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
        assert 'class="doc-separator"' in ar_page.html_content
        assert "<p><hr" not in ar_page.html_content

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


def test_doc_viewer_uses_cairo_controls_and_responsive_sidebar_button() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir)
        (docs_dir / "ar.md").write_text(
            "---\ntitle: دليل\nlang: ar\ndirection: rtl\n---\n# دليل\n",
            encoding="utf-8",
        )
        dialog = DocViewerDialog(docs_dir=docs_dir)
        dialog.resize(1100, 640)
        dialog._update_sidebar_toggle_button()
        assert not dialog._toggle_btn.text()
        assert not dialog._toggle_btn.icon().isNull()
        assert dialog._prev_btn.font().family() == "Cairo"
        assert dialog._next_btn.font().family() == "Cairo"

        dialog.resize(700, 640)
        dialog._update_sidebar_toggle_button()
        assert not dialog._toggle_btn.text()
        assert not dialog._toggle_btn.icon().isNull()


def test_sidebar_icon_falls_back_when_qtawesome_name_is_unavailable() -> None:
    assert not icon_for("sidebar").isNull()
