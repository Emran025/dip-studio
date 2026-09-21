"""Photoshop-style right workspace sidebar with navigable panel tabs."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dip_studio.presentation.dialogs import ToolParametersPanel
from dip_studio.presentation.panel_group import PanelGroup
from dip_studio.presentation.vector_icons import icon_for


class RightSidebar(QWidget):
    """Owns panel navigation, not document or processing state."""

    layerSelectionChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.properties = ToolParametersPanel()

        # Layers panel container and controls
        self.layers = QListWidget()
        self.layers.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.layers.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.layers.customContextMenuRequested.connect(self._layer_context_menu)
        self._layer_structure_callback = None
        self._layer_rename_callback = None
        self.layers_data: tuple[object, ...] = ()

        # Layer controls: Blend Mode, Lock, Opacity
        self.layer_blend_mode = QComboBox()
        self.layer_blend_mode.addItems([
            "Normal",
            "Multiply",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Darken",
            "Lighten",
            "Difference",
        ])
        self.layer_blend_mode.currentTextChanged.connect(self._blend_mode_changed)

        self.layer_lock_button = QToolButton()
        self.layer_lock_button.setIcon(icon_for("layer.unlock"))
        self.layer_lock_button.setIconSize(QSize(14, 14))
        self.layer_lock_button.setToolTip("Lock / Unlock selected layer")
        self.layer_lock_button.setCheckable(True)
        self.layer_lock_button.setFixedSize(30, 26)
        self.layer_lock_button.clicked.connect(self._lock_toggled)

        self.layer_opacity = QDoubleSpinBox()
        self.layer_opacity.setRange(0.0, 1.0)
        self.layer_opacity.setSingleStep(0.05)
        self.layer_opacity.setValue(1.0)
        self.layer_opacity.setPrefix("Opacity ")
        self.layer_opacity.valueChanged.connect(self._opacity_changed)

        self.layers.currentRowChanged.connect(self._layer_selected)
        self.layers.itemClicked.connect(lambda item: self._layer_selected(self.layers.row(item)))
        self.layers.itemChanged.connect(self._visibility_changed)
        self._layer_callback = None

        self.channels = QListWidget()
        self.channels.addItems(["RGB", "Red", "Green", "Blue", "Alpha"])
        self.navigator = QLabel()
        self.navigator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.navigator.setText("No document")
        self.navigator.setMinimumHeight(120)
        self.history = QListWidget()

        self.tabs = PanelGroup()
        self.tabs.add_panel(self.properties, "Properties")
        self.tabs.add_panel(self.layers, "Layers")
        self.tabs.add_panel(self.channels, "Channels")
        self.tabs.add_panel(self.navigator, "Navigator")
        self.tabs.add_panel(self.history, "History")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        # Layer mode & lock header
        header = QHBoxLayout()
        header.addWidget(self.layer_blend_mode, stretch=1)
        header.addWidget(self.layer_lock_button)
        layout.addLayout(header)

        # Layer structure action buttons
        controls = QHBoxLayout()
        for icon_name, action, tooltip in (
            ("layer.add", "add", "Add layer"),
            ("layer.remove", "remove", "Remove selected layers"),
            ("layer.duplicate", "duplicate", "Duplicate selected layer"),
            ("layer.merge", "merge_down", "Merge layer down"),
            ("layer.up", "up", "Move layer up"),
            ("layer.down", "down", "Move layer down"),
        ):
            button = QToolButton()
            button.setObjectName("layerActionButton")
            button.setIcon(icon_for(icon_name))
            button.setIconSize(QSize(12, 12))
            button.setFixedSize(36, 30)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _checked=False, value=action: self._structure(value))
            controls.addWidget(button)
        layout.addLayout(controls)
        layout.addWidget(self.layer_opacity)

    def show_layers(
        self,
        layers: tuple[object, ...],
        selected_ids: tuple[object, ...] = (),
    ) -> None:
        self.layers_data = layers
        self.layers.blockSignals(True)
        self.layer_opacity.blockSignals(True)
        self.layer_blend_mode.blockSignals(True)
        self.layer_lock_button.blockSignals(True)
        self.layers.clear()
        selected_keys = {str(layer_id) for layer_id in selected_ids}
        for layer in layers:
            item = QListWidgetItem(layer.name)
            if getattr(layer, "locked", False):
                item.setIcon(icon_for("layer.lock"))
            item.setData(Qt.ItemDataRole.UserRole, layer.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked
            )
            self.layers.addItem(item)
            if str(layer.id) in selected_keys:
                item.setSelected(True)
        selected_items = self.layers.selectedItems()
        if selected_items:
            self.layers.setCurrentItem(selected_items[0])
        elif layers:
            self.layers.setCurrentRow(0)
        current = self.layers.currentItem()
        if current is not None:
            current_layer = next(
                (
                    layer
                    for layer in layers
                    if str(layer.id) == str(current.data(Qt.ItemDataRole.UserRole))
                ),
                None,
            )
            if current_layer is not None:
                self.layer_opacity.setValue(current_layer.opacity)
                blend = getattr(current_layer, "blend_mode", "normal")
                self.layer_blend_mode.setCurrentText(blend.title())
                is_locked = getattr(current_layer, "locked", False)
                self.layer_lock_button.setChecked(is_locked)
                self.layer_lock_button.setIcon(
                    icon_for("layer.lock" if is_locked else "layer.unlock")
                )
        self.layer_lock_button.blockSignals(False)
        self.layer_blend_mode.blockSignals(False)
        self.layer_opacity.blockSignals(False)
        self.layers.blockSignals(False)

    def set_layer_callback(self, callback) -> None:
        self._layer_callback = callback

    def set_layer_structure_callback(self, callback) -> None:
        self._layer_structure_callback = callback

    def set_layer_rename_callback(self, callback) -> None:
        self._layer_rename_callback = callback

    def rename_selected_layer(self) -> None:
        self._rename_selected()

    def _structure(self, action: str) -> None:
        item = self.layers.currentItem()
        if self._layer_structure_callback is not None:
            selected = tuple(
                it.data(Qt.ItemDataRole.UserRole) for it in self.layers.selectedItems()
            )
            self._layer_structure_callback(
                action,
                selected if selected else ((item.data(Qt.ItemDataRole.UserRole),) if item else ()),
            )

    def _layer_context_menu(self, position: object) -> None:
        item = self.layers.itemAt(position)
        if item is not None and not item.isSelected():
            self.layers.setCurrentItem(item)
        menu = QMenu(self)
        copy_sel = menu.addAction("New Layer via Copy (Ctrl+J)")
        cut_sel = menu.addAction("New Layer via Cut (Ctrl+Shift+J)")
        menu.addSeparator()
        merge = menu.addAction("Merge Down (Ctrl+E)")
        duplicate = menu.addAction("Duplicate Layer")
        rename = menu.addAction("Rename Layer")
        toggle_lock = menu.addAction("Toggle Lock")
        menu.addSeparator()
        remove = menu.addAction("Remove Selected")
        chosen = menu.exec(self.layers.viewport().mapToGlobal(position))
        if chosen is copy_sel:
            self._structure("copy_selection")
        elif chosen is cut_sel:
            self._structure("cut_selection")
        elif chosen is merge:
            self._structure("merge_down")
        elif chosen is duplicate:
            self._structure("duplicate")
        elif chosen is rename:
            self._rename_selected()
        elif chosen is toggle_lock:
            self._structure("toggle_lock")
        elif chosen is remove:
            self._structure("remove")

    def _rename_selected(self) -> None:
        item = self.layers.currentItem()
        if item is None or self._layer_rename_callback is None:
            return
        current_name = item.text()
        name, accepted = QInputDialog.getText(
            self, "Rename layer", "Layer name:", text=current_name
        )
        if accepted and name.strip():
            self._layer_rename_callback(item.data(Qt.ItemDataRole.UserRole), name.strip())

    def _layer_selected(self, row: int) -> None:
        if 0 <= row < self.layers.count():
            item = self.layers.item(row)
            if item is not None:
                self.layerSelectionChanged.emit(item.data(Qt.ItemDataRole.UserRole))
            self.layer_opacity.blockSignals(True)
            self.layer_blend_mode.blockSignals(True)
            self.layer_lock_button.blockSignals(True)
            layer = next(
                (
                    candidate
                    for candidate in self.layers_data
                    if candidate.id == item.data(Qt.ItemDataRole.UserRole)
                ),
                None,
            ) if item is not None else None
            if layer is not None:
                self.layer_opacity.setValue(layer.opacity)
                blend = getattr(layer, "blend_mode", "normal")
                self.layer_blend_mode.setCurrentText(blend.title())
                is_locked = getattr(layer, "locked", False)
                self.layer_lock_button.setChecked(is_locked)
                self.layer_lock_button.setIcon(
                    icon_for("layer.lock" if is_locked else "layer.unlock")
                )
            self.layer_lock_button.blockSignals(False)
            self.layer_blend_mode.blockSignals(False)
            self.layer_opacity.blockSignals(False)

    def _visibility_changed(self, item: QListWidgetItem) -> None:
        if self._layer_callback is not None:
            selected = tuple(
                it.data(Qt.ItemDataRole.UserRole) for it in self.layers.selectedItems()
            )
            self._layer_callback(
                selected or (item.data(Qt.ItemDataRole.UserRole),),
                item.checkState() == Qt.CheckState.Checked,
                None,
                None,
                None,
            )

    def _opacity_changed(self, value: float) -> None:
        if self._layer_callback is not None and self.layers.currentRow() >= 0:
            item = self.layers.currentItem()
            if item is not None:
                selected = tuple(
                    it.data(Qt.ItemDataRole.UserRole) for it in self.layers.selectedItems()
                )
                self._layer_callback(
                    selected or (item.data(Qt.ItemDataRole.UserRole),),
                    None,
                    value,
                    None,
                    None,
                )

    def _blend_mode_changed(self, mode_text: str) -> None:
        if self._layer_callback is not None and self.layers.currentRow() >= 0:
            item = self.layers.currentItem()
            if item is not None:
                lid = item.data(Qt.ItemDataRole.UserRole)
                self._layer_callback((lid,), None, None, mode_text.lower(), None)

    def _lock_toggled(self, checked: bool) -> None:
        self.layer_lock_button.setIcon(icon_for("layer.lock" if checked else "layer.unlock"))
        if self._layer_callback is not None and self.layers.currentRow() >= 0:
            item = self.layers.currentItem()
            if item is not None:
                lid = item.data(Qt.ItemDataRole.UserRole)
                self._layer_callback((lid,), None, None, None, checked)

    def selected_layer_id(self) -> object | None:
        item = self.layers.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def selected_layer_ids(self) -> tuple[object, ...]:
        return tuple(
            item.data(Qt.ItemDataRole.UserRole) for item in self.layers.selectedItems()
        )

    def select_layer(self, layer_id: object) -> None:
        for row in range(self.layers.count()):
            item = self.layers.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == str(layer_id):
                self.layers.setCurrentItem(item)
                return

    def add_history(self, label: str) -> None:
        self.history.addItem(label)

    def set_history_states(self, labels: list[str], current_index: int) -> None:
        """Refresh the history panel to reflect actual undo/redo stack."""
        self.history.blockSignals(True)
        self.history.clear()
        for i, label in enumerate(labels):
            item = QListWidgetItem(label)
            if i == current_index:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.history.addItem(item)
        if 0 <= current_index < self.history.count():
            self.history.setCurrentRow(current_index)
        self.history.blockSignals(False)

    def set_history_jump_callback(self, callback) -> None:
        """callback(index: int) -> None called when user clicks a history entry."""
        self._history_jump_callback = callback
        self.history.currentRowChanged.connect(self._history_row_changed)

    def _history_row_changed(self, row: int) -> None:
        if hasattr(self, '_history_jump_callback') and self._history_jump_callback is not None:
            self._history_jump_callback(row)

    def set_channel_callback(self, callback) -> None:
        """callback(row: int) -> None called when user selects a channel."""
        self._channel_callback = callback
        self.channels.currentRowChanged.connect(self._channel_row_changed)

    def _channel_row_changed(self, row: int) -> None:
        if hasattr(self, '_channel_callback') and self._channel_callback is not None:
            self._channel_callback(row)

    def update_navigator(self, thumbnail_data: bytes | None, zoom: float) -> None:
        """Update navigator thumbnail and zoom label."""
        if thumbnail_data is None:
            self.navigator.setText(f"Zoom: {zoom*100:.0f}%")
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(thumbnail_data):
            scaled = pixmap.scaled(
                200, 120,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.navigator.setPixmap(scaled)
        self.navigator.setToolTip(f"Zoom: {zoom*100:.0f}%")

    def select_panel(self, name: str) -> None:
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.setCurrentIndex(index)
                return
