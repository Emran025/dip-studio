"""Reusable dialogs and parameter controls for the desktop workspace."""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dip_studio.application.shortcut_registry import (
    ShortcutBinding,
    ShortcutRegistry,
    default_shortcut_registry,
)
from dip_studio.presentation.vector_icons import icon_for


def _choice_icon_name(choice: str) -> str:
    """Choose a meaningful existing icon for common choice-list values."""
    normalized = choice.casefold()
    if any(token in normalized for token in ("rgba", "rgb", "color", "colour")):
        return "color_selection"
    if "gray" in normalized or "grey" in normalized:
        return "edge"
    if normalized in {"ltr", "rtl"}:
        return "text"
    if normalized in {"png", "jpeg", "jpg", "bmp", "tiff", "ppm"}:
        return "file.new"
    if any(token in normalized for token in ("multiply", "darken")):
        return "gradient"
    if any(token in normalized for token in ("screen", "lighten")):
        return "zoom"
    return "selection"


@dataclass(frozen=True, slots=True)
class NewProjectValues:
    name: str
    width: int
    height: int
    color_mode: str


class NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New project")
        self.setModal(True)
        self.setMinimumSize(420, 260)
        self._name = QLineEdit("Untitled")
        self._width = QSpinBox()
        self._width.setRange(1, 100000)
        self._width.setValue(800)
        self._height = QSpinBox()
        self._height.setRange(1, 100000)
        self._height.setValue(600)
        self._color_mode = QComboBox()
        for label, icon_name in (
            ("RGBA 8-bit", "color_selection"),
            ("RGB 8-bit", "gradient"),
            ("Grayscale 8-bit", "edge"),
        ):
            self._color_mode.addItem(icon_for(icon_name), label)

        form = QFormLayout()
        form.addRow("Name", self._name)
        form.addRow("Width", self._width)
        form.addRow("Height", self._height)
        form.addRow("Color mode", self._color_mode)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> NewProjectValues:
        return NewProjectValues(
            self._name.text().strip(),
            self._width.value(),
            self._height.value(),
            self._color_mode.currentText(),
        )

    def accept(self) -> None:
        if not self._name.text().strip():
            self._name.setFocus()
            return
        super().accept()


