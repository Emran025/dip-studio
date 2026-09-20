"""Desktop application entry point."""

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from dip_studio.composition import create_main_window
from dip_studio.presentation.theme import DARK
from dip_studio.presentation.theme_adapter import palette_for, stylesheet_for
from dip_studio.presentation.vector_icons import icon_for


def run() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("DIP Studio")
    application.setOrganizationName("DIP Studio")
    application.setWindowIcon(icon_for("app"))
    application.setPalette(palette_for(DARK))
    QSettings("DIP Studio", "DIP Studio").clear()  # Reset cached workspace/debug state.
    application.setStyleSheet(stylesheet_for(DARK))
    window = create_main_window()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(run())
