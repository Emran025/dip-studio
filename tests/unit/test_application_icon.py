"""Regression coverage for the packaged application icon."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dip_studio.presentation.vector_icons import icon_for


def test_application_icon_uses_supplied_svg_asset() -> None:
    app = QApplication.instance() or QApplication([])
    del app
    icon = icon_for("app")
    assert not icon.isNull()
    assert icon.pixmap(256, 256).isNull() is False