class CommandPaletteDialog(QDialog):
    def __init__(
        self,
        commands: tuple[tuple[str, Callable[[], None]], ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Command palette")
        self.setModal(True)
        self.setMinimumSize(560, 380)
        self.resize(560, 380)
        self._commands = commands
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search commands and tools...")
        self._list = QListWidget()
        self._search.textChanged.connect(self._filter)
        self._list.itemActivated.connect(self._activate)
        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._list)
        self._filter("")
        self._search.setFocus()

    def _filter(self, text: str) -> None:
        query = text.casefold().strip()
        self._list.clear()
        for label, _ in self._commands:
            if not query or query in label.casefold():
                self._list.addItem(label)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _activate(self, item: QListWidgetItem) -> None:
        for label, callback in self._commands:
            if label == item.text():
                self.accept()
                callback()
                return


class ShortcutEditorDialog(QDialog):
    """Searchable shortcut editor with conflict validation."""

    def __init__(self, registry: ShortcutRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setMinimumSize(700, 500)
        self.resize(700, 500)
        self._registry = registry
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search commands...")
        self._list = QListWidget()
        self._editor = QKeySequenceEdit()
        self._apply = QPushButton("Apply")
        self._cancel = QPushButton("Cancel")
        self._reset = QPushButton("Reset")
        self._bindings = {item.command_id: item for item in registry.list()}
        self._defaults = default_shortcut_registry()
        self._list.currentItemChanged.connect(self._select_binding)
        self._search.textChanged.connect(self._filter)
        self._apply.clicked.connect(self._apply_changes)
        self._cancel.clicked.connect(self.reject)
        self._reset.clicked.connect(self._reset_binding)
        form = QFormLayout()
        form.addRow("Shortcut", self._editor)
        buttons = QHBoxLayout()
        buttons.addWidget(self._apply)
        buttons.addWidget(self._reset)
        buttons.addWidget(self._cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._list)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self._filter("")

    def _filter(self, text: str) -> None:
        query = text.casefold().strip()
        self._list.clear()
        for binding in self._bindings.values():
            if not query or query in binding.command_id.casefold():
                item = QListWidgetItem(f"{binding.command_id} — {binding.key}")
                item.setData(Qt.ItemDataRole.UserRole, binding.command_id)
                self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _select_binding(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        binding = self._bindings[current.data(Qt.ItemDataRole.UserRole)]
        self._editor.setKeySequence(QKeySequence(binding.key))

    def _reset_binding(self) -> None:
        current = self._list.currentItem()
        if current is None:
            return
        command_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            binding = self._defaults.get(command_id)
        except KeyError:
            return
        self._editor.setKeySequence(QKeySequence(binding.key))

    def _apply_changes(self) -> None:
        current = self._list.currentItem()
        if current is None:
            self.accept()
            return
        command_id = current.data(Qt.ItemDataRole.UserRole)
        binding = self._bindings[command_id]
        key = self._editor.keySequence().toString()
        try:
            self._registry.register(
                ShortcutBinding(
                    command_id,
                    key,
                    binding.context,
                    binding.priority,
                    binding.enabled,
                    binding.user_customizable,
                )
            )
        except ValueError:
            self._editor.setFocus()
            return
        self._bindings[command_id] = self._registry.get(command_id)
        self._filter(self._search.text())
        self.accept()


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    label: str
    kind: str
    default: object
    minimum: float = 0
    maximum: float = 100
    choices: tuple[str, ...] = ()
    id: str | None = None
    read_only: bool = False
    step: float | None = None


class ToolParametersPanel(QWidget):
    """Generates controls from a tool parameter schema."""

    previewRequested = Signal(dict)
    applyRequested = Signal(dict)
    cancelRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._controls: dict[str, QWidget] = {}
        self._definitions: tuple[ParameterDefinition, ...] = ()
        self._actions: QWidget | None = None
        self._empty = QLineEdit("Select a tool to edit parameters")
        self._empty.setReadOnly(True)
        self._form.addRow(self._empty)

    def _create_actions(self) -> QWidget:
        actions_widget = QWidget()
        actions = QHBoxLayout(actions_widget)
        actions.setContentsMargins(0, 8, 0, 0)
        preview = QPushButton("Preview")
        apply = QPushButton("Apply")
        cancel = QPushButton("Cancel")
        preview.clicked.connect(lambda: self.previewRequested.emit(self.values()))
        apply.clicked.connect(lambda: self.applyRequested.emit(self.values()))
        cancel.clicked.connect(self.cancelRequested)
        actions.addWidget(preview)
        actions.addWidget(apply)
        actions.addWidget(cancel)
        return actions_widget

    def set_schema(
        self,
        schema: tuple[ParameterDefinition, ...],
        show_actions: bool = True,
    ) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._controls.clear()
        if self._actions is not None:
            self._actions.deleteLater()
        self._actions = None
        self._definitions = schema
        if not schema:
            self._form.addRow("Parameters", QLineEdit("No parameters"))
            return
        for index, definition in enumerate(schema):
            control: QWidget
            if definition.kind == "integer":
                widget = QSpinBox()
                widget.setRange(int(definition.minimum), int(definition.maximum))
                if definition.step is not None:
                    widget.setSingleStep(int(definition.step))
                widget.setValue(int(definition.default))
                widget.valueChanged.connect(lambda _v: self.previewRequested.emit(self.values()))
                control = widget
            elif definition.kind == "number":
                widget = QDoubleSpinBox()
                widget.setRange(definition.minimum, definition.maximum)
                if definition.step is not None:
                    widget.setSingleStep(definition.step)
                widget.setValue(float(definition.default))
                widget.valueChanged.connect(lambda _v: self.previewRequested.emit(self.values()))
                control = widget
            elif definition.kind == "choice":
                widget = QComboBox()
                for choice in definition.choices:
                    widget.addItem(
                        icon_for(_choice_icon_name(choice)),
                        choice,
                    )
                widget.setCurrentText(str(definition.default))
                widget.currentTextChanged.connect(lambda _t: self.previewRequested.emit(self.values()))
                control = widget
            elif definition.kind == "boolean":
                widget = QCheckBox()
                widget.setChecked(bool(definition.default))
                widget.toggled.connect(lambda _c: self.previewRequested.emit(self.values()))
                control = widget
            else:
                widget = QLineEdit(str(definition.default))
                widget.editingFinished.connect(lambda: self.previewRequested.emit(self.values()))
                control = widget
            if definition.read_only:
                control.setEnabled(False)
            self._controls[str(index)] = control
            self._form.addRow(definition.label, control)
        if show_actions:
            self._actions = self._create_actions()
            self._form.addRow(self._actions)
        else:
            self._actions = None

    def values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for index, definition in enumerate(self._definitions):
            control = self._controls[str(index)]
            if isinstance(control, QSpinBox | QDoubleSpinBox):
                value: object = control.value()
            elif isinstance(control, QComboBox):
                value = control.currentText()
            elif isinstance(control, QCheckBox):
                value = control.isChecked()
            elif isinstance(control, QLineEdit):
                value = control.text()
            else:
                raise TypeError(f"Unsupported parameter control: {type(control).__name__}")
            values[definition.id or definition.label] = value
        return values

    def set_values(self, values: dict[str, object]) -> None:
        """Update control values programmatically by label or index."""
        key_to_index = {
            key.lower(): str(i)
            for i, definition in enumerate(self._definitions)
            for key in (definition.label, definition.id or definition.label)
        }
        for k, v in values.items():
            idx = key_to_index.get(str(k).lower())
            if idx and idx in self._controls:
                ctrl = self._controls[idx]
                blocker = QSignalBlocker(ctrl)
                if isinstance(ctrl, QSpinBox):
                    try:
                        ctrl.setValue(int(float(v)))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(ctrl, QDoubleSpinBox):
                    try:
                        ctrl.setValue(float(v))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(ctrl, QComboBox):
                    ctrl.setCurrentText(str(v))
                elif isinstance(ctrl, QCheckBox):
                    ctrl.setChecked(bool(v))
                elif isinstance(ctrl, QLineEdit):
                    ctrl.setText(str(v))
                del blocker


# ──────────────────────────── Analysis Dialogs ───────────────────────────────

class _HistogramWidget(QWidget):
    """QPainter-based per-channel histogram bar chart.

    Renders 256 frequency bins as filled rectangles on a dark background using
    a log scale so both peak and shadow detail are visible simultaneously.
    """

    _CHANNEL_COLORS: dict[str, tuple[int, int, int]] = {
        "R": (220, 60, 60),
        "G": (60, 200, 60),
        "B": (60, 100, 220),
        "L": (160, 160, 160),
        "A": (200, 200, 60),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts: list[int] = []
        self._channel: str = "L"
        self.setMinimumSize(512, 200)

    def set_data(self, channel: str, counts: list[int]) -> None:
        """Update the displayed channel data and trigger a repaint."""
        self._channel = channel
        self._counts = counts
        self.update()

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        import math

        w = self.width()
        h = self.height()
        n = len(self._counts)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            # Dark background
            painter.fillRect(0, 0, w, h, QColor(28, 28, 28))
            if n == 0:
                return
            # Log-scale counts for better visual dynamic range.
            log_counts = [math.log1p(c) for c in self._counts]
            max_log = max(log_counts) if log_counts else 1.0
            if max_log == 0.0:
                max_log = 1.0
            r, g, b = self._CHANNEL_COLORS.get(self._channel, (160, 160, 160))
            bar_color = QColor(r, g, b, 200)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bar_color)
            chart_h = h - 24  # leave 24 px for x-axis labels
            bar_w = w / n
            for i, val in enumerate(log_counts):
                bar_h = int((val / max_log) * chart_h)
                x = int(i * bar_w)
                bw = max(1, int(bar_w) + (1 if i < n - 1 else 0))
                painter.drawRect(x, chart_h - bar_h, bw, bar_h)
            # X-axis
            painter.setPen(QColor(120, 120, 120))
            painter.drawLine(0, chart_h, w, chart_h)
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(2, h - 4, "0")
            painter.drawText(w // 2 - 10, h - 4, "128")
            painter.drawText(w - 24, h - 4, "255")
        finally:
            painter.end()


class HistogramDialog(QDialog):
    """Display per-channel pixel intensity histogram using a QPainter bar chart."""

    def __init__(
        self,
        histogram_data: "dict[str, list[int]]",
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            histogram_data: mapping of channel name → list of 256 counts.
                Expected keys: 'R', 'G', 'B' for colour images or 'L' for grey.
        """
        super().__init__(parent)
        self.setWindowTitle("Histogram")
        self.setModal(False)
        self.setMinimumSize(520, 320)
        self.resize(640, 380)

        self._data = histogram_data
        self._channel_selector = QComboBox()
        channel_icons = {
            "R": "brush",
            "G": "gradient",
            "B": "shape",
            "A": "layer.visible",
            "L": "edge",
        }
        for channel in histogram_data:
            self._channel_selector.addItem(
                icon_for(channel_icons.get(channel.upper(), "histogram")),
                channel,
            )
        self._channel_selector.currentTextChanged.connect(self._refresh)

        self._histogram_widget = _HistogramWidget(self)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._channel_selector)
        layout.addWidget(self._histogram_widget, stretch=1)
        layout.addWidget(buttons)

        self._refresh(self._channel_selector.currentText())

    def _refresh(self, channel: str) -> None:
        counts = self._data.get(channel, [])
        self._histogram_widget.set_data(channel, counts)

    @staticmethod
    def from_buffer(
        arr: "object",  # np.ndarray
        parent: QWidget | None = None,
    ) -> "HistogramDialog":
        """Create a HistogramDialog from a NumPy array (H, W, C) or (H, W)."""
        import numpy as np  # type: ignore[import-untyped]

        a: np.ndarray = arr  # type: ignore[assignment]
        data: dict[str, list[int]] = {}
        if a.ndim == 2:
            hist, _ = np.histogram(a.flatten(), bins=256, range=(0, 256))
            data["L"] = hist.tolist()
        elif a.ndim == 3:
            for i, name in enumerate(("R", "G", "B", "A")[: a.shape[2]]):
                hist, _ = np.histogram(a[:, :, i].flatten(), bins=256, range=(0, 256))
                data[name] = hist.tolist()
        return HistogramDialog(data, parent)


class ImageStatsDialog(QDialog):
    """Display per-channel image statistics (min, max, mean, std, median)."""

    def __init__(
        self,
        stats: "dict[str, dict[str, float]]",
        image_info: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            stats: {channel → {stat_name → value}}
            image_info: optional header string (e.g. "800×600 RGB 8-bit")
        """
        super().__init__(parent)
        self.setWindowTitle("Image Statistics")
        self.setModal(False)
        self.setMinimumSize(400, 300)

        from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem

        layout = QVBoxLayout(self)
        if image_info:
            header = QLabel(f"<b>{image_info}</b>")
            layout.addWidget(header)

        channels = list(stats.keys())
        stat_names = ["min", "max", "mean", "std", "median"]
        table = QTableWidget(len(stat_names), len(channels))
        table.setHorizontalHeaderLabels(channels)
        table.setVerticalHeaderLabels(stat_names)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for col, ch in enumerate(channels):
            ch_stats = stats[ch]
            for row, sname in enumerate(stat_names):
                val = ch_stats.get(sname, float("nan"))
                item = QTableWidgetItem(f"{val:.2f}")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, col, item)

        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def from_buffer(
        arr: "object",
        image_info: str = "",
        parent: QWidget | None = None,
    ) -> "ImageStatsDialog":
        """Build an ImageStatsDialog by computing stats from a NumPy array."""
        import numpy as np  # type: ignore[import-untyped]

        a: np.ndarray = arr  # type: ignore[assignment]
        stat_names = ["min", "max", "mean", "std", "median"]
        stats: dict[str, dict[str, float]] = {}

        if a.ndim == 2:
            ch_data = a.astype(np.float64)
            stats["L"] = {
                "min": float(ch_data.min()),
                "max": float(ch_data.max()),
                "mean": float(ch_data.mean()),
                "std": float(ch_data.std()),
                "median": float(np.median(ch_data)),
            }
        elif a.ndim == 3:
            for i, name in enumerate(("R", "G", "B", "A")[: a.shape[2]]):
                ch_data = a[:, :, i].astype(np.float64)
                stats[name] = {
                    "min": float(ch_data.min()),
                    "max": float(ch_data.max()),
                    "mean": float(ch_data.mean()),
                    "std": float(ch_data.std()),
                    "median": float(np.median(ch_data)),
                }

        return ImageStatsDialog(stats, image_info, parent)


class ExportDialog(QDialog):
    """Dialog for choosing export format and quality before saving."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Image")
        self.setModal(True)
        self.setMinimumSize(380, 200)

        self._format = QComboBox()
        for format_name in ("PNG", "JPEG", "BMP", "TIFF", "PPM"):
            self._format.addItem(icon_for("file.new"), format_name)
        self._format.currentTextChanged.connect(self._on_format_change)

        self._quality_label_widget = __import__(
            "PySide6.QtWidgets", fromlist=["QLabel"]
        ).QLabel("Quality (JPEG):")
        self._quality = QSpinBox()
        self._quality.setRange(1, 100)
        self._quality.setValue(85)

        form = QFormLayout()
        form.addRow("Format", self._format)
        form.addRow(self._quality_label_widget, self._quality)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._on_format_change("PNG")

    def _on_format_change(self, fmt: str) -> None:
        visible = fmt == "JPEG"
        self._quality_label_widget.setVisible(visible)
        self._quality.setVisible(visible)

    def selected_format(self) -> str:
        return self._format.currentText().lower()

    def selected_quality(self) -> int:
        return self._quality.value()
