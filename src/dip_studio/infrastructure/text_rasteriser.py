"""Text rasteriser — converts a TextLayer into an RGBA NumPy array.

Lives in ``infrastructure/`` because it imports PySide6 (a Qt dependency),
which is not allowed in ``domain/`` or ``application/``.

The rasterised array is written into ``ImageDataStore`` by the application
commands (``AddTextLayer``, ``EditTextLayer``) and stored as the layer's
``buffer_id``.

Architecture: doc-06 TextLayer — "Text stays editable until rasterisation is
explicitly requested."  This module is that rasterisation step.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from dip_studio.domain.model import TextLayer


def rasterise_text(layer: "TextLayer", width: int, height: int) -> np.ndarray:
    """Render *layer*'s text into an RGBA uint8 ndarray of shape (height, width, 4).

    Uses ``QPainter.drawText()`` for accurate font metrics, kerning, and
    RTL/Arabic text direction support (via Qt's Bidi engine).

    Parameters
    ----------
    layer :
        The ``TextLayer`` containing text content and style properties.
    width, height :
        Dimensions of the output canvas in pixels.  Text is placed at the
        top-left of the canvas; ``layer.transform`` (if any) is NOT applied
        here — the compositor handles transforms at render time.

    Returns
    -------
    np.ndarray
        ``uint8`` RGBA array of shape ``(height, width, 4)``.
    """
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import (
        QColor,
        QFont,
        QImage,
        QPainter,
        QPen,
    )

    # ── Build QImage target ─────────────────────────────────────────────────
    qimg = QImage(width, height, QImage.Format.Format_RGBA8888)
    qimg.fill(QColor(0, 0, 0, 0))  # transparent background

    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # ── Optional background fill ────────────────────────────────────────────
    br, bg, bb, ba = layer.background_color
    if ba > 0:
        painter.fillRect(0, 0, width, height, QColor(br, bg, bb, ba))

    # ── Font ────────────────────────────────────────────────────────────────
    font = QFont(layer.font_family, layer.font_size)
    font.setBold(layer.bold)
    font.setItalic(layer.italic)
    if layer.letter_spacing != 0.0:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, layer.letter_spacing)
    painter.setFont(font)

    # ── Text colour ─────────────────────────────────────────────────────────
    r, g, b, a = layer.color_rgba
    painter.setPen(QPen(QColor(r, g, b, a)))

    # ── Alignment ───────────────────────────────────────────────────────────
    h_align_map = {
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
    }
    h_align = h_align_map.get(layer.alignment, Qt.AlignmentFlag.AlignLeft)
    alignment_flags = h_align | Qt.AlignmentFlag.AlignTop

    # ── Layout direction (RTL for Arabic) ──────────────────────────────────
    if layer.direction == "rtl":
        painter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    else:
        painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    # ── Draw ────────────────────────────────────────────────────────────────
    rect = QRectF(0.0, 0.0, float(width), float(height))
    painter.drawText(rect, alignment_flags, layer.text)
    painter.end()

    # ── Convert QImage → NumPy ──────────────────────────────────────────────
    # QImage.Format_RGBA8888 stores bytes in R-G-B-A order, which matches
    # the NumPy RGBA convention used throughout dip_studio.
    ptr = qimg.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4)).copy()
    return arr
