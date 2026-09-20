"""Desktop application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from dip_studio.composition import create_main_window
from dip_studio.presentation.theme_adapter import palette_for
from dip_studio.presentation.theme import DARK


def run() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("DIP Studio")
    application.setPalette(palette_for(DARK))
    window = create_main_window()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(run())
