"""Qt adapter for centralized semantic theme tokens."""

from PySide6.QtGui import QColor, QPalette

from dip_studio.presentation.theme import ThemeTokens


def palette_for(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens.surface))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens.surface_alt))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens.foreground))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.foreground))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.accent))
    return palette
