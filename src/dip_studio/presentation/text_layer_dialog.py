"""Modal dialog for creating and editing a TextLayer.

Emits ``textLayerConfirmed(TextLayer)`` when the user clicks OK.
Used by the ``text`` tool handler in ``main_window.py``.

Architecture: doc-06 — TextLayer is a first-class layer with editable
text content.  This dialog provides the editing UI before rasterisation.
"""
from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QColorDialog,
)

class TextLayerDialog(QDialog):
    """Modal dialog for composing / editing a TextLayer.

    Parameters
    ----------
    existing_layer :
        Pass an existing ``TextLayer`` to pre-populate all fields for editing.
        Pass ``None`` to open a blank "new text layer" dialog.
    parent :
        Parent widget.
    """

    # Emitted with the fully-constructed TextLayer prototype when OK is clicked.
    textLayerConfirmed = Signal(object)  # TextLayer

    def __init__(
        self,
        existing_layer: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._existing = existing_layer
        self._color_rgba: tuple[int, int, int, int] = (0, 0, 0, 255)
        self._bg_color_rgba: tuple[int, int, int, int] = (0, 0, 0, 0)

        if existing_layer is not None:
            self.setWindowTitle("Edit Text Layer")
            self._color_rgba = existing_layer.color_rgba
            self._bg_color_rgba = existing_layer.background_color
        else:
            self.setWindowTitle("Add Text Layer")

        self.setModal(True)
        self.setMinimumSize(480, 460)

        self._build_ui()
        if existing_layer is not None:
            self._populate(existing_layer)

    # ──────────────────────────── UI construction ────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Layer name
        self._name_edit = QLineEdit("Text Layer")
        form.addRow("Layer name:", self._name_edit)

        # Text content (multiline)
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Enter text here…")
        self._text_edit.setMinimumHeight(80)
        form.addRow("Text:", self._text_edit)

        # Font family
        self._font_combo = QFontComboBox()
        form.addRow("Font family:", self._font_combo)

        # Font size
        self._size_spin = QSpinBox()
        self._size_spin.setRange(4, 500)
        self._size_spin.setValue(24)
        self._size_spin.setSuffix(" pt")
        form.addRow("Font size:", self._size_spin)

        # Bold / Italic
        style_row = QWidget()
        sr_layout = QHBoxLayout(style_row)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        self._bold_check = QCheckBox("Bold")
        self._italic_check = QCheckBox("Italic")
        sr_layout.addWidget(self._bold_check)
        sr_layout.addWidget(self._italic_check)
        sr_layout.addStretch()
        form.addRow("Style:", style_row)

        # Colour picker
        colour_row = QWidget()
        cl_layout = QHBoxLayout(colour_row)
        cl_layout.setContentsMargins(0, 0, 0, 0)
        self._colour_preview = QLabel()
        self._colour_preview.setFixedSize(32, 20)
        self._colour_btn = QPushButton("Choose…")
        self._colour_btn.clicked.connect(self._pick_color)
        cl_layout.addWidget(self._colour_preview)
        cl_layout.addWidget(self._colour_btn)
        cl_layout.addStretch()
        form.addRow("Text colour:", colour_row)

        # Background colour
        bg_row = QWidget()
        bg_layout = QHBoxLayout(bg_row)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_preview = QLabel()
        self._bg_preview.setFixedSize(32, 20)
        self._bg_btn = QPushButton("Choose…")
        self._bg_btn.clicked.connect(self._pick_bg_color)
        bg_layout.addWidget(self._bg_preview)
        bg_layout.addWidget(self._bg_btn)
        bg_layout.addStretch()
        form.addRow("Background:", bg_row)

        # Alignment
        self._align_combo = QComboBox()
        self._align_combo.addItems(["left", "center", "right"])
        form.addRow("Alignment:", self._align_combo)

        # Writing direction
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["ltr", "rtl"])
        form.addRow("Direction:", self._dir_combo)

        # Letter spacing
        self._letter_spin = QDoubleSpinBox()
        self._letter_spin.setRange(-20.0, 100.0)
        self._letter_spin.setDecimals(1)
        self._letter_spin.setValue(0.0)
        self._letter_spin.setSuffix(" px")
        form.addRow("Letter spacing:", self._letter_spin)

        # Line spacing
        self._line_spin = QDoubleSpinBox()
        self._line_spin.setRange(0.5, 5.0)
        self._line_spin.setDecimals(2)
        self._line_spin.setSingleStep(0.1)
        self._line_spin.setValue(1.2)
        form.addRow("Line spacing:", self._line_spin)

        layout.addLayout(form)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accepted)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_color_preview()
        self._refresh_bg_preview()

    def _populate(self, layer: Any) -> None:
        self._name_edit.setText(layer.name)
        self._text_edit.setPlainText(layer.text)
        self._font_combo.setCurrentFont(QFont(layer.font_family))
        self._size_spin.setValue(layer.font_size)
        self._bold_check.setChecked(layer.bold)
        self._italic_check.setChecked(layer.italic)
        idx = self._align_combo.findText(layer.alignment)
        if idx >= 0:
            self._align_combo.setCurrentIndex(idx)
        idx = self._dir_combo.findText(layer.direction)
        if idx >= 0:
            self._dir_combo.setCurrentIndex(idx)
        self._letter_spin.setValue(layer.letter_spacing)
        self._line_spin.setValue(layer.line_spacing)
        self._refresh_color_preview()
        self._refresh_bg_preview()

    # ──────────────────────────── colour helpers ─────────────────────────────

    def _pick_color(self) -> None:
        r, g, b, a = self._color_rgba
        initial = QColor(r, g, b, a)
        col = QColorDialog.getColor(initial, self, "Text colour",
                                    QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if col.isValid():
            self._color_rgba = (col.red(), col.green(), col.blue(), col.alpha())
            self._refresh_color_preview()

    def _pick_bg_color(self) -> None:
        r, g, b, a = self._bg_color_rgba
        initial = QColor(r, g, b, a)
        col = QColorDialog.getColor(initial, self, "Background colour",
                                    QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if col.isValid():
            self._bg_color_rgba = (col.red(), col.green(), col.blue(), col.alpha())
            self._refresh_bg_preview()

    def _refresh_color_preview(self) -> None:
        r, g, b, a = self._color_rgba
        self._colour_preview.setStyleSheet(
            f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #888;"
        )

    def _refresh_bg_preview(self) -> None:
        r, g, b, a = self._bg_color_rgba
        self._bg_preview.setStyleSheet(
            f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #888;"
        )

    # ──────────────────────────── accept / build ─────────────────────────────

    def _on_accepted(self) -> None:
        layer_id = self._existing.id if self._existing is not None else uuid.uuid4()
        name = self._name_edit.text().strip() or "Text Layer"
        from dip_studio.application.presentation_bridge import make_text_layer
        layer = make_text_layer(
            id=layer_id,
            name=name,
            text=self._text_edit.toPlainText(),
            font_family=self._font_combo.currentFont().family(),
            font_size=self._size_spin.value(),
            bold=self._bold_check.isChecked(),
            italic=self._italic_check.isChecked(),
            color_rgba=self._color_rgba,
            alignment=self._align_combo.currentText(),
            direction=self._dir_combo.currentText(),
            letter_spacing=self._letter_spin.value(),
            line_spacing=self._line_spin.value(),
            background_color=self._bg_color_rgba,
        )
        self.textLayerConfirmed.emit(layer)
        self.accept()
