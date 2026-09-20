"""Theme-aware Qt workspace composition; editor behavior stays in application."""

import json
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QByteArray, QEvent, QPoint, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QImage, QKeyEvent, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QToolBar,
    QWidget,
)

from dip_studio.application.editor import EditorController
from dip_studio.application.input_dispatcher import (
    FocusState,
    InputDispatcher,
)
from dip_studio.application.shortcut_profiles import (
    CUSTOM_PROFILE,
    DEFAULT_PROFILE,
    PROFILE_NAMES,
    create_profile_registry,
)
from dip_studio.application.shortcut_registry import (
    ShortcutBinding,
    default_shortcut_registry,
)
from dip_studio.presentation.dialogs import (
    CommandPaletteDialog,
    NewProjectDialog,
    ParameterDefinition,
    ShortcutEditorDialog,
)
from dip_studio.presentation.sidebar import RightSidebar
from dip_studio.presentation.theme import DARK, LIGHT
from dip_studio.presentation.theme_adapter import palette_for
from dip_studio.rendering.ports import BlankDocumentRenderer


class ImageView(Protocol):
    width: int
    height: int


class LayerView(Protocol):
    id: object
    name: str
    visible: bool
    opacity: float


class DocumentView(Protocol):
    name: str
    image: ImageView
    layers: tuple[LayerView, ...]
    is_dirty: bool


