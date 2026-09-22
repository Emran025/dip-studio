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
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.accent_foreground))
    palette.setColor(QPalette.ColorRole.Button, QColor(tokens.surface_alt))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.foreground))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens.foreground_muted))
    return palette


def stylesheet_for(tokens: ThemeTokens) -> str:
    return f"""
        QWidget {{
            color: {tokens.foreground};
        }}
        /* One application-wide scrollbar policy: compact, square, theme-aware,
           with no arrow buttons at either end. */
        QScrollBar:vertical {{
            background: {tokens.surface};
            width: 8px;
            margin: 0;
            border: 0;
        }}
        QScrollBar:horizontal {{
            background: {tokens.surface};
            height: 8px;
            margin: 0;
            border: 0;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {tokens.border};
            border: 0;
            border-radius: 0;
            min-height: 24px;
            min-width: 24px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {tokens.foreground_muted};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
            height: 0;
            border: 0;
            background: transparent;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
        QDialog, QMainWindow {{
            background: {tokens.surface};
        }}
        QDialog {{
            min-width: 360px;
            border: 1px solid {tokens.border};
            border-radius: 4px;
        }}
        QToolButton#layerActionButton {{
            background: {tokens.surface_alt};
            color: {tokens.foreground};
            border: 1px solid {tokens.border};
            border-radius: 4px;
            padding: 3px;
        }}
        QToolButton#layerActionButton:hover {{
            background: {tokens.field};
            border-color: {tokens.accent};
        }}
        QToolButton#layerActionButton:pressed {{
            background: {tokens.accent};
            border-color: {tokens.accent};
        }}
        QMenuBar {{
            background: {tokens.surface};
            color: {tokens.foreground};
            border-bottom: 1px solid {tokens.border};
            padding: 2px 4px;
        }}
        QMenuBar::item {{
            background: transparent;
            color: {tokens.foreground};
            padding: 6px 10px;
        }}
        QMenuBar::item:selected, QMenuBar::item:pressed {{
            background: {tokens.accent};
            color: {tokens.accent_foreground};
        }}
        QMenu {{
            background: {tokens.surface_alt};
            color: {tokens.foreground};
            border: 1px solid {tokens.border};
            padding: 5px;
        }}
        QMenu::item {{
            background: transparent;
            color: {tokens.foreground};
            padding: 7px 26px 7px 10px;
        }}
        QMenu::item:selected {{
            background: {tokens.accent};
            color: {tokens.accent_foreground};
        }}
        QLabel {{
            color: {tokens.foreground};
        }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {{
            background: {tokens.field};
            color: {tokens.field_foreground};
            border: 1px solid {tokens.border};
            border-radius: 4px;
            padding: 5px 7px;
            selection-background-color: {tokens.accent};
            selection-color: {tokens.accent_foreground};
        }}
        QComboBox QAbstractItemView, QListWidget {{
            background: {tokens.field};
            color: {tokens.field_foreground};
            border: 1px solid {tokens.border};
            selection-background-color: {tokens.accent};
            selection-color: {tokens.accent_foreground};
        }}
        QPushButton, QDialogButtonBox QPushButton {{
            background: {tokens.surface_alt};
            color: {tokens.foreground};
            border: 1px solid {tokens.border};
            border-radius: 4px;
            padding: 6px 16px;
            min-height: 20px;
        }}
        QPushButton:hover, QDialogButtonBox QPushButton:hover {{
            border-color: {tokens.accent};
            background: {tokens.field};
        }}
        QPushButton:default, QDialogButtonBox QPushButton:focus {{
            background: {tokens.accent};
            color: {tokens.accent_foreground};
            border-color: {tokens.accent};
        }}
        QCheckBox, QRadioButton {{
            color: {tokens.foreground};
        }}
        QTabBar::tab {{
            background: {tokens.surface_alt};
            color: {tokens.foreground};
            padding: 7px 10px;
        }}
        QTabBar::tab:selected {{
            background: {tokens.accent};
            color: {tokens.accent_foreground};
        }}
        QWidget#documentBar {{
            background: {tokens.surface};
        }}
        QTabBar#documentTabs {{
            background: {tokens.surface};
        }}
        QTabBar#documentTabs::tab {{
            background: {tokens.surface_alt};
            color: {tokens.foreground_muted};
            border: 1px solid {tokens.border};
            border-bottom: 0;
            border-radius: 4px 4px 0 0;
            padding: 6px 18px;
            margin-right: 3px;
        }}
        QTabBar#documentTabs::tab:selected {{
            background: {tokens.field};
            color: {tokens.foreground};
            border-top: 2px solid {tokens.accent};
        }}
        QToolButton#newDocumentButton {{
            background: {tokens.surface_alt};
            color: {tokens.foreground};
            border: 1px solid {tokens.border};
            border-radius: 4px;
            font-size: 18px;
        }}
        QToolButton#newDocumentButton:hover {{
            background: {tokens.accent};
            color: {tokens.accent_foreground};
            border-color: {tokens.accent};
        }}
    """
