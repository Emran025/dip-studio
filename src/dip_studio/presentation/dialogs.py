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
        self.resize(520, 360)
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
        self.resize(620, 420)
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
        self._actions = QWidget()
        actions = QHBoxLayout(self._actions)
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
        self._empty = QLineEdit("Select a tool to edit parameters")
        self._empty.setReadOnly(True)
        self._form.addRow(self._empty)

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
