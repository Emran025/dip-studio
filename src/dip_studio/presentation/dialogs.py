"""Reusable dialogs and parameter controls for the desktop workspace."""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
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
        self._color_mode.addItems(["RGBA 8-bit", "RGB 8-bit", "Grayscale 8-bit"])

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

    def set_schema(self, schema: tuple[ParameterDefinition, ...]) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._controls.clear()
        self._definitions = schema
        if not schema:
            self._form.addRow("Parameters", QLineEdit("No parameters"))
            return
        for index, definition in enumerate(schema):
            control: QWidget
            if definition.kind == "integer":
                widget = QSpinBox()
                widget.setRange(int(definition.minimum), int(definition.maximum))
                widget.setValue(int(definition.default))
                control = widget
            elif definition.kind == "number":
                widget = QDoubleSpinBox()
                widget.setRange(definition.minimum, definition.maximum)
                widget.setValue(float(definition.default))
                control = widget
            elif definition.kind == "choice":
                widget = QComboBox()
                widget.addItems(list(definition.choices))
                widget.setCurrentText(str(definition.default))
                control = widget
            elif definition.kind == "boolean":
                widget = QCheckBox()
                widget.setChecked(bool(definition.default))
                control = widget
            else:
                widget = QLineEdit(str(definition.default))
                control = widget
            self._controls[str(index)] = control
            self._form.addRow(definition.label, control)
        self._actions = self._create_actions()
        self._form.addRow(self._actions)

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
            values[definition.label] = value
        return values

    def set_values(self, values: dict[str, object]) -> None:
        """Update control values programmatically by label or index."""
        label_to_index = {d.label.lower(): str(i) for i, d in enumerate(self._definitions)}
        for k, v in values.items():
            idx = label_to_index.get(str(k).lower())
            if idx and idx in self._controls:
                ctrl = self._controls[idx]
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


# ──────────────────────────── Analysis Dialogs ───────────────────────────────

class HistogramDialog(QDialog):
    """Display per-channel pixel intensity histogram using a simple Qt bar widget."""

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
        self.setMinimumSize(520, 360)
        self.resize(640, 400)

        self._data = histogram_data
        self._channel_selector = QComboBox()
        self._channel_selector.addItems(list(histogram_data.keys()))
        self._channel_selector.currentTextChanged.connect(self._refresh)

        from PySide6.QtWidgets import QLabel, QScrollArea

        self._chart_label = QLabel()
        self._chart_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self._chart_label.setMinimumSize(480, 256)

        scroll = QScrollArea()
        scroll.setWidget(self._chart_label)
        scroll.setWidgetResizable(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._channel_selector)
        layout.addWidget(scroll)
        layout.addWidget(buttons)

        self._refresh(self._channel_selector.currentText())

    def _refresh(self, channel: str) -> None:
        counts = self._data.get(channel, [])
        if not counts:
            self._chart_label.setText("No data")
            return
        max_count = max(counts) or 1
        bar_height = 200
        lines: list[str] = []
        # ASCII bar chart: one character column per 8 intensity bins
        for bucket in range(0, 256, 8):
            bucket_val = max(counts[bucket:bucket + 8]) if bucket + 8 <= len(counts) else 0
            bars = int(bucket_val / max_count * bar_height)
            lines.append(f"{bucket:3d} │{'█' * bars}")
        lines.append("    └" + "─" * 25 + " intensity →")
        self._chart_label.setText("\n".join(lines))
        self._chart_label.setFont(
            self._chart_label.font().__class__("Courier New", 8)
        )

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
        self._format.addItems(["PNG", "JPEG", "BMP", "TIFF", "PPM"])
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