class CanvasView(QWidget):
    """Read-only preview surface fed by rendered bytes."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(320, 240)
        self.setObjectName("canvas")
        self._source_image: QImage | None = None
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._grid_enabled = False
        self._show_before = False
        self._pan = QPoint()
        self._drag_start: QPoint | None = None
        self.__space_pan = False

    def show_preview(self, data: bytes) -> None:
        image = QImage()
        if not image.loadFromData(data, "PPM"):
            raise ValueError("Renderer returned an invalid preview frame")
        self._source_image = image
        self._render_zoomed()

    def set_grid_enabled(self, enabled: bool) -> None:
        self._grid_enabled = enabled
        self.update()

    def set_before_after(self, show_before: bool) -> None:
        self._show_before = show_before
        self.update()

    def mousePressEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton and (
            self._space_pan or event.button() == Qt.MouseButton.LeftButton
        ):
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        if self._drag_start is not None:
            current = event.position().toPoint()
            self._pan += current - self._drag_start
            self._drag_start = current
            self._clamp_pan()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: object) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: object) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def wheelEvent(self, event: object) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    @property
    def zoom(self) -> float:
        return self._zoom

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    def fit_to_view(self) -> None:
        if self._source_image is None:
            return
        width_ratio = max(0.1, (self.width() - 24) / self._source_image.width())
        height_ratio = max(0.1, (self.height() - 24) / self._source_image.height())
        self.set_zoom(min(width_ratio, height_ratio))

    def set_zoom(self, zoom: float) -> None:
        self._zoom = min(8.0, max(0.1, zoom))
        self._clamp_pan()
        self._render_zoomed()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if self._source_image is not None:
            self._render_zoomed()

    def _render_zoomed(self) -> None:
        if self._source_image is None:
            return
        size = self._source_image.size()
        size.setWidth(max(1, round(size.width() * self._zoom)))
        size.setHeight(max(1, round(size.height() * self._zoom)))
        pixmap = QPixmap.fromImage(self._source_image).scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._pixmap = pixmap
        self._clamp_pan()
        self.update()

    def _clamp_pan(self) -> None:
        if self._pixmap is None:
            self._pan = QPoint()
            return
        max_x = max(0, (self._pixmap.width() - self.width()) // 2)
        max_y = max(0, (self._pixmap.height() - self.height()) // 2)
        self._pan.setX(max(-max_x, min(max_x, self._pan.x())))
        self._pan.setY(max(-max_y, min(max_y, self._pan.y())))

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.darkGray)
        if self._grid_enabled:
            painter.setPen(Qt.GlobalColor.gray)
            for x in range(0, self.width(), 16):
                painter.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), 16):
                painter.drawLine(0, y, self.width(), y)
        if self._pixmap is None:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Create a document to start")
            return
        x = (self.width() - self._pixmap.width()) // 2 + self._pan.x()
        y = (self.height() - self._pixmap.height()) // 2 + self._pan.y()
        if self._show_before:
            painter.setOpacity(0.45)
        painter.drawPixmap(x, y, self._pixmap)


class MainWindow(QMainWindow):
    def __init__(self, controller: EditorController | None = None) -> None:
        super().__init__()
        self._controller = controller or EditorController(BlankDocumentRenderer())
        self._profile_name = DEFAULT_PROFILE
        self._shortcuts = default_shortcut_registry()
        self._default_shortcuts = default_shortcut_registry()
        self._input_dispatcher = InputDispatcher(self._shortcuts)
        self._shortcut_load_rejections: tuple[str, ...] = ()
        self._load_shortcut_profile()
        self._load_shortcut_overrides()
        self._project_path: Path | None = None
        self._tokens = DARK
        self._canvas = CanvasView()
        self.setWindowTitle("DIP Studio")
        self.resize(1200, 760)
        self.setCentralWidget(self._canvas)
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_docks()
        self._register_input_handlers()
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        self._apply_theme()
        self._restore_workspace()
        if self._shortcut_load_rejections:
            self.statusBar().showMessage(
                "Some saved shortcuts were ignored because they are invalid or unavailable"
            )

    def _create_actions(self) -> None:
        self._new_action = QAction("New", self)
        self._new_action.setShortcut(QKeySequence(self._shortcut("file.new")))
        self._new_action.triggered.connect(self._show_new_project)
        self._open_project_action = QAction("Open project...", self)
        self._open_project_action.triggered.connect(self._open_project)
        self._save_project_action = QAction("Save project", self)
        self._save_project_action.setShortcut(QKeySequence(self._shortcut("file.save")))
        self._save_project_action.triggered.connect(self._save_project)
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence(self._shortcut("edit.undo")))
        self._undo_action.triggered.connect(self._undo)
        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence(self._shortcut("edit.redo")))
        self._redo_action.triggered.connect(self._redo)
        self._add_layer_action = QAction("Add layer", self)
        self._add_layer_action.setShortcut(QKeySequence(self._shortcut("layer.add")))
        self._add_layer_action.triggered.connect(self._add_layer)
        self._duplicate_layer_action = QAction("Duplicate layer", self)
        self._duplicate_layer_action.setShortcut(QKeySequence(self._shortcut("layer.duplicate")))
        self._duplicate_layer_action.triggered.connect(self._duplicate_selected_layer)
        self._remove_layer_action = QAction("Remove selected layers", self)
        self._remove_layer_action.setShortcut(QKeySequence(self._shortcut("layer.remove")))
        self._remove_layer_action.triggered.connect(self._remove_selected_layers)
        self._move_layer_up_action = QAction("Move layer up", self)
        self._move_layer_up_action.setShortcut(QKeySequence(self._shortcut("layer.move_up")))
        self._move_layer_up_action.triggered.connect(lambda: self._move_selected_layer(-1))
        self._move_layer_down_action = QAction("Move layer down", self)
        self._move_layer_down_action.setShortcut(QKeySequence(self._shortcut("layer.move_down")))
        self._move_layer_down_action.triggered.connect(lambda: self._move_selected_layer(1))
        self._toggle_layer_visibility_action = QAction("Toggle layer visibility", self)
        self._toggle_layer_visibility_action.setShortcut(QKeySequence(self._shortcut("layer.toggle_visibility")))
        self._toggle_layer_visibility_action.triggered.connect(self._toggle_selected_visibility)
        self._rename_layer_action = QAction("Rename selected layer", self)
        self._rename_layer_action.setShortcut(QKeySequence(self._shortcut("layer.rename")))
        self._rename_layer_action.triggered.connect(self._rename_selected_layer)
        self._theme_action = QAction("Toggle theme", self)
        self._theme_action.triggered.connect(self._toggle_theme)
        self._command_action = QAction("Command palette", self)
        self._command_action.setShortcut(QKeySequence(self._shortcut("application.command_palette")))
        self._command_action.triggered.connect(self._show_command_palette)
        self._shortcut_editor_action = QAction("Keyboard shortcuts", self)
        self._shortcut_editor_action.triggered.connect(self._show_shortcut_editor)
        self._zoom_in_action = QAction("Zoom in", self)
        self._zoom_in_action.setShortcut(QKeySequence(self._shortcut("canvas.zoom_in")))
        self._zoom_in_action.triggered.connect(self._zoom_in)
        self._zoom_out_action = QAction("Zoom out", self)
        self._zoom_out_action.setShortcut(QKeySequence(self._shortcut("canvas.zoom_out")))
        self._zoom_out_action.triggered.connect(self._zoom_out)
        self._fit_action = QAction("Fit canvas", self)
        self._fit_action.triggered.connect(self._fit_canvas)
        self._actual_size_action = QAction("Actual size", self)
        self._actual_size_action.triggered.connect(self._actual_size)
        self._grid_action = QAction("Show grid", self)
        self._grid_action.setCheckable(True)
        self._grid_action.triggered.connect(self._toggle_grid)
        self._before_after_action = QAction("Before/after", self)
        self._before_after_action.setCheckable(True)
        self._before_after_action.triggered.connect(self._toggle_before_after)
        self._workspace_action = QAction("Workspace sidebar", self)
        self._workspace_action.setCheckable(True)
        self._workspace_action.setChecked(True)
        self._workspace_action.triggered.connect(self._toggle_workspace_sidebar)
        self._tool_actions: tuple[QAction, ...] = tuple(
            self._make_tool_action(tool.id, tool.name, tool.shortcut)
            for tool in self._controller.tools
            if tool.shortcut
        )

    def _register_input_handlers(self) -> None:
        handlers = {
            "file.new": self._show_new_project,
            "file.save": self._save_project,
            "edit.undo": self._undo,
            "edit.redo": self._redo,
            "layer.add": self._add_layer,
            "layer.duplicate": self._duplicate_selected_layer,
            "layer.remove": self._remove_selected_layers,
            "layer.move_up": lambda: self._move_selected_layer(-1),
            "layer.move_down": lambda: self._move_selected_layer(1),
            "layer.toggle_visibility": self._toggle_selected_visibility,
            "layer.rename": self._rename_selected_layer,
            "application.command_palette": self._show_command_palette,
            "canvas.zoom_in": self._zoom_in,
            "canvas.zoom_out": self._zoom_out,
        }
        for command_id, handler in handlers.items():
            self._input_dispatcher.register(command_id, handler)
        for tool in self._controller.tools:
            if tool.shortcut:
                self._input_dispatcher.register(
                    f"tool.{tool.id}",
                    lambda name=tool.name: self._select_tool(name),
                )

    def _focus_state(self, widget: QWidget | None) -> FocusState:
        if widget is None:
            return FocusState()
        if isinstance(widget, (QLineEdit, QTextEdit, QAbstractSpinBox, QComboBox)):
            return FocusState(input_field=True)
        if isinstance(widget, QDialog) or self.activeModalWidget() is not None:
            return FocusState(modal_dialog=True)
        if self._sidebar.isAncestorOf(widget):
            return FocusState(panel_context="Layer Panel")
        return FocusState(canvas=self._canvas.isAncestorOf(widget) or widget is self._canvas)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return super().eventFilter(watched, event)
        if event.isAutoRepeat():
            return super().eventFilter(watched, event)
        widget = QApplication.focusWidget()
        state = self._focus_state(widget)
        if state.input_field or state.modal_dialog:
            return super().eventFilter(watched, event)
        key = QKeySequence(event.modifiers() | Qt.KeyboardModifier(event.key())).toString()
        if not key:
            return super().eventFilter(watched, event)
        if self._input_dispatcher.dispatch(key, state) is None:
            return super().eventFilter(watched, event)
        event.accept()
        return True

    def _shortcut(self, command_id: str) -> str:
        return self._shortcuts.get(command_id).key

    def _make_tool_action(self, tool_id: str, name: str, shortcut: str | None) -> QAction:
        action = QAction(f"Tool: {name}", self)
        if shortcut is not None:
            command_id = f"tool.{tool_id}"
            try:
                shortcut = self._shortcuts.get(command_id).key
            except KeyError:
                self._shortcuts.register(ShortcutBinding(command_id, shortcut, "Tool", 20))
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False, value=name: self._select_tool(value))
        return action

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self._new_action)
        file_menu.addAction(self._open_project_action)
        file_menu.addAction(self._save_project_action)
        file_menu.addAction("Open image...", self._open_image)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self._theme_action)
        view_menu.addAction(self._command_action)
        view_menu.addAction(self._shortcut_editor_action)
        profile_menu = view_menu.addMenu("Shortcut profile")
        for profile_name in PROFILE_NAMES:
            action = profile_menu.addAction(profile_name)
            action.setCheckable(True)
            action.setChecked(profile_name == self._profile_name)
            action.triggered.connect(
                lambda _checked=False, name=profile_name: self._switch_shortcut_profile(name)
            )
        self._profile_actions = {
            action.text(): action
            for action in profile_menu.actions()
        }
        view_menu.addAction(self._workspace_action)
        view_menu.addSeparator()
        view_menu.addAction(self._zoom_in_action)
        view_menu.addAction(self._zoom_out_action)
        view_menu.addAction(self._fit_action)
        view_menu.addAction(self._actual_size_action)
        view_menu.addAction(self._grid_action)
        view_menu.addAction(self._before_after_action)
        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._add_layer_action)
        edit_menu.addAction(self._duplicate_layer_action)
        edit_menu.addAction(self._remove_layer_action)
        edit_menu.addAction(self._move_layer_up_action)
        edit_menu.addAction(self._move_layer_down_action)
        edit_menu.addAction(self._toggle_layer_visibility_action)
        edit_menu.addAction(self._rename_layer_action)
        window_menu = self.menuBar().addMenu("Window")
        window_menu.addAction(self._workspace_action)
        window_menu.addSeparator()
        for panel_name in ("Properties", "Layers", "Channels", "Navigator", "History"):
            action = window_menu.addAction(panel_name)
            action.triggered.connect(
                lambda checked=False, name=panel_name: self._select_workspace_panel(name)
            )
        window_menu.addSeparator()
        window_menu.addAction("Save workspace", self._save_workspace)
        window_menu.addAction("Reset workspace", self._reset_workspace)
        for name in ("Image", "Layer", "Select", "Filter", "Analysis", "Help"):
            self.menuBar().addMenu(name)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main toolbar", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.addAction(self._new_action)
        toolbar.addAction(self._command_action)
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self._zoom_out_action)
        toolbar.addAction(self._fit_action)
        toolbar.addAction(self._zoom_in_action)
        toolbar.addAction(self._grid_action)
        for action in self._tool_actions:
            self.addAction(action)
        self.addToolBar(toolbar)

    def _create_docks(self) -> None:
        tools = QListWidget()
        for tool in self._controller.tools:
            tools.addItem(tool.name)
        self._tools_dock = self._dock("Tools", tools)
        self._sidebar = RightSidebar()
        self._workspace_dock = self._dock("Workspace", self._sidebar)
        self._sidebar.set_layer_callback(self._change_layer)
        self._sidebar.set_layer_structure_callback(self._change_layer_structure)
        self._sidebar.set_layer_rename_callback(self._rename_layer)
        self._tools_dock.widget().currentTextChanged.connect(self._select_tool)
        self._sidebar.properties.previewRequested.connect(self._preview_parameters)
        self._sidebar.properties.applyRequested.connect(self._apply_parameters)
        self._sidebar.properties.cancelRequested.connect(self._cancel_parameters)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tools_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._workspace_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dock("Timeline", QLabel("Timeline")))

    def _dock(self, title: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"{title.lower()}Dock")
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.AllDockWidgetFeatures)
        return dock

    def _create_blank_document(self) -> None:
        if not self._confirm_document_transition():
            return
        document = self._controller.create_document("Untitled", 800, 600)
        self._show_document(document, "Created blank document")
        self._project_path = None

    def _show_new_project(self) -> None:
        if not self._confirm_document_transition():
            return
        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            document = self._controller.create_document(values.name, values.width, values.height)
            self._show_document(document, "Created project")
            self._project_path = None
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "New project failed", str(error))

    def _select_tool(self, name: str) -> None:
        tool = next((item for item in self._controller.tools if item.name == name), None)
        if tool is None:
            self._sidebar.properties.set_schema(())
            return
        schema = tuple(
            ParameterDefinition(
                parameter.label,
                parameter.kind,
                parameter.default,
                parameter.minimum,
                parameter.maximum,
                parameter.choices,
            )
            for parameter in tool.parameters
        )
        self._sidebar.properties.set_schema(schema)
        self._sidebar.select_panel("Properties")

    def _change_layer(
        self, layer_ids: tuple[object, ...], visible: bool | None, opacity: float | None
    ) -> None:
        try:
            if visible is not None:
                document = self._controller.set_layers_visibility(layer_ids, visible)
                label = "Shown" if visible else "Hidden"
            elif opacity is not None:
                document = self._controller.set_layers_opacity(layer_ids, opacity)
                label = f"Opacity {opacity:.0%}"
            else:
                return
            self._sidebar.add_history(f"{label} layer")
            self._sidebar.show_layers(document.layers, layer_ids)
            self._update_window_title(document)
            self.statusBar().showMessage(f"{label} layer")
        except (IndexError, KeyError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Layer update failed", str(error))

    def _change_layer_structure(self, action: str, layer_ids: tuple[object, ...]) -> None:
        try:
            previous_ids = set(layer_ids)
            existing_ids = (
                {layer.id for layer in self._controller.document.layers}
                if self._controller.document is not None
                else set()
            )
            if action == "add":
                document = self._controller.add_layer()
                label = "Added layer"
                selected_ids = (document.layers[-1].id,)
            elif not layer_ids:
                return
            elif action == "remove":
                document = self._controller.remove_layers(layer_ids)
                label = "Removed selected layers"
                selected_ids = tuple(layer.id for layer in document.layers if layer.id in previous_ids)
            elif action == "duplicate":
                document = self._controller.duplicate_layer(layer_ids[0])
                label = "Duplicated layer"
                selected_ids = (next(layer.id for layer in document.layers if layer.id not in existing_ids),)
            elif action == "up":
                document = self._controller.move_layer(layer_ids[0], -1)
                label = "Moved layer up"
                selected_ids = layer_ids
            elif action == "down":
                document = self._controller.move_layer(layer_ids[0], 1)
                label = "Moved layer down"
                selected_ids = layer_ids
            else:
                return
            self._show_document(document, label, selected_ids)
        except (IndexError, KeyError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Layer update failed", str(error))

    def _selected_layer_ids(self) -> tuple[object, ...]:
        return self._sidebar.selected_layer_ids()

    def _add_layer(self) -> None:
        try:
            document = self._controller.add_layer()
            self._show_document(document, "Added layer", (document.layers[-1].id,))
        except (ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Layer update failed", str(error))

    def _duplicate_selected_layer(self) -> None:
        selected = self._selected_layer_ids()
        if selected:
            self._change_layer_structure("duplicate", selected)

    def _remove_selected_layers(self) -> None:
        selected = self._selected_layer_ids()
        if selected:
            self._change_layer_structure("remove", selected)

    def _move_selected_layer(self, delta: int) -> None:
        selected = self._selected_layer_ids()
        if selected:
            self._change_layer_structure("up" if delta < 0 else "down", selected[:1])

    def _toggle_selected_visibility(self) -> None:
        selected = self._selected_layer_ids()
        document = self._controller.document
        if not selected or document is None:
            return
        selected_layers = tuple(layer for layer in document.layers if layer.id in selected)
        visible = not all(layer.visible for layer in selected_layers)
        self._change_layer(selected, visible, None)

    def _rename_layer(self, layer_id: object, name: str) -> None:
        try:
            document = self._controller.rename_layer(layer_id, name)
            self._show_document(document, "Renamed layer")
        except (KeyError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Layer rename failed", str(error))

    def _rename_selected_layer(self) -> None:
        if self._selected_layer_ids():
            self._sidebar.rename_selected_layer()

    def _preview_parameters(self, values: dict[str, object]) -> None:
        tool = self._tools_dock.widget().currentItem()
        if tool is not None:
            try:
                self._controller.preview_processing(tool.text().lower(), values)
                self.statusBar().showMessage(f"Preview parameters: {', '.join(values)}")
            except (KeyError, ValueError, RuntimeError) as error:
                QMessageBox.critical(self, "Preview failed", str(error))

    def _apply_parameters(self, values: dict[str, object]) -> None:
        tool = self._tools_dock.widget().currentItem()
        if tool is not None:
            try:
                document = self._controller.apply_processing(tool.text().lower(), values)
                self._sidebar.add_history(f"Applied parameters: {tool.text()}")
                self._show_document(document, f"Applied {tool.text()}")
            except (KeyError, ValueError, RuntimeError) as error:
                QMessageBox.critical(self, "Apply failed", str(error))

    def _cancel_parameters(self) -> None:
        tool = self._tools_dock.widget().currentItem()
        if tool is not None:
            self._sidebar.add_history(f"Cancelled parameters: {tool.text()}")
            self.statusBar().showMessage("Parameter preview cancelled")

    def _undo(self) -> None:
        try:
            document = self._controller.undo()
            self._show_document(document, "Undo")
        except RuntimeError as error:
            QMessageBox.information(self, "Undo", str(error))

    def _redo(self) -> None:
        try:
            document = self._controller.redo()
            self._show_document(document, "Redo")
        except RuntimeError as error:
            QMessageBox.information(self, "Redo", str(error))

    def _open_project(self) -> None:
        if not self._confirm_document_transition():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open project", "", "DIP projects (*.dip);;All files (*)"
        )
        if not filename:
            return
        try:
            document = self._controller.open_project(Path(filename))
            self._project_path = Path(filename)
            self._show_document(document, "Opened project")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Open project failed", str(error))

    def _save_project(self) -> bool:
        path = self._project_path
        if path is None:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save project", "", "DIP projects (*.dip);;All files (*)"
            )
            if not filename:
                return False
            path = Path(filename)
            if path.suffix.lower() != ".dip":
                path = path.with_suffix(".dip")
        try:
            document = self._controller.save_project(path)
            self._project_path = path
            self._show_document(document, "Saved project")
            return True
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, "Save project failed", str(error))
            return False

    def _open_image(self) -> None:
        if not self._confirm_document_transition():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open image", "", "Images (*.ppm);;All files (*)"
        )
        if not filename:
            return
        try:
            document = self._controller.open_image(Path(filename))
            self._project_path = None
            self._show_document(document, "Opened image")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Open image failed", str(error))

    def _show_document(
        self,
        document: DocumentView,
        history_label: str,
        selected_ids: tuple[object, ...] = (),
    ) -> None:
        if not selected_ids:
            selected_ids = self._sidebar.selected_layer_ids()
        self._sidebar.show_layers(document.layers, selected_ids)
        settings = self._settings()
        selected_id = settings.value("selectedLayerId", "")
        if selected_id:
            self._sidebar.select_layer(str(selected_id))
        self._sidebar.add_history(history_label)
        self._canvas.show_preview(self._controller.preview(document.image.width, document.image.height))
        self.statusBar().showMessage(
            f"{document.name} — {document.image.width} × {document.image.height} — "
            f"{self._canvas.zoom:.0%}"
        )
        self._update_window_title(document)

    def _update_window_title(self, document: DocumentView) -> None:
        active = self._controller.document
        dirty_marker = "*" if active is not None and active.is_dirty else ""
        self.setWindowTitle(f"{dirty_marker}{document.name} — DIP Studio")

    def _confirm_document_transition(self) -> bool:
        document = self._controller.document
        if document is None or not document.is_dirty:
            return True
        message = QMessageBox(self)
        message.setWindowTitle("Unsaved changes")
        message.setText(f"{document.name} has unsaved changes.")
        message.setInformativeText("Save your changes before continuing?")
        save = message.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = message.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        message.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() is save:
            return self._save_project()
        return message.clickedButton() is discard

    def _show_command_palette(self) -> None:
        commands = (
            ("New project", self._show_new_project),
            ("Open project", self._open_project),
            ("Open image", self._open_image),
            ("Save project", self._save_project),
            ("Keyboard shortcuts", self._show_shortcut_editor),
            ("Undo", self._undo),
            ("Redo", self._redo),
            ("Add layer", self._add_layer),
            ("Duplicate selected layer", self._duplicate_selected_layer),
            ("Remove selected layers", self._remove_selected_layers),
            ("Move selected layer up", lambda: self._move_selected_layer(-1)),
            ("Move selected layer down", lambda: self._move_selected_layer(1)),
            ("Toggle selected layer visibility", self._toggle_selected_visibility),
            ("Rename selected layer", self._rename_selected_layer),
            ("Toggle theme", self._toggle_theme),
            ("Zoom in", self._zoom_in),
            ("Zoom out", self._zoom_out),
            ("Fit canvas", self._fit_canvas),
            ("Actual size", self._actual_size),
            ("Toggle grid", lambda: self._grid_action.trigger()),
            ("Toggle before/after", lambda: self._before_after_action.trigger()),
        ) + tuple(
            (f"Tool: {tool.name}", lambda name=tool.name: self._select_tool(name))
            for tool in self._controller.tools
        )
        CommandPaletteDialog(commands, self).exec()

    def _show_shortcut_editor(self) -> None:
        if ShortcutEditorDialog(self._shortcuts, self).exec() == QDialog.DialogCode.Accepted:
            self._refresh_shortcuts()

    def _refresh_shortcuts(self) -> None:
        actions = {
            "file.new": self._new_action,
            "file.save": self._save_project_action,
            "edit.undo": self._undo_action,
            "edit.redo": self._redo_action,
            "layer.add": self._add_layer_action,
            "layer.duplicate": self._duplicate_layer_action,
            "layer.remove": self._remove_layer_action,
            "layer.move_up": self._move_layer_up_action,
            "layer.move_down": self._move_layer_down_action,
            "layer.toggle_visibility": self._toggle_layer_visibility_action,
            "layer.rename": self._rename_layer_action,
            "application.command_palette": self._command_action,
            "canvas.zoom_in": self._zoom_in_action,
            "canvas.zoom_out": self._zoom_out_action,
        }
        for command_id, action in actions.items():
            action.setShortcut(QKeySequence(self._shortcut(command_id)))

    def _zoom_in(self) -> None:
        self._canvas.zoom_in()
        self._update_zoom_status()

    def _zoom_out(self) -> None:
        self._canvas.zoom_out()
        self._update_zoom_status()

    def _fit_canvas(self) -> None:
        self._canvas.fit_to_view()
        self._update_zoom_status()

    def _actual_size(self) -> None:
        self._canvas.actual_size()
        self._update_zoom_status()

    def _toggle_grid(self, enabled: bool) -> None:
        self._canvas.set_grid_enabled(enabled)

    def _toggle_before_after(self, enabled: bool) -> None:
        self._canvas.set_before_after(enabled)

    def _update_zoom_status(self) -> None:
        document = self._controller.document
        if document is not None:
            self.statusBar().showMessage(
                f"{document.name} — {document.image.width} × {document.image.height} — "
                f"{self._canvas.zoom:.0%}"
            )

    def _toggle_workspace_sidebar(self, visible: bool) -> None:
        self._workspace_dock.setVisible(visible)

    def _select_workspace_panel(self, name: str) -> None:
        self._sidebar.select_panel(name)
        if not self._workspace_dock.isVisible():
            self._workspace_action.setChecked(True)
            self._workspace_dock.show()

    def _settings(self) -> QSettings:
        return QSettings("DIP Studio", "DIP Studio")

    def _load_shortcut_profile(self) -> None:
        value = self._settings().value("shortcutProfile", DEFAULT_PROFILE)
        if isinstance(value, str) and value in PROFILE_NAMES:
            self._profile_name = value
        self._shortcuts = create_profile_registry(self._profile_name)
        self._default_shortcuts = create_profile_registry(self._profile_name)
        self._input_dispatcher.set_registry(self._shortcuts)

    def _load_shortcut_overrides(self) -> None:
        raw = self._settings().value(
            f"shortcutOverrides/{self._profile_name}",
            "",
        )
        if not isinstance(raw, str) or not raw:
            return
        try:
            overrides = json.loads(raw)
        except json.JSONDecodeError:
            self._shortcut_load_rejections = ("invalid shortcut settings",)
            return
        if not isinstance(overrides, dict):
            self._shortcut_load_rejections = ("invalid shortcut settings",)
            return
        self._shortcut_load_rejections = self._shortcuts.apply_overrides(overrides)

    def _save_shortcut_overrides(self) -> None:
        settings = self._settings()
        settings.setValue(
            f"shortcutOverrides/{self._profile_name}",
            json.dumps(
                self._shortcuts.overrides(self._default_shortcuts),
                sort_keys=True,
            ),
        )
        settings.sync()

    def _switch_shortcut_profile(self, profile_name: str) -> None:
        if profile_name == self._profile_name:
            return
        self._save_shortcut_overrides()
        self._profile_name = profile_name
        self._shortcuts = create_profile_registry(profile_name)
        self._default_shortcuts = create_profile_registry(profile_name)
        self._input_dispatcher.set_registry(self._shortcuts)
        self._shortcut_load_rejections = ()
        self._load_shortcut_overrides()
        self._refresh_shortcuts()
        for name, action in self._profile_actions.items():
            action.setChecked(name == profile_name)
        self._save_profile_name()
        self.statusBar().showMessage(f"Shortcut profile: {profile_name}")

    def _save_profile_name(self) -> None:
        settings = self._settings()
        settings.setValue("shortcutProfile", self._profile_name)
        settings.sync()

    def _save_workspace(self) -> None:
        settings = self._settings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("workspacePanel", self._sidebar.tabs.currentIndex())
        selected_id = self._sidebar.selected_layer_id()
        if selected_id is not None:
            settings.setValue("selectedLayerId", str(selected_id))
        settings.sync()
        self.statusBar().showMessage("Workspace saved")

    def _restore_workspace(self) -> None:
        settings = self._settings()
        geometry = settings.value("geometry", QByteArray())
        state = settings.value("windowState", QByteArray())
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        if isinstance(state, QByteArray):
            self.restoreState(state)
        panel = settings.value("workspacePanel", 0, type=int)
        if 0 <= panel < self._sidebar.tabs.count():
            self._sidebar.tabs.setCurrentIndex(panel)

    def _reset_workspace(self) -> None:
        self.resize(1200, 760)
        self._workspace_dock.show()
        self._workspace_action.setChecked(True)
        self._sidebar.tabs.setCurrentIndex(0)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tools_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._workspace_dock)
        self.statusBar().showMessage("Workspace reset")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_document_transition():
            event.ignore()
            return
        self._save_shortcut_overrides()
        self._save_workspace()
        event.accept()

    def _toggle_theme(self) -> None:
        self._tokens = LIGHT if self._tokens == DARK else DARK
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setPalette(palette_for(self._tokens))
        self.setStyleSheet(
            f"QMainWindow {{ background: {self._tokens.surface}; }}"
            f" QDockWidget {{ color: {self._tokens.foreground}; }}"
        )
