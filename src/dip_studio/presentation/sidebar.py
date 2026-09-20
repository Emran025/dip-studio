"""Photoshop-style right workspace sidebar with navigable panel tabs."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dip_studio.presentation.dialogs import ToolParametersPanel
from dip_studio.presentation.vector_icons import icon_for


class RightSidebar(QWidget):
    """Owns panel navigation, not document or processing state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.properties = ToolParametersPanel()
        self.layers = QListWidget()
        self.layers.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.layers.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.layers.customContextMenuRequested.connect(self._layer_context_menu)
        self._layer_structure_callback = None
        self._layer_rename_callback = None
        self.layer_opacity = QDoubleSpinBox()
        self.layer_opacity.setRange(0.0, 1.0)
        self.layer_opacity.setSingleStep(0.05)
        self.layer_opacity.setValue(1.0)
        self.layer_opacity.setPrefix("Opacity ")
        self.layers_data: tuple[object, ...] = ()
        self.layer_opacity.valueChanged.connect(self._opacity_changed)
        self.layers.currentRowChanged.connect(self._layer_selected)
        self.layers.itemChanged.connect(self._visibility_changed)
        self._layer_callback = None
        self.channels = QListWidget()
        self.channels.addItems(["RGB", "Red", "Green", "Blue", "Alpha"])
        self.navigator = QLabel("Fit: 100%")
        self.navigator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.history = QListWidget()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.addTab(self.properties, "Properties")
        self.tabs.addTab(self.layers, "Layers")
        self.tabs.addTab(self.channels, "Channels")
        self.tabs.addTab(self.navigator, "Navigator")
        self.tabs.addTab(self.history, "History")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        controls = QHBoxLayout()
        for icon_name, action, tooltip in (
            ("layer.add", "add", "Add layer"),
            ("layer.remove", "remove", "Remove selected layers"),
            ("layer.duplicate", "duplicate", "Duplicate selected layer"),
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
        self.layers.clear()
        selected_keys = {str(layer_id) for layer_id in selected_ids}
        for layer in layers:
            item = QListWidgetItem(layer.name)
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
                item.data(Qt.ItemDataRole.UserRole) for item in self.layers.selectedItems()
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
        rename = menu.addAction("Rename")
        duplicate = menu.addAction("Duplicate")
        menu.addSeparator()
        remove = menu.addAction("Remove selected")
        chosen = menu.exec(self.layers.viewport().mapToGlobal(position))
        if chosen is rename:
            self._rename_selected()
        elif chosen is duplicate:
            self._structure("duplicate")
        elif chosen is remove:
            self._structure("remove")

    def _rename_selected(self) -> None:
        item = self.layers.currentItem()
        if item is None or self._layer_rename_callback is None:
            return
        name, accepted = QInputDialog.getText(self, "Rename layer", "Layer name:", text=item.text())
        if accepted and name.strip():
            self._layer_rename_callback(item.data(Qt.ItemDataRole.UserRole), name.strip())

    def _layer_selected(self, row: int) -> None:
        if 0 <= row < self.layers.count():
            self.layer_opacity.blockSignals(True)
            item = self.layers.item(row)
            layer = next(
                (
                    candidate
                    for candidate in self.layers_data
                    if candidate.id == item.data(Qt.ItemDataRole.UserRole)
                ),
                None,
            )
            if layer is not None:
                self.layer_opacity.setValue(layer.opacity)
            self.layer_opacity.blockSignals(False)

    def _visibility_changed(self, item: QListWidgetItem) -> None:
        if self._layer_callback is not None:
            selected = tuple(
                selected_item.data(Qt.ItemDataRole.UserRole)
                for selected_item in self.layers.selectedItems()
            )
            self._layer_callback(
                selected or (item.data(Qt.ItemDataRole.UserRole),),
                item.checkState() == Qt.CheckState.Checked,
                None,
            )

    def _opacity_changed(self, value: float) -> None:
        if self._layer_callback is not None and self.layers.currentRow() >= 0:
            item = self.layers.currentItem()
            if item is not None:
                selected = tuple(
                    selected_item.data(Qt.ItemDataRole.UserRole)
                    for selected_item in self.layers.selectedItems()
                )
                self._layer_callback(
                    selected or (item.data(Qt.ItemDataRole.UserRole),),
                    None,
                    value,
                )

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

    def select_panel(self, name: str) -> None:
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.setCurrentIndex(index)
                return
