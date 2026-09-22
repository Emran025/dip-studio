"""Theme-aware Qt workspace composition; editor behavior stays in application."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QByteArray, QEvent, QPoint, QSettings, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QKeyEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
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
    DEFAULT_PROFILE,
    PROFILE_NAMES,
    create_profile_registry,
)
from dip_studio.application.shortcut_registry import (
    ShortcutBinding,
    default_shortcut_registry,
)
from dip_studio.application.tool_registry import ToolDefinition
from dip_studio.core.errors import CancellationError
from dip_studio.presentation.canvas_view import CanvasView
from dip_studio.presentation.background_worker import BackgroundWorker
from dip_studio.presentation.dialogs import (
    CommandPaletteDialog,
    ExportDialog,
    HistogramDialog,
    ImageStatsDialog,
    NewProjectDialog,
    ParameterDefinition,
    ShortcutEditorDialog,
)
from dip_studio.presentation.dock_title_bar import DockPanel
from dip_studio.presentation.document_bar import DocumentBar
from dip_studio.presentation.sidebar import RightSidebar
from dip_studio.presentation.theme import DARK, LIGHT
from dip_studio.presentation.theme_adapter import palette_for, stylesheet_for
from dip_studio.presentation.tool_panel import ToolPanel
from dip_studio.presentation.vector_icons import icon_for
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
        self._project_paths: dict[str, Path] = {}
        self._tokens = DARK
        self._canvas = CanvasView()
        self._selection_origin: QPoint | None = None
        self._active_tool_id: str | None = None
        self._processing_worker = BackgroundWorker(self)
        self._processing_token = None
        self._ui_commands: dict[str, Callable[[], None]] = {}
        self.setWindowTitle("DIP Studio")
        self.setWindowIcon(icon_for("app"))
        self.resize(1200, 760)
        self.setCentralWidget(self._canvas)
        self._canvas.set_active_tool_callback(self._on_canvas_tool_event)
        self._canvas.cropCommitted.connect(self._commit_crop_from_selection)
        self._canvas.cropRectChanged.connect(self._on_crop_rect_changed)
        self._canvas.selectionCleared.connect(
            lambda: self.statusBar().showMessage("Selection cleared", 1500)
        )
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
        if self._controller.plugin_failures:
            self.statusBar().showMessage(
                f"{len(self._controller.plugin_failures)} plugin activation issue(s); "
                "see the application log",
                8000,
            )

    def _create_actions(self) -> None:
        self._new_action = QAction("New", self)
        self._new_action.setIcon(icon_for("file.new"))
        self._new_action.setShortcut(QKeySequence(self._shortcut("file.new")))
        self._register_ui_command("file.new", self._show_new_project)
        self._new_action.triggered.connect(
            lambda _checked=False: self._dispatch_ui_command("file.new")
        )
        self._open_project_action = QAction("Open project...", self)
        self._open_project_action.triggered.connect(self._open_project)
        self._save_project_action = QAction("Save project", self)
        self._save_project_action.setShortcut(QKeySequence(self._shortcut("file.save")))
        self._register_ui_command("file.save", self._save_project)
        self._save_project_action.triggered.connect(
            lambda _checked=False: self._dispatch_ui_command("file.save")
        )
        self._undo_action = QAction("Undo", self)
        self._undo_action.setIcon(icon_for("undo"))
        self._undo_action.setShortcut(QKeySequence(self._shortcut("edit.undo")))
        self._register_ui_command("edit.undo", self._undo)
        self._undo_action.triggered.connect(
            lambda _checked=False: self._dispatch_ui_command("edit.undo")
        )
        self._redo_action = QAction("Redo", self)
        self._redo_action.setIcon(icon_for("redo"))
        self._redo_action.setShortcut(QKeySequence(self._shortcut("edit.redo")))
        self._register_ui_command("edit.redo", self._redo)
        self._redo_action.triggered.connect(
            lambda _checked=False: self._dispatch_ui_command("edit.redo")
        )
        self._add_layer_action = QAction("Add layer", self)
        self._add_layer_action.setShortcut(QKeySequence(self._shortcut("layer.add")))
        self._add_layer_action.triggered.connect(self._add_layer)
        self._layer_via_copy_action = QAction("New layer via copy", self)
        self._layer_via_copy_action.setShortcut(QKeySequence("Ctrl+J"))
        self._layer_via_copy_action.triggered.connect(
            lambda: self._create_layer_from_selection(cut=False)
        )
        self._layer_via_cut_action = QAction("New layer via cut", self)
        self._layer_via_cut_action.setShortcut(QKeySequence("Ctrl+Shift+J"))
        self._layer_via_cut_action.triggered.connect(
            lambda: self._create_layer_from_selection(cut=True)
        )
        self._merge_down_action = QAction("Merge down", self)
        self._merge_down_action.setShortcut(QKeySequence("Ctrl+E"))
        self._merge_down_action.triggered.connect(self._merge_down)
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
        self._copy_layers_action = QAction("Copy selected layers", self)
        self._copy_layers_action.setShortcut(QKeySequence("Ctrl+C"))
        self._copy_layers_action.triggered.connect(self._copy_selected_layers)
        self._paste_layers_action = QAction("Paste layers", self)
        self._paste_layers_action.setShortcut(QKeySequence("Ctrl+V"))
        self._paste_layers_action.triggered.connect(self._paste_layers)
        self._theme_action = QAction("Toggle theme", self)
        self._theme_action.triggered.connect(self._toggle_theme)
        self._command_action = QAction("Command palette", self)
        self._command_action.setIcon(icon_for("command"))
        self._command_action.setShortcut(QKeySequence(self._shortcut("application.command_palette")))
        self._command_action.triggered.connect(self._show_command_palette)
        self._shortcut_editor_action = QAction("Keyboard shortcuts", self)
        self._shortcut_editor_action.triggered.connect(self._show_shortcut_editor)
        self._zoom_in_action = QAction("Zoom in", self)
        self._zoom_in_action.setIcon(icon_for("zoom.in"))
        self._zoom_in_action.setShortcut(QKeySequence(self._shortcut("canvas.zoom_in")))
        self._zoom_in_action.triggered.connect(self._zoom_in)
        self._zoom_out_action = QAction("Zoom out", self)
        self._zoom_out_action.setIcon(icon_for("zoom.out"))
        self._zoom_out_action.setShortcut(QKeySequence(self._shortcut("canvas.zoom_out")))
        self._zoom_out_action.triggered.connect(self._zoom_out)
        self._fit_action = QAction("Fit canvas", self)
        self._fit_action.setIcon(icon_for("fit"))
        self._fit_action.triggered.connect(self._fit_canvas)
        self._actual_size_action = QAction("Actual size", self)
        self._actual_size_action.triggered.connect(self._actual_size)
        self._grid_action = QAction("Show grid", self)
        self._grid_action.setIcon(icon_for("grid"))
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
            self._register_ui_command(command_id, handler)
            self._input_dispatcher.register(
                command_id,
                lambda command_id=command_id: self._dispatch_ui_command(command_id),
            )
        for tool in self._controller.tools:
            if tool.shortcut:
                command_id = f"tool.{tool.id}"
                self._register_ui_command(
                    command_id, lambda value=tool.id: self._select_tool(value)
                )
                self._input_dispatcher.register(
                    command_id,
                    lambda command_id=command_id: self._dispatch_ui_command(command_id),
                )

    def _register_ui_command(self, command_id: str, handler: Callable[[], None]) -> None:
        """Register the single presentation command path used by UI surfaces."""
        if not command_id.strip():
            raise ValueError("Command id cannot be empty")
        self._ui_commands[command_id] = handler

    def _dispatch_ui_command(self, command_id: str) -> None:
        try:
            handler = self._ui_commands[command_id]
        except KeyError as error:
            raise KeyError(f"Unknown UI command: {command_id}") from error
        handler()

    def _focus_state(self, widget: QWidget | None) -> FocusState:
        if widget is None:
            return FocusState()
        if isinstance(widget, (QLineEdit, QTextEdit, QAbstractSpinBox, QComboBox)):
            return FocusState(input_field=True)
        if isinstance(widget, QDialog) or QApplication.activeModalWidget() is not None:
            return FocusState(modal_dialog=True)
        if self._sidebar.isAncestorOf(widget):
            return FocusState(panel_context="Layer Panel")
        return FocusState(canvas=self._canvas.isAncestorOf(widget) or widget is self._canvas)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget):
            self._style_native_title_bar(watched)
            return super().eventFilter(watched, event)
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return super().eventFilter(watched, event)
        if event.isAutoRepeat():
            return super().eventFilter(watched, event)
        widget = QApplication.focusWidget()
        state = self._focus_state(widget)
        if state.input_field or state.modal_dialog:
            return super().eventFilter(watched, event)
        if (
            self._active_tool_id == "crop"
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self._commit_crop_from_selection()
            event.accept()
            return True
        if self._canvas.hasFocus() and event.key() in (
            Qt.Key.Key_Plus,
            Qt.Key.Key_Equal,
        ):
            self._canvas.zoom_in()
            event.accept()
            return True
        if self._canvas.hasFocus() and event.key() in (
            Qt.Key.Key_Minus,
            Qt.Key.Key_Underscore,
        ):
            self._canvas.zoom_out()
            event.accept()
            return True
        key = QKeySequence(event.modifiers() | Qt.KeyboardModifier(event.key())).toString()
        if not key:
            return super().eventFilter(watched, event)
        if self._input_dispatcher.dispatch(key, state) is None:
            return super().eventFilter(watched, event)
        event.accept()
        return True

    def _style_native_title_bar(self, widget: QWidget) -> None:
        """Match Windows native title bars to the active application theme."""
        window = widget.windowHandle()
        if window is None:
            return
        title_color = QColor(self._tokens.surface)
        text_color = QColor(self._tokens.foreground)
        set_title_color = getattr(window, "setTitleBarColor", None)
        set_button_color = getattr(window, "setTitleBarButtonColor", None)
        if callable(set_title_color):
            set_title_color(title_color)
        if callable(set_button_color):
            set_button_color(text_color)

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
        command_id = f"tool.{tool_id}"
        self._register_ui_command(
            command_id, lambda value=tool_id: self._select_tool(value)
        )
        action.triggered.connect(
            lambda _checked=False, command_id=command_id:
            self._dispatch_ui_command(command_id)
        )
        return action

    def _processing_action(
        self,
        operation: str,
        parameters: dict[str, object],
        *,
        dialog: bool = False,
    ) -> Callable[[], None]:
        command_id = f"processing.{operation}.dialog" if dialog else f"processing.{operation}"
        if dialog:
            handler = lambda: self._apply_filter_dialog(operation)
        else:
            handler = lambda: self._quick_apply(operation, parameters)
        self._register_ui_command(command_id, handler)
        return lambda command_id=command_id: self._dispatch_ui_command(command_id)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self._new_action)
        file_menu.addAction(self._open_project_action)
        file_menu.addAction(self._save_project_action)
        file_menu.addAction("Open Image...", self._open_image)
        file_menu.addAction("Place Image as Layer...", self._place_image)
        file_menu.addSeparator()
        file_menu.addAction("Export As...", self._export_image)
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
        edit_menu.addSeparator()
        edit_menu.addAction(self._copy_layers_action)
        edit_menu.addAction(self._paste_layers_action)
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
        tools_menu = self.menuBar().addMenu("Tools")
        tool_menus = {}
        for tool, action in zip(self._controller.tools, self._tool_actions, strict=True):
            category_menu = tool_menus.get(tool.category)
            if category_menu is None:
                category_menu = tools_menu.addMenu(tool.category)
                tool_menus[tool.category] = category_menu
            category_menu.addAction(action)
        image_menu = self.menuBar().addMenu("Image")
        image_menu.addAction("Rotate 90° CW").triggered.connect(lambda: self._rotate_image(90))
        image_menu.addAction("Rotate 90° CCW").triggered.connect(lambda: self._rotate_image(-90))
        image_menu.addAction("Rotate 180°").triggered.connect(lambda: self._rotate_image(180))
        image_menu.addSeparator()
        image_menu.addAction("Flip Horizontal").triggered.connect(lambda: self._flip_image('horizontal'))
        image_menu.addAction("Flip Vertical").triggered.connect(lambda: self._flip_image('vertical'))

        layer_menu = self.menuBar().addMenu("Layer")
        layer_menu.addAction(self._add_layer_action)
        layer_menu.addAction(self._layer_via_copy_action)
        layer_menu.addAction(self._layer_via_cut_action)
        layer_menu.addAction(self._duplicate_layer_action)
        layer_menu.addSeparator()
        layer_menu.addAction(self._merge_down_action)
        layer_menu.addSeparator()
        layer_menu.addAction(self._remove_layer_action)
        layer_menu.addAction(self._toggle_layer_visibility_action)
        layer_menu.addAction(self._rename_layer_action)

        select_menu = self.menuBar().addMenu("Select")
        select_menu.addAction("Select All").triggered.connect(self._select_all)
        select_menu.addAction("Deselect").triggered.connect(
            lambda: self._canvas.set_selection_rect(None)
        )

        filter_menu = self.menuBar().addMenu("Filter")
        blur_menu = filter_menu.addMenu("Blur")
        blur_menu.addAction("Gaussian Blur...").triggered.connect(
            self._processing_action("gaussian_blur", {}, dialog=True)
        )
        blur_menu.addAction("Median Blur...").triggered.connect(
            self._processing_action("median_blur", {}, dialog=True)
        )
        blur_menu.addAction("Bilateral Filter...").triggered.connect(
            self._processing_action("bilateral_filter", {}, dialog=True)
        )

        edge_menu = filter_menu.addMenu("Edges")
        edge_menu.addAction("Sobel").triggered.connect(self._processing_action("sobel", {}))
        edge_menu.addAction("Canny...").triggered.connect(
            self._processing_action("canny", {}, dialog=True)
        )
        edge_menu.addAction("Laplacian").triggered.connect(
            self._processing_action("laplacian", {})
        )

        adjust_menu = filter_menu.addMenu("Adjust")
        adjust_menu.addAction("Negative").triggered.connect(
            self._processing_action("negative", {})
        )
        adjust_menu.addAction("Gamma...").triggered.connect(
            self._processing_action("gamma", {}, dialog=True)
        )
        adjust_menu.addAction("Log Transform").triggered.connect(
            self._processing_action("log_transform", {"c": "1.0"})
        )
        adjust_menu.addAction("Brightness & Contrast...").triggered.connect(
            self._processing_action("brightness_contrast", {}, dialog=True)
        )

        hist_menu = filter_menu.addMenu("Histogram")
        hist_menu.addAction("Equalize").triggered.connect(
            self._processing_action("histogram_equalization", {})
        )
        hist_menu.addAction("CLAHE...").triggered.connect(
            self._processing_action("clahe", {}, dialog=True)
        )

        morph_menu = filter_menu.addMenu("Morphology")
        morph_menu.addAction("Erode").triggered.connect(self._processing_action("erode", {}))
        morph_menu.addAction("Dilate").triggered.connect(self._processing_action("dilate", {}))
        morph_menu.addAction("Open").triggered.connect(
            self._processing_action("morph_open", {})
        )
        morph_menu.addAction("Close").triggered.connect(
            self._processing_action("morph_close", {})
        )

        color_menu = filter_menu.addMenu("Color")
        color_menu.addAction("Grayscale").triggered.connect(
            self._processing_action("grayscale", {})
        )
        color_menu.addAction("Hue & Saturation...").triggered.connect(
            self._processing_action("hue_saturation", {}, dialog=True)
        )

        analysis_menu = self.menuBar().addMenu("Analysis")
        analysis_menu.addAction("Histogram", self._show_histogram)
        analysis_menu.addAction("Image Statistics", self._show_image_stats)
        analysis_menu.addSeparator()
        analysis_menu.addAction(
            "Threshold...", self._processing_action("threshold", {}, dialog=True)
        )
        analysis_menu.addAction(
            "Segment...", self._processing_action("segment", {}, dialog=True)
        )

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About DIP Studio").triggered.connect(self._show_about)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main toolbar", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        document_bar = DocumentBar(self)
        document_bar.newRequested.connect(self._show_new_project)
        document_bar.documentSelected.connect(self._switch_document)
        document_bar.documentCloseRequested.connect(self._close_document)
        self._document_bar = document_bar
        toolbar.addWidget(document_bar)
        for action in self._tool_actions:
            self.addAction(action)
        self.addToolBar(toolbar)

        # Add tool-name indicator to right of status bar
        from PySide6.QtWidgets import QLabel
        self._tool_status_label = QLabel("Tool: —")
        self._tool_status_label.setStyleSheet("padding: 0 8px; font-weight: bold;")
        self.statusBar().addPermanentWidget(self._tool_status_label)

    def _create_docks(self) -> None:
        tools = ToolPanel(self._controller.tools)
        tools.toolSelected.connect(self._select_tool)
        self._tool_panel = tools
        self._tools_dock = self._dock("Tools", tools)
        self._sidebar = RightSidebar()
        self._sidebar.tabs.panelDetached.connect(self._detach_workspace_panel)
        self._workspace_dock = self._dock("Workspace", self._sidebar)
        self._sidebar.set_layer_callback(self._change_layer)
        self._sidebar.set_layer_structure_callback(self._change_layer_structure)
        self._sidebar.set_layer_rename_callback(self._rename_layer)
        self._sidebar.properties.previewRequested.connect(self._preview_parameters)
        self._sidebar.properties.applyRequested.connect(self._apply_parameters)
        self._sidebar.properties.cancelRequested.connect(self._cancel_parameters)
        self._sidebar.set_history_jump_callback(self._on_history_jump)
        self._sidebar.set_channel_callback(self._on_channel_selected)
        self._sidebar.layerSelectionChanged.connect(self._on_layer_selection_changed)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tools_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._workspace_dock)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea,
            self._dock("Timeline", QLabel("Timeline")),
        )

    def _dock(
        self,
        title: str,
        widget: QWidget,
        panel_group: object | None = None,
        panel_name: str | None = None,
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"{title.lower()}Dock")
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        native_title_bar = QWidget(dock)
        native_title_bar.setFixedHeight(1)
        dock.setTitleBarWidget(native_title_bar)
        dock.setWidget(DockPanel(dock, widget, self, panel_group, panel_name))
        return dock

    def _detach_workspace_panel(self, name: str, widget: QWidget) -> None:
        widget.setParent(None)
        widget.setVisible(True)
        widget.show()
        dock = self._dock(name, widget, self._sidebar.tabs, name)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        dock.setMinimumSize(220, 140)
        dock.setSizeIncrement(1, 1)
        dock.resize(300, 360)
        dock.setFloating(True)
        dock.move(self.geometry().center() - QPoint(150, 180))
        dock.show()
        dock.raise_()
        widget.show()
        dock.widget().show()

    def _merge_dock_at_position(self, dock: QDockWidget, position: object) -> bool:
        if not isinstance(position, QPoint):
            return False
        target = self._workspace_dock
        target_position = target.mapFromGlobal(position)
        if not target.rect().contains(target_position):
            return False
        panel = dock.widget()
        if not isinstance(panel, DockPanel):
            return False
        group = self._sidebar.tabs
        content = panel._content
        name = panel._panel_name
        if name is None:
            return False
        content.setParent(None)
        content.setVisible(True)
        dock.setWidget(None)
        group.attach_panel(content, name)
        dock.close()
        return True

    def _create_blank_document(self) -> None:
        if not self._confirm_document_transition():
            return
        document = self._controller.create_document("Untitled", 800, 600)
        self._show_document(document, "Created blank document")

    def _show_new_project(self) -> None:
        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            document = self._controller.create_document(values.name, values.width, values.height)
            self._show_document(document, "Created project")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "New project failed", str(error))

    def _select_tool(self, tool_id: str) -> None:
        """Activate a tool: update controller, properties panel, and canvas cursor."""
        tool = next((t for t in self._controller.tools if t.id == tool_id), None)
        if tool is None:
            self._sidebar.properties.set_schema(())
            return
        try:
            self._controller.set_active_tool(tool_id)
        except KeyError:
            pass
        self._active_tool_id = tool_id
        self._tool_panel.select_tool(tool_id, emit=False)
        if tool_id not in {
            "selection",
            "ellipse_selection",
            "lasso",
            "polygon_selection",
            "color_selection",
            "crop",
        }:
            self._selection_origin = None
            self._canvas.set_selection_rect(None)
        # Load parameter schema into Properties panel
        schema = tuple(
            ParameterDefinition(
                parameter.label, parameter.kind, parameter.default,
                parameter.minimum, parameter.maximum, parameter.choices,
            )
            for parameter in tool.parameters
        )
        self._sidebar.properties.set_schema(schema)
        self._sidebar.select_panel("Properties")
        # Activate Photoshop crop mode or standard canvas mode
        if tool_id == "crop":
            self._canvas.set_crop_mode(True)
            doc = self._controller.document
            if doc is not None:
                rect = self._selected_layer_content_rect(doc)
                self._canvas.set_crop_rect_from_image(
                    *rect, doc.image.width, doc.image.height
                )
        else:
            self._canvas.set_crop_mode(False)
        # Update canvas cursor based on the active tool
        self._update_canvas_cursor(tool_id)
        # Update status bar
        self.statusBar().showMessage(
            f"Tool: {tool.name}  —  {tool.description}", 3000
        )
        if hasattr(self, '_tool_status_label'):
            self._tool_status_label.setText(f"Tool: {tool.name}")

    def _on_layer_selection_changed(self, layer_id: object) -> None:
        """Handle layer selection change in sidebar layer list or canvas hit-testing."""
        if layer_id is None:
            return
        doc = self._controller.document
        if doc is None:
            return
        layer = next((l for l in doc.layers if l.id == layer_id), None)
        if layer is not None:
            self.statusBar().showMessage(f"Active layer: {layer.name}")
            if hasattr(self._controller, "set_active_layer"):
                self._controller.set_active_layer(layer.id)  # type: ignore[arg-type]
            rect = self._selected_layer_content_rect(doc, layer.id)
            self._canvas.set_active_layer_rect(
                *rect, layer.name, doc.image.width, doc.image.height
            )
            from dip_studio.application.presentation_bridge import is_text_layer
            if self._active_tool_id == "text" and is_text_layer(layer):
                self._show_text_layer_dialog(existing_layer=layer)
            if self._active_tool_id == "crop":
                self._controller.set_active_tool("crop")
                self._tool_panel.select_tool("crop", emit=False)
                self._canvas.set_crop_mode(True)
                self._update_canvas_cursor("crop")
                self._canvas.set_crop_rect_from_image(
                    *rect, doc.image.width, doc.image.height
                )
            elif self._active_tool_id not in {
                "selection",
                "ellipse_selection",
                "lasso",
                "polygon_selection",
                "color_selection",
            }:
                self._canvas.set_selection_rect(None)

    def _selected_layer_content_rect(
        self, document: DocumentView, layer_id: object | None = None
    ) -> tuple[int, int, int, int]:
        """Return the selected image layer's non-transparent content bounds (x, y, w, h)."""
        full = (0, 0, document.image.width, document.image.height)
        selected = (layer_id,) if layer_id is not None else self._selected_layer_ids()
        store = self._controller.data_store
        if not selected or store is None:
            return full
        layer = next((item for item in document.layers if item.id == selected[0]), None)
        if layer is None or layer.buffer_id is None:
            return full
        try:
            from dip_studio.rendering.compositor import _to_rgba

            buffer = _to_rgba(store.get(layer.buffer_id))
            source_height, source_width = buffer.shape[:2]
            if source_width <= 0 or source_height <= 0:
                return full
            t = getattr(layer, "transform", None)
            tx = int(t.tx) if t else 0
            ty = int(t.ty) if t else 0
            return (
                tx,
                ty,
                max(1, source_width),
                max(1, source_height),
            )
        except (KeyError, ValueError):
            return full

    def _on_crop_rect_changed(self, rect: object) -> None:
        """Update properties panel and status bar when crop rectangle changes."""
        doc = self._controller.document
        if doc is None:
            return
        from PySide6.QtCore import QRect
        if not isinstance(rect, QRect) or rect.isNull():
            return
        ix1, iy1 = self._canvas.widget_to_image_pos(rect.topLeft(), doc.image.width, doc.image.height)
        ix2, iy2 = self._canvas.widget_to_image_pos(rect.bottomRight(), doc.image.width, doc.image.height)
        w = max(1, ix2 - ix1)
        h = max(1, iy2 - iy1)
        self.statusBar().showMessage(
            f"Crop: {w}×{h} at ({ix1}, {iy1}) — Press Enter to commit or Esc to cancel"
        )
        self._sidebar.properties.set_values({
            "X": ix1, "Y": iy1,
            "Width": w, "Height": h,
            "x": ix1, "y": iy1,
            "width": w, "height": h,
        })

    def _update_canvas_cursor(self, tool_id: str) -> None:
        """Set the canvas cursor to match the active tool."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor
        cursor_map = {
            "hand":         Qt.CursorShape.OpenHandCursor,
            "move":         Qt.CursorShape.SizeAllCursor,
            "zoom":         Qt.CursorShape.SizeBDiagCursor,
            "crop":         Qt.CursorShape.CrossCursor,
            "eyedropper":   Qt.CursorShape.CrossCursor,
            "text":         Qt.CursorShape.IBeamCursor,
            "rotate":       Qt.CursorShape.SizeHorCursor,
            "brush":        Qt.CursorShape.CrossCursor,
            "pencil":       Qt.CursorShape.CrossCursor,
            "eraser":       Qt.CursorShape.BlankCursor,
            "fill":         Qt.CursorShape.PointingHandCursor,
            "selection":    Qt.CursorShape.CrossCursor,
            "ellipse_selection": Qt.CursorShape.CrossCursor,
            "lasso":        Qt.CursorShape.CrossCursor,
            "polygon_selection": Qt.CursorShape.CrossCursor,
        }
        shape = cursor_map.get(tool_id, Qt.CursorShape.ArrowCursor)
        self._canvas.setCursor(QCursor(shape))

    def _on_canvas_tool_event(self, event_type: str, event: object) -> None:
        """Route canvas mouse events to the active tool's handler."""
        tool_id = self._active_tool_id or self._controller.active_tool_id
        handler = self._tool_event_handlers.get(tool_id)
        if handler:
            handler(event_type, event)

    @property
    def _tool_event_handlers(self) -> dict[str, object]:
        return {
            "move": self._tool_move_event,
            "select": self._tool_move_event,
            "zoom": self._tool_zoom_event,
            "hand": self._tool_pan_event,
            "eyedropper": self._tool_eyedropper_event,
            "histogram": self._tool_histogram_event,
            "selection": self._tool_selection_event,
            "ellipse_selection": self._tool_selection_event,
            "lasso": self._tool_selection_event,
            "polygon_selection": self._tool_selection_event,
            # Paint tools (Phase 5)
            "brush": self._tool_paint_event,
            "pencil": self._tool_paint_event,
            "eraser": self._tool_eraser_event,
            "fill": self._tool_fill_event,
            # Text tool (Phase E)
            "text": self._tool_text_event,
        }

    def _tool_move_event(self, event_type: str, event: object) -> None:
        """Move / Select tool handler:
        - Press: Hit-test canvas to auto-select clicked layer & start drag.
        - Move: Translate selected layer position interactively on canvas.
        - Release: Finalize layer move.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return

        doc = self._controller.document
        if doc is None:
            return

        pos = event.position().toPoint()
        ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)

        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            hit_layer = self._controller.hit_test_layer(ix, iy)
            if hit_layer is not None:
                self._sidebar.select_layer(hit_layer.id)
                self._on_layer_selection_changed(hit_layer.id)
            self._move_drag_start = (ix, iy)
            self._canvas.setCursor(Qt.CursorShape.ClosedHandCursor if hit_layer else Qt.CursorShape.SizeAllCursor)

        elif event_type == "move" and getattr(self, "_move_drag_start", None) is not None:
            start_x, start_y = self._move_drag_start
            dx = ix - start_x
            dy = iy - start_y
            if dx != 0 or dy != 0:
                selected = self._selected_layer_ids()
                if selected:
                    target_id = selected[0]
                    layer = next((l for l in doc.layers if l.id == target_id), None)
                    if layer is not None and not layer.locked:
                        doc = self._controller.translate_layer(target_id, dx, dy)
                        self._move_drag_start = (ix, iy)
                        rect = self._selected_layer_content_rect(doc, target_id)
                        self._canvas.set_active_layer_rect(
                            *rect, layer.name, doc.image.width, doc.image.height
                        )
                        self._refresh_preview()

        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            self._move_drag_start = None
            self._canvas.setCursor(Qt.CursorShape.SizeAllCursor)

    def _tool_zoom_event(self, event_type: str, event: object) -> None:
        """Zoom tool: left-click zooms in, right-click zooms out."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        if event_type == "press":
            if event.button() == Qt.MouseButton.LeftButton:
                self._canvas.zoom_in()
            elif event.button() == Qt.MouseButton.RightButton:
                self._canvas.zoom_out()

    def _tool_pan_event(self, event_type: str, event: object) -> None:
        """Hand tool: click and drag pans the canvas directly."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._canvas._drag_start = event.position().toPoint()
            self._canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event_type == "move" and self._canvas._drag_start is not None:
            current = event.position().toPoint()
            self._canvas._pan += current - self._canvas._drag_start
            self._canvas._drag_start = current
            self._canvas._clamp_pan()
            self._canvas.update()
        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            self._canvas._drag_start = None
            self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)

    def _tool_selection_event(self, event_type: str, event: object) -> None:
        """Selection & Crop tools: interactive drag / click to define region on canvas.

        Dispatches to sub-handlers based on the active tool id:
          ``selection``          → rectangular marquee (drag)
          ``crop``               → rectangular crop region (drag)
          ``ellipse_selection``  → elliptical marquee (drag → rasterise)
          ``lasso``              → freehand polygon (move → accumulate points)
          ``polygon_selection``  → click-by-click polygon (release = add vertex)
        """
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return

        tool = self._active_tool_id or ""

        if tool in ("selection", "crop", ""):
            self._rect_selection_event(event_type, event)
        elif tool == "ellipse_selection":
            self._ellipse_selection_event(event_type, event)
        elif tool == "lasso":
            self._lasso_event(event_type, event)
        elif tool == "polygon_selection":
            self._polygon_event(event_type, event)

    def _rect_selection_event(self, event_type: str, event: object) -> None:
        """Rectangle / crop drag handler (original logic)."""
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return
        pos = event.position().toPoint()
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._selection_origin = pos
            self._canvas.set_selection_rect(QRect(pos, pos))
        elif event_type == "move" and self._selection_origin is not None:
            rect = QRect(self._selection_origin, pos).normalized()
            self._canvas.set_selection_rect(rect)
            doc = self._controller.document
            if doc is not None:
                ix1, iy1 = self._canvas.widget_to_image_pos(
                    rect.topLeft(), doc.image.width, doc.image.height
                )
                ix2, iy2 = self._canvas.widget_to_image_pos(
                    rect.bottomRight(), doc.image.width, doc.image.height
                )
                w = max(1, ix2 - ix1)
                h = max(1, iy2 - iy1)
                self.statusBar().showMessage(
                    f"{(self._active_tool_id or 'selection').title()}: {w}×{h} at ({ix1}, {iy1})"
                )
        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            if self._selection_origin is not None:
                rect = QRect(self._selection_origin, pos).normalized()
                doc = self._controller.document
                if doc is not None and rect.width() > 4 and rect.height() > 4:
                    ix1, iy1 = self._canvas.widget_to_image_pos(
                        rect.topLeft(), doc.image.width, doc.image.height
                    )
                    ix2, iy2 = self._canvas.widget_to_image_pos(
                        rect.bottomRight(), doc.image.width, doc.image.height
                    )
                    w = max(1, ix2 - ix1)
                    h = max(1, iy2 - iy1)
                    if self._active_tool_id == "crop":
                        self.statusBar().showMessage(
                            f"Crop region: {w}×{h} at ({ix1}, {iy1}). Click Apply in Properties to crop."
                        )
                    else:
                        self._controller.set_selection(  # type: ignore[attr-defined]
                            self._controller.make_selection(
                                x=ix1, y=iy1, width=w, height=h, kind="rectangle"
                            )
                        ) if hasattr(self._controller, "set_selection") else None
                self._selection_origin = None

    def _ellipse_selection_event(self, event_type: str, event: object) -> None:
        """Ellipse marquee: drag bounding box → rasterise on release."""
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return
        pos = event.position().toPoint()
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._selection_origin = pos
            self._canvas.set_selection_rect(QRect(pos, pos))
        elif event_type == "move" and self._selection_origin is not None:
            rect = QRect(self._selection_origin, pos).normalized()
            self._canvas.set_selection_rect(rect)
        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            if self._selection_origin is not None:
                from PySide6.QtCore import QRect
                rect = QRect(self._selection_origin, pos).normalized()
                doc = self._controller.document
                store = self._controller.data_store
                if doc is not None and store is not None and rect.width() > 4 and rect.height() > 4:
                    ix1, iy1 = self._canvas.widget_to_image_pos(
                        rect.topLeft(), doc.image.width, doc.image.height
                    )
                    ix2, iy2 = self._canvas.widget_to_image_pos(
                        rect.bottomRight(), doc.image.width, doc.image.height
                    )
                    bw = max(1, ix2 - ix1)
                    bh = max(1, iy2 - iy1)
                    try:
                        from dip_studio.application.presentation_bridge import rasterise_ellipse
                        mask = rasterise_ellipse(
                            doc.image.width, doc.image.height,
                            ix1 + bw // 2, iy1 + bh // 2, bw // 2, bh // 2,
                        )
                        mask_bid = store.allocate(mask)
                        sel = self._controller.make_selection(
                            x=ix1, y=iy1, width=bw, height=bh,
                            kind="ellipse", mask_buffer_id=mask_bid,
                        )
                        if hasattr(self._controller, "set_selection"):
                            self._controller.set_selection(sel)  # type: ignore[attr-defined]
                        self.statusBar().showMessage(f"Ellipse selection: {bw}×{bh}")
                    except Exception as exc:
                        self.statusBar().showMessage(f"Ellipse selection error: {exc}", 3000)
                self._selection_origin = None

    def _lasso_event(self, event_type: str, event: object) -> None:
        """Freehand lasso: accumulate mouse-move points → rasterise on release."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return
        pos = event.position().toPoint()
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._lasso_points: list[tuple[int, int]] = []
            self._selection_origin = pos
        elif event_type == "move" and self._selection_origin is not None:
            doc = self._controller.document
            if doc is not None:
                ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
                if not hasattr(self, "_lasso_points"):
                    self._lasso_points = []
                self._lasso_points.append((ix, iy))
        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            if self._selection_origin is not None:
                doc = self._controller.document
                store = self._controller.data_store
                pts = getattr(self, "_lasso_points", [])
                if doc is not None and store is not None and len(pts) >= 3:
                    try:
                        from dip_studio.application.presentation_bridge import rasterise_lasso
                        mask = rasterise_lasso(doc.image.width, doc.image.height, pts)
                        mask_bid = store.allocate(mask)
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        x1, y1 = min(xs), min(ys)
                        bw = max(1, max(xs) - x1)
                        bh = max(1, max(ys) - y1)
                        sel = self._controller.make_selection(
                            x=x1, y=y1, width=bw, height=bh,
                            kind="lasso", mask_buffer_id=mask_bid,
                        )
                        if hasattr(self._controller, "set_selection"):
                            self._controller.set_selection(sel)  # type: ignore[attr-defined]
                        self.statusBar().showMessage(f"Lasso selection: {len(pts)} points")
                    except Exception as exc:
                        self.statusBar().showMessage(f"Lasso error: {exc}", 3000)
                self._selection_origin = None
                self._lasso_points = []

    def _polygon_event(self, event_type: str, event: object) -> None:
        """Click-by-click polygon: each left-click adds a vertex; double-click closes.

        The polygon is rasterised and committed when the user double-clicks.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent

        if not isinstance(event, QMouseEvent):
            return
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            doc = self._controller.document
            if doc is None:
                return
            pos = event.position().toPoint()
            ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
            if not hasattr(self, "_poly_points"):
                self._poly_points: list[tuple[int, int]] = []
            self._poly_points.append((ix, iy))
            self.statusBar().showMessage(f"Polygon: {len(self._poly_points)} vertices (double-click to close)")
        elif event_type == "double_click":
            pts = getattr(self, "_poly_points", [])
            doc = self._controller.document
            store = self._controller.data_store
            if doc is not None and store is not None and len(pts) >= 3:
                try:
                    from dip_studio.application.presentation_bridge import rasterise_polygon
                    mask = rasterise_polygon(doc.image.width, doc.image.height, pts)
                    mask_bid = store.allocate(mask)
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    x1, y1 = min(xs), min(ys)
                    bw = max(1, max(xs) - x1)
                    bh = max(1, max(ys) - y1)
                    sel = self._controller.make_selection(
                        x=x1, y=y1, width=bw, height=bh,
                        kind="polygon", mask_buffer_id=mask_bid,
                    )
                    if hasattr(self._controller, "set_selection"):
                        self._controller.set_selection(sel)  # type: ignore[attr-defined]
                    self.statusBar().showMessage(f"Polygon selection closed: {len(pts)} vertices")
                except Exception as exc:
                    self.statusBar().showMessage(f"Polygon error: {exc}", 3000)
            self._poly_points = []

    def _tool_eyedropper_event(self, event_type: str, event: object) -> None:
        """Eyedropper: click to sample pixel color at cursor position."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        if event_type != "press" or event.button() != Qt.MouseButton.LeftButton:
            return
        # Sample pixel from the canvas at click position
        document = self._controller.document
        store = self._controller.data_store
        if document is None or store is None:
            return
        layer = next((la for la in document.layers if la.buffer_id is not None), None)
        if layer is None or layer.buffer_id is None:
            return
        try:
            arr = store.get(layer.buffer_id)
            # Map widget coordinates to image coordinates
            pos = event.position().toPoint()
            img_w = document.image.width
            img_h = document.image.height
            canvas_w = max(1, self._canvas.width())
            canvas_h = max(1, self._canvas.height())
            ix = int(pos.x() / canvas_w * img_w)
            iy = int(pos.y() / canvas_h * img_h)
            ix = max(0, min(ix, img_w - 1))
            iy = max(0, min(iy, img_h - 1))
            if arr.ndim == 3:
                r, g, b = int(arr[iy, ix, 0]), int(arr[iy, ix, 1]), int(arr[iy, ix, 2])
                alpha = int(arr[iy, ix, 3]) if arr.shape[2] == 4 else 255
            else:
                r = g = b = int(arr[iy, ix])
                alpha = 255
            self.statusBar().showMessage(
                f"Eyedropper: ({ix},{iy})  R:{r} G:{g} B:{b} A:{alpha}", 4000
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Eyedropper error: {exc}", 2000)

    def _tool_histogram_event(self, event_type: str, event: object) -> None:
        """Histogram tool: clicking shows histogram dialog."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._show_histogram()

    # ------------------------------------------------------------------
    # Paint tool event handlers (Phase 5)
    # ------------------------------------------------------------------

    def _tool_paint_event(self, event_type: str, event: object) -> None:
        """Brush / Pencil tools: accumulate stroke points and paint on release."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        doc = self._controller.document
        if doc is None:
            return
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._stroke_points: list[tuple[int, int]] = []
            pos = event.position().toPoint()
            ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
            self._stroke_points.append((ix, iy))
        elif event_type == "move" and event.buttons() & Qt.MouseButton.LeftButton:
            if not hasattr(self, "_stroke_points"):
                self._stroke_points = []
            pos = event.position().toPoint()
            ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
            self._stroke_points.append((ix, iy))
            # Live paint every few points to keep preview responsive.
            if len(self._stroke_points) % 5 == 0:
                self._flush_paint_stroke(commit=False)
        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, "_stroke_points") and self._stroke_points:
                self._flush_paint_stroke(commit=True)
                self._stroke_points = []

    def _flush_paint_stroke(self, *, commit: bool) -> None:
        """Call controller.paint_stroke() and refresh the canvas."""
        points = getattr(self, "_stroke_points", [])
        if not points:
            return
        # Brush colour: use foreground colour from sidebar if available.
        color = (0, 0, 0, 255)  # black default
        try:
            color = self._sidebar.foreground_color_rgba  # type: ignore[attr-defined]
        except AttributeError:
            pass
        result = self._controller.paint_stroke(points, color, size=20, hardness=0.8, opacity=1.0)
        if result is not None and commit:
            self._show_document(result, "")

    def _tool_eraser_event(self, event_type: str, event: object) -> None:
        """Eraser tool: reduce alpha of active layer along stroke path."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        doc = self._controller.document
        if doc is None:
            return
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            self._erase_points: list[tuple[int, int]] = []
            pos = event.position().toPoint()
            ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
            self._erase_points.append((ix, iy))
        elif event_type == "move" and event.buttons() & Qt.MouseButton.LeftButton:
            if not hasattr(self, "_erase_points"):
                self._erase_points = []
            pos = event.position().toPoint()
            ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
            self._erase_points.append((ix, iy))
        elif event_type == "release" and event.button() == Qt.MouseButton.LeftButton:
            points = getattr(self, "_erase_points", [])
            if points:
                result = self._controller.eraser_stroke(points, size=30, hardness=0.9, opacity=1.0)
                if result is not None:
                    self._show_document(result, "")
            self._erase_points = []

    def _tool_fill_event(self, event_type: str, event: object) -> None:
        """Fill tool: BFS flood-fill at clicked pixel."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        doc = self._controller.document
        if doc is None:
            return
        if event_type == "press" and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            ix, iy = self._canvas.widget_to_image_pos(pos, doc.image.width, doc.image.height)
            color = (0, 0, 0, 255)
            try:
                color = self._sidebar.foreground_color_rgba  # type: ignore[attr-defined]
            except AttributeError:
                pass
            result = self._controller.flood_fill(ix, iy, color, tolerance=15)
            if result is not None:
                self._show_document(result, "Flood fill")

    def _tool_text_event(self, event_type: str, event: object) -> None:
        """Text tool: left-click opens TextLayerDialog to create / insert a text layer."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        if not isinstance(event, QMouseEvent):
            return
        if event_type != "press" or event.button() != Qt.MouseButton.LeftButton:
            return
        self._show_text_layer_dialog(existing_layer=None)

    def _show_text_layer_dialog(self, existing_layer: object = None) -> None:
        """Open the TextLayerDialog and execute AddTextLayer on confirmation."""
        try:
            from dip_studio.presentation.text_layer_dialog import TextLayerDialog
        except ImportError:
            self.statusBar().showMessage("TextLayerDialog unavailable", 2000)
            return

        dlg = TextLayerDialog(
            existing_layer=existing_layer if existing_layer is not None else None,
            parent=self,
        )

        def _on_confirmed(text_layer: object) -> None:
            try:
                from dip_studio.application.text_commands import AddTextLayer, EditTextLayer
                store = self._controller.data_store
                if store is None:
                    self.statusBar().showMessage("No active document", 2000)
                    return
                if existing_layer is None:
                    cmd = AddTextLayer(store, text_layer)  # type: ignore[arg-type]
                else:
                    cmd = EditTextLayer(store, existing_layer.id, text_layer)  # type: ignore[arg-type]
                result = self._controller.execute_command(cmd)
                if result is not None:
                    self._show_document(result, cmd.label)
                else:
                    # execute_command may return None; refresh anyway.
                    doc = self._controller.document
                    if doc is not None:
                        self._show_document(doc, cmd.label)
            except Exception as exc:
                self.statusBar().showMessage(f"Text layer error: {exc}", 3000)

        dlg.textLayerConfirmed.connect(_on_confirmed)
        dlg.exec()


    def _switch_document(self, document_id: object) -> None:
        try:
            document = self._controller.activate_document(document_id)
            self._show_document(document, "Switched document")
        except (KeyError, RuntimeError) as error:
            QMessageBox.critical(self, "Switch document failed", str(error))

    def _close_document(self, document_id: object) -> None:
        try:
            document = self._controller.activate_document(document_id)
            if document.is_dirty and not self._confirm_document_transition():
                return
            self._controller.close_document(document_id)
            self._project_paths.pop(str(document_id), None)
            remaining = self._controller.open_documents
            if remaining:
                self._controller.activate_document(remaining[0].id)
                self._show_document(remaining[0], "Closed document")
            else:
                self._canvas.clear_preview()
                self._document_bar.set_documents((), "")
                self.setWindowTitle("DIP Studio")
        except (KeyError, RuntimeError) as error:
            QMessageBox.critical(self, "Close document failed", str(error))

    def _copy_selected_layers(self) -> None:
        selected = self._selected_layer_ids()
        if not selected:
            return
        count = self._controller.copy_layers(selected)
        self.statusBar().showMessage(f"Copied {count} layer(s)")

    def _paste_layers(self) -> None:
        try:
            document = self._controller.paste_layers()
            selected = tuple(layer.id for layer in document.layers[-1:])
            self._show_document(document, "Pasted layers", selected)
        except RuntimeError as error:
            self.statusBar().showMessage(str(error))

    def _change_layer(
        self,
        layer_ids: tuple[object, ...],
        visible: bool | None = None,
        opacity: float | None = None,
        blend_mode: str | None = None,
        locked: bool | None = None,
    ) -> None:
        try:
            if visible is not None:
                document = self._controller.set_layers_visibility(layer_ids, visible)
                label = "Shown" if visible else "Hidden"
            elif opacity is not None:
                document = self._controller.set_layers_opacity(layer_ids, opacity)
                label = f"Opacity {opacity:.0%}"
            elif blend_mode is not None:
                document = self._controller.set_layer_blend_mode(layer_ids[0], blend_mode)
                label = f"Blend Mode: {blend_mode.title()}"
            elif locked is not None:
                document = self._controller.set_layer_locked(layer_ids[0], locked)
                label = "Locked" if locked else "Unlocked"
            else:
                return
            self._sidebar.show_layers(document.layers, layer_ids)
            self._update_window_title(document)
            self._refresh_preview()
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
            elif action == "copy_selection":
                self._create_layer_from_selection(cut=False)
                return
            elif action == "cut_selection":
                self._create_layer_from_selection(cut=True)
                return
            elif action == "merge_down":
                self._merge_down()
                return
            elif action == "toggle_lock":
                if layer_ids:
                    doc = self._controller.document
                    if doc is not None:
                        target = next((l for l in doc.layers if l.id == layer_ids[0]), None)
                        if target is not None:
                            self._change_layer(layer_ids, None, None, None, not target.locked)
                return
            elif not layer_ids:
                return
            elif action == "remove":
                document = self._controller.remove_layers(layer_ids)
                label = "Removed selected layers"
                selected_ids = tuple(
                    layer.id for layer in document.layers if layer.id in previous_ids
                )
            elif action == "duplicate":
                document = self._controller.duplicate_layer(layer_ids[0])
                label = "Duplicated layer"
                selected_ids = (
                    next(layer.id for layer in document.layers if layer.id not in existing_ids),
                )
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
            self._refresh_preview()
        except (IndexError, KeyError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Layer update failed", str(error))

    def _merge_down(self) -> None:
        """Merge selected layer with the layer directly below it (Ctrl+E)."""
        selected = self._selected_layer_ids()
        if not selected:
            return
        try:
            document = self._controller.merge_down(selected[0])
            self._show_document(document, "Merged down layer", (selected[0],))
            self._refresh_preview()
            self.statusBar().showMessage("Merged layer down", 2000)
        except Exception as exc:
            QMessageBox.critical(self, "Merge Down Failed", str(exc))

    def _create_layer_from_selection(self, cut: bool = False) -> None:
        """Create a new layer from active canvas selection rect (Ctrl+J / Ctrl+Shift+J)."""
        doc = self._controller.document
        if doc is None:
            self.statusBar().showMessage("No active document", 2000)
            return
        rect = self._canvas.current_selection_image_rect(doc.image.width, doc.image.height)
        if rect is None:
            self.statusBar().showMessage(
                "No selection active. Drag on canvas with selection tool first.", 3000
            )
            return
        selected = self._selected_layer_ids()
        target_layer_id = selected[0] if selected else None
        try:
            document = self._controller.create_layer_from_selection(
                rect, layer_id=target_layer_id, cut=cut
            )
            self._canvas.set_selection_rect(None)
            self._show_document(
                document,
                "Layer via Cut" if cut else "Layer via Copy",
                (document.layers[-1].id,),
            )
            self._refresh_preview()
            self.statusBar().showMessage(
                f"Created new layer from {rect[2]}×{rect[3]} selection", 3000
            )
        except Exception as exc:
            QMessageBox.critical(self, "Selection to Layer Failed", str(exc))

    def _commit_crop_from_selection(self) -> None:
        """Commit crop using active canvas selection rectangle on Enter/Return key."""
        doc = self._controller.document
        if doc is None:
            return
        rect = self._canvas.current_selection_image_rect(doc.image.width, doc.image.height)
        if rect is None:
            return
        x, y, w, h = rect
        if w < 2 or h < 2:
            return
        try:
            document, label = self._apply_crop_target(doc, x, y, w, h)
            self._canvas.set_crop_mode(False)
            self._canvas.set_selection_rect(None)
            self._show_document(document, label)
            self._canvas.fit_to_view()
            if self._active_tool_id == "crop":
                self._canvas.set_crop_mode(True)
                rect_content = self._selected_layer_content_rect(document)
                self._canvas.set_crop_rect_from_image(
                    *rect_content, document.image.width, document.image.height
                )
            self._refresh_preview()
            self.statusBar().showMessage(label, 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Crop Failed", str(exc))

    def _apply_crop_target(
        self, doc: DocumentView, x: int, y: int, width: int, height: int
    ) -> tuple[DocumentView, str]:
        # Crop commits the active document. Layer selection controls which
        # content is displayed/edited, but must not change document geometry.
        document = self._controller.crop_document(x, y, width, height)
        return document, f"Cropped document to {width}×{height}"

    def _select_all(self) -> None:
        """Select entire active document (Ctrl+A)."""
        doc = self._controller.document
        if doc is None:
            return
        from PySide6.QtCore import QRect

        self._canvas.set_selection_rect(QRect(0, 0, self._canvas.width(), self._canvas.height()))
        self.statusBar().showMessage(
            f"Selected all ({doc.image.width}×{doc.image.height})", 2000
        )

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
        tool = self._selected_tool()
        if tool is not None:
            try:
                self._controller.validate_tool_parameters(tool.id, values)
                preview_data = self._controller.preview_processing(tool.id, values)
                if preview_data:
                    self._canvas.show_preview(preview_data)
                self.statusBar().showMessage(f"Preview parameters: {', '.join(values)}")
            except (KeyError, ValueError, RuntimeError) as error:
                QMessageBox.critical(self, "Preview failed", str(error))

    def _apply_parameters(self, values: dict[str, object]) -> None:
        tool = self._selected_tool()
        if tool is not None:
            try:
                self._controller.validate_tool_parameters(tool.id, values)
            except ValueError as error:
                QMessageBox.warning(self, "Invalid parameters", str(error))
                return
            if tool.id == "crop":
                x = int(float(values.get("X", values.get("x", 0))))
                y = int(float(values.get("Y", values.get("y", 0))))
                doc = self._controller.document
                default_w = doc.image.width if doc else 400
                default_h = doc.image.height if doc else 300
                w = int(float(values.get("Width", values.get("width", default_w))))
                h = int(float(values.get("Height", values.get("height", default_h))))
                try:
                    document, label = self._apply_crop_target(doc, x, y, w, h)
                    self._canvas.set_crop_mode(False)
                    self._canvas.set_selection_rect(None)
                    self._sidebar.add_history(label)
                    self._show_document(document, label)
                    self._canvas.fit_to_view()
                    if self._active_tool_id == "crop":
                        self._canvas.set_crop_mode(True)
                        rect_content = self._selected_layer_content_rect(document)
                        self._canvas.set_crop_rect_from_image(
                            *rect_content, document.image.width, document.image.height
                        )
                    self._refresh_preview()
                    self.statusBar().showMessage(label, 3000)
                except Exception as error:
                    QMessageBox.critical(self, "Crop failed", str(error))
                return
            try:
                if self._processing_token is not None:
                    self._processing_token.cancel()
                self.statusBar().showMessage(f"Applying {tool.name}…")
                self._processing_token = self._controller.apply_processing_async(
                    tool.id,
                    values,
                    self._processing_worker.submit,
                    on_done=lambda document: self._on_async_processing_done(
                        document, tool.name
                    ),
                    on_error=lambda error: self._on_async_processing_error(error),
                    on_stale=lambda: self._on_async_processing_stale(tool.name),
                    on_progress=lambda percent: self.statusBar().showMessage(
                        f"Applying {tool.name}: {percent}%"
                    ),
                )
            except (KeyError, ValueError, RuntimeError) as error:
                QMessageBox.critical(self, "Apply failed", str(error))

    def _on_async_processing_done(self, document: DocumentView, tool_name: str) -> None:
        self._processing_token = None
        self._sidebar.add_history(f"Applied parameters: {tool_name}")
        self._show_document(document, f"Applied {tool_name}")
        self._refresh_preview()
        self.statusBar().showMessage(f"Applied {tool_name}", 3000)

    def _on_async_processing_error(self, error: Exception) -> None:
        self._processing_token = None
        if isinstance(error, CancellationError):
            self.statusBar().showMessage("Processing cancelled", 3000)
            return
        QMessageBox.critical(self, "Apply failed", str(error))

    def _on_async_processing_stale(self, tool_name: str) -> None:
        self._processing_token = None
        self.statusBar().showMessage(
            f"Discarded stale {tool_name} result; the document changed.",
            5000,
        )

    def _cancel_parameters(self) -> None:
        tool = self._selected_tool()
        if tool is not None:
            self._sidebar.add_history(f"Cancelled parameters: {tool.name}")
            self._refresh_preview()
            self.statusBar().showMessage("Parameter preview cancelled")

    def _selected_tool(self) -> ToolDefinition | None:
        if self._active_tool_id is None:
            return self._tool_panel.selected_tool()
        return next(
            (tool for tool in self._controller.tools if tool.id == self._active_tool_id),
            None,
        )

    def _undo(self) -> None:
        try:
            document = self._controller.undo()
            self._show_document(document, "Undo")
            self._canvas.fit_to_view()
            if self._active_tool_id == "crop":
                self._canvas.set_crop_mode(True)
                rect = self._selected_layer_content_rect(document)
                self._canvas.set_crop_rect_from_image(
                    *rect, document.image.width, document.image.height
                )
        except RuntimeError as error:
            QMessageBox.information(self, "Undo", str(error))

    def _redo(self) -> None:
        try:
            document = self._controller.redo()
            self._show_document(document, "Redo")
            self._canvas.fit_to_view()
            if self._active_tool_id == "crop":
                self._canvas.set_crop_mode(True)
                rect = self._selected_layer_content_rect(document)
                self._canvas.set_crop_rect_from_image(
                    *rect, document.image.width, document.image.height
                )
        except RuntimeError as error:
            QMessageBox.information(self, "Redo", str(error))

    def _on_history_jump(self, row: int) -> None:
        """Jump to the selected history state when clicked in the History panel."""
        if self._controller.document is None:
            return
        try:
            document = self._controller.history_jump_to(row)
            self._show_document(document, f"History jump to state {row}")
            self._canvas.fit_to_view()
            if self._active_tool_id == "crop":
                self._canvas.set_crop_mode(True)
                rect = self._selected_layer_content_rect(document)
                self._canvas.set_crop_rect_from_image(
                    *rect, document.image.width, document.image.height
                )
            self._refresh_preview()
        except Exception as exc:
            self.statusBar().showMessage(f"History jump error: {exc}", 2000)

    def _on_channel_selected(self, row: int) -> None:
        """Filter canvas preview to show only the selected channel (0=RGB, 1=R, 2=G, 3=B, 4=A)."""
        doc = self._controller.document
        store = self._controller.data_store
        if doc is None or store is None:
            return
        layer = next((la for la in doc.layers if la.buffer_id is not None), None)
        if layer is None or layer.buffer_id is None:
            return
        try:
            import numpy as np

            arr = store.get(layer.buffer_id)
            if row == 0:  # Composite RGB
                self._refresh_preview()
                return
            ch_idx = row - 1  # 0=R, 1=G, 2=B, 3=Alpha
            if arr.ndim == 2:
                single_ch = arr
            elif ch_idx < arr.shape[2]:
                single_ch = arr[:, :, ch_idx]
            else:
                return
            ch3 = np.stack([single_ch, single_ch, single_ch], axis=-1)
            self._canvas.set_preview_array(ch3)
            ch_names = ["RGB", "Red", "Green", "Blue", "Alpha"]
            name = ch_names[row] if row < len(ch_names) else f"Channel {row}"
            self.statusBar().showMessage(f"Viewing channel: {name}", 2000)
        except (KeyError, RuntimeError, ValueError) as error:
            self.statusBar().showMessage(f"Preview failed: {error}", 4000)

    def _open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open project", "", "DIP projects (*.dip);;All files (*)"
        )
        if not filename:
            return
        try:
            document = self._controller.open_project(Path(filename))
            self._project_paths[str(document.id)] = Path(filename)
            self._show_document(document, "Opened project")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Open project failed", str(error))

    def _save_project(self) -> bool:
        document = self._controller.document
        if document is None:
            return False
        path = self._project_paths.get(str(document.id))
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
            self._project_paths[str(document.id)] = path
            self._show_document(document, "Saved project")
            return True
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, "Save project failed", str(error))
            return False

    def _open_image(self) -> None:
        if not self._confirm_document_transition():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.webp *.ppm);;All files (*)"
        )
        if not filename:
            return
        try:
            document = self._controller.open_image(Path(filename))
            selected_ids = (document.layers[0].id,) if document.layers else ()
            self._show_document(document, "Opened image", selected_ids=selected_ids)
            self._sidebar.select_panel("Layers")
            self._canvas.fit_to_view()
            self._canvas.setFocus()
            if self._active_tool_id == "crop":
                self._canvas.set_crop_mode(True)
            else:
                self._canvas.set_selection_rect(None)
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
            if not selected_ids and document.layers:
                selected_ids = (document.layers[0].id,)
        self._sidebar.show_layers(document.layers, selected_ids)

        if hasattr(self._sidebar, 'set_history_states'):
            labels = self._controller.history_labels()
            current_idx = self._controller.history_current_index()
            self._sidebar.set_history_states(labels, current_idx)

        # ── Fast direct-array rendering path (no JPEG/PNG encoding overhead) ──
        raw_arr = None
        renderer = getattr(self._controller, "_renderer", None)
        if renderer is not None and hasattr(renderer, "render_raw"):
            from dip_studio.rendering.ports import RenderRequest
            try:
                raw_arr = renderer.render_raw(
                    RenderRequest(str(document.id), document.image.width, document.image.height)
                )
            except Exception as exc:
                self.statusBar().showMessage(f"Preview render failed: {exc}", 3000)
                raw_arr = None

        if raw_arr is not None:
            self._canvas.set_preview_array(raw_arr)
        else:
            try:
                preview = self._controller.preview(document.image.width, document.image.height)
                self._canvas.show_preview(preview)
            except Exception as exc:
                self.statusBar().showMessage(f"Preview render failed: {exc}", 3000)
                self._canvas.clear_preview()
            raw_arr = None  # used below for navigator only

        if self._active_tool_id == "crop":
            self._canvas.set_crop_mode(True)
            rect = self._selected_layer_content_rect(document)
            self._canvas.set_crop_rect_from_image(
                *rect, document.image.width, document.image.height
            )
        if hasattr(self._sidebar, "update_navigator"):
            # Navigator uses the byte preview; compute lazily only when needed.
            try:
                preview_bytes = self._controller.preview(document.image.width, document.image.height)
                self._sidebar.update_navigator(preview_bytes, self._canvas.zoom)
            except Exception as exc:
                self.statusBar().showMessage(f"Navigator preview failed: {exc}", 3000)
        self.statusBar().showMessage(
            f"{document.name} — {document.image.width} × {document.image.height} — "
            f"{self._canvas.zoom:.0%}"
        )
        self._update_window_title(document)
        self._document_bar.set_documents(
            self._controller.open_documents, document.id
        )

    def _update_window_title(self, document: DocumentView) -> None:
        active = self._controller.document
        dirty_marker = "*" if active is not None and active.is_dirty else ""
        self.setWindowTitle(f"{dirty_marker}{document.name} — DIP Studio")
        self._document_bar.set_documents(
            self._controller.open_documents, document.id
        )

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
        palette_handlers = {
            "file.new": self._show_new_project,
            "file.open_project": self._open_project,
            "file.open_image": self._open_image,
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
            "layer.copy": self._copy_selected_layers,
            "layer.paste": self._paste_layers,
            "view.theme": self._toggle_theme,
            "canvas.zoom_in": self._zoom_in,
            "canvas.zoom_out": self._zoom_out,
            "canvas.fit": self._fit_canvas,
            "canvas.actual_size": self._actual_size,
            "canvas.grid": lambda: self._grid_action.trigger(),
            "canvas.before_after": lambda: self._before_after_action.trigger(),
        }
        for command_id, handler in palette_handlers.items():
            self._register_ui_command(command_id, handler)
        commands = (
            ("New project", lambda: self._dispatch_ui_command("file.new")),
            ("Open project", lambda: self._dispatch_ui_command("file.open_project")),
            ("Open image", lambda: self._dispatch_ui_command("file.open_image")),
            ("Save project", lambda: self._dispatch_ui_command("file.save")),
            ("Keyboard shortcuts", self._show_shortcut_editor),
            ("Undo", lambda: self._dispatch_ui_command("edit.undo")),
            ("Redo", lambda: self._dispatch_ui_command("edit.redo")),
            ("Add layer", lambda: self._dispatch_ui_command("layer.add")),
            ("Duplicate selected layer", lambda: self._dispatch_ui_command("layer.duplicate")),
            ("Remove selected layers", lambda: self._dispatch_ui_command("layer.remove")),
            ("Move selected layer up", lambda: self._dispatch_ui_command("layer.move_up")),
            ("Move selected layer down", lambda: self._dispatch_ui_command("layer.move_down")),
            ("Toggle selected layer visibility", lambda: self._dispatch_ui_command("layer.toggle_visibility")),
            ("Rename selected layer", lambda: self._dispatch_ui_command("layer.rename")),
            ("Copy selected layers", lambda: self._dispatch_ui_command("layer.copy")),
            ("Paste layers", lambda: self._dispatch_ui_command("layer.paste")),
            ("Toggle theme", lambda: self._dispatch_ui_command("view.theme")),
            ("Zoom in", lambda: self._dispatch_ui_command("canvas.zoom_in")),
            ("Zoom out", lambda: self._dispatch_ui_command("canvas.zoom_out")),
            ("Fit canvas", lambda: self._dispatch_ui_command("canvas.fit")),
            ("Actual size", lambda: self._dispatch_ui_command("canvas.actual_size")),
            ("Toggle grid", lambda: self._dispatch_ui_command("canvas.grid")),
            ("Toggle before/after", lambda: self._dispatch_ui_command("canvas.before_after")),
        ) + tuple(
            (
                f"Tool: {tool.name}",
                lambda tool_id=tool.id: self._dispatch_ui_command(f"tool.{tool_id}"),
            )
            for tool in self._controller.tools
        ) + tuple(
            (
                f"Process: {tool.name}",
                self._processing_action(
                    tool.id,
                    {},
                    dialog=bool(tool.parameters),
                ),
            )
            for tool in self._controller.tools
            if tool.category in {"Filter", "Analysis"} and tool.id
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
        restored = True
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            restored = self.restoreGeometry(geometry) and restored
        if isinstance(state, QByteArray) and not state.isEmpty():
            restored = self.restoreState(state) and restored
        if not restored:
            self._reset_workspace(save=False)
            self.statusBar().showMessage(
                "Saved workspace was invalid; default layout restored", 5000
            )
        panel = settings.value("workspacePanel", 0, type=int)
        if 0 <= panel < self._sidebar.tabs.count():
            self._sidebar.tabs.setCurrentIndex(panel)

    def _reset_workspace(self, *, save: bool = True) -> None:
        self.resize(1200, 760)
        self._workspace_dock.show()
        self._workspace_action.setChecked(True)
        self._sidebar.tabs.setCurrentIndex(0)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tools_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._workspace_dock)
        if save:
            self._save_workspace()
        self.statusBar().showMessage("Workspace reset")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_document_transition():
            event.ignore()
            return
        self._processing_worker.cancel_all()
        self._processing_worker.wait_for_done()
        self._save_shortcut_overrides()
        self._save_workspace()
        self._save_workspace()
        event.accept()

    def _toggle_theme(self) -> None:
        self._tokens = LIGHT if self._tokens == DARK else DARK
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setPalette(palette_for(self._tokens))
        self.setStyleSheet(
            stylesheet_for(self._tokens)
            + f"""
            QMainWindow, QDockWidget, QToolBar {{
                background: {self._tokens.surface};
                color: {self._tokens.foreground};
            }}
            QWidget#dockPanel {{
                background: {self._tokens.surface};
            }}
            QWidget#dockPanel {{
                background: {self._tokens.surface};
            }}
            QWidget#dockPanelHeader {{
                background: {self._tokens.surface};
                border: 0;
            }}
            QLabel#dockGrip {{
                background: transparent;
                color: {self._tokens.foreground_muted};
                font-size: 9px;
                letter-spacing: 2px;
            }}
            QLabel#dockGrip:hover {{
                color: {self._tokens.foreground};
            }}
            QToolButton#dockCloseButton {{
                background: transparent;
                color: {self._tokens.foreground_muted};
                border: 0;
                font-size: 13px;
            }}
            QToolButton#dockCloseButton:hover {{
                background: {self._tokens.accent};
                color: {self._tokens.accent_foreground};
            }}
            QToolButton#dockCollapseButton {{
                background: transparent;
                color: {self._tokens.foreground_muted};
                border: 0;
                font-size: 13px;
                padding: 0;
            }}
            QToolButton#dockCollapseButton:hover {{
                background: {self._tokens.field};
                color: {self._tokens.foreground};
            }}
            QFrame#dockDropIndicator {{
                background: {self._tokens.accent};
                border: 2px solid {self._tokens.accent};
            }}
            QToolBar {{
                border: 0;
                spacing: 6px;
                padding: 5px 8px;
            }}
            QToolButton#toolButton {{
                background: {self._tokens.surface_alt};
                border: 1px solid {self._tokens.border};
                border-radius: 6px;
                color: {self._tokens.foreground};
            }}
            QWidget#toolGroupContainer {{
                background: transparent;
            }}
            QFrame#toolGridPopup {{
                background: {self._tokens.surface_alt};
                border: 1px solid {self._tokens.border};
                border-radius: 4px;
            }}
            QToolButton#toolGridItem {{
                background: {self._tokens.surface};
                color: {self._tokens.foreground};
                border: 1px solid {self._tokens.border};
                border-radius: 3px;
                padding: 3px;
            }}
            QToolButton#toolGridItem:hover {{
                background: {self._tokens.accent};
                border-color: {self._tokens.accent};
            }}
            QToolButton#toolGroupArrow {{
                background: {self._tokens.surface_alt};
                color: {self._tokens.foreground_muted};
                border: 0;
                border-radius: 2px;
                padding: 0;
                font-size: 9px;
                font-weight: 600;
            }}
            QToolButton#toolGroupArrow:hover {{
                background: {self._tokens.accent};
                color: {self._tokens.accent_foreground};
            }}
            QToolButton#toolButton:hover {{
                border-color: {self._tokens.accent};
                background: {self._tokens.surface};
            }}
            QToolButton#toolButton:checked {{
                border: 2px solid {self._tokens.accent};
                background: {self._tokens.surface_alt};
                color: {self._tokens.foreground};
            }}
            QToolButton#toolButton:checked:hover {{
                background: {self._tokens.surface};
            }}
            QTabWidget::pane, QListWidget, QLineEdit, QDoubleSpinBox {{
                background: {self._tokens.surface_alt};
                color: {self._tokens.foreground};
                border: 1px solid {self._tokens.border};
            }}
            QTabBar::tab {{
                background: {self._tokens.surface_alt};
                color: {self._tokens.foreground};
                padding: 7px 10px;
            }}
            QTabBar::tab:selected {{
                background: {self._tokens.accent};
                color: {self._tokens.surface};
            }}
            """
        )

    def _rotate_image(self, degrees: int) -> None:
        """Rotate the active layer's content."""
        document = self._controller.document
        if document is None:
            return
        params = {"degrees": degrees}
        try:
            self._controller.apply_processing("rotate", params)
            doc = self._controller.document
            assert doc is not None
            self._show_document(doc, f"Rotate {degrees}°", ())
        except (KeyError, Exception) as e:
            self.statusBar().showMessage(f"Rotate not available: {e}", 3000)

    def _flip_image(self, direction: str) -> None:
        """Flip the active layer's content horizontally or vertically."""
        document = self._controller.document
        if document is None:
            return
        try:
            self._controller.apply_processing("flip", {"direction": direction})
            doc = self._controller.document
            assert doc is not None
            self._show_document(doc, f"Flip {direction}", ())
        except (KeyError, Exception) as e:
            self.statusBar().showMessage(f"Flip not available: {e}", 3000)

    def _quick_apply(self, operation: str, params: dict) -> None:
        """Apply a processing operation with default parameters (no dialog)."""
        if self._controller.document is None:
            self.statusBar().showMessage("No active document", 2000)
            return
        try:
            doc = self._controller.apply_processing(operation, params)
            self._show_document(doc, operation.replace('_', ' ').title(), ())
            self._refresh_preview()
        except KeyError:
            self.statusBar().showMessage(f"Operation '{operation}' not available", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Error: {e}", 3000)

    def _apply_filter_dialog(self, operation: str) -> None:
        """Open tool parameters panel for a specific filter operation."""
        try:
            tool = self._controller._tool_registry.get(operation)
        except KeyError:
            self.statusBar().showMessage(f"Filter '{operation}' not registered", 3000)
            return
        self._select_tool(tool.id)
        self._sidebar.select_panel("Properties")

    def _refresh_preview(self) -> None:
        """Request a fresh render from the renderer and update the canvas."""
        document = self._controller.document
        if document is None:
            return
        try:
            preview = self._controller.preview(
                max(1, self._canvas.width()),
                max(1, self._canvas.height()),
                self._canvas.zoom,
            )
            self._canvas.show_preview(preview)
            if hasattr(self._sidebar, 'update_navigator'):
                self._sidebar.update_navigator(preview, self._canvas.zoom)
        except Exception as exc:
            self.statusBar().showMessage(f"Preview render failed: {exc}", 3000)
            self._canvas.clear_preview()

    def _show_histogram(self) -> None:
        """Show the pixel intensity histogram for the active layer."""
        document = self._controller.document
        if document is None:
            self.statusBar().showMessage("No active document", 2000)
            return
        store = self._controller.data_store
        layer = next((la for la in document.layers if la.buffer_id is not None), None)
        if layer is None or store is None:
            self.statusBar().showMessage("No image data to analyze", 2000)
            return
        try:
            arr = store.get(layer.buffer_id)
            dlg = HistogramDialog.from_buffer(arr, parent=self)
            dlg.show()
        except Exception as exc:
            self.statusBar().showMessage(f"Histogram error: {exc}", 3000)

    def _show_image_stats(self) -> None:
        """Show per-channel image statistics (min, max, mean, std, median)."""
        document = self._controller.document
        if document is None:
            self.statusBar().showMessage("No active document", 2000)
            return
        store = self._controller.data_store
        layer = next((la for la in document.layers if la.buffer_id is not None), None)
        if layer is None or store is None:
            self.statusBar().showMessage("No image data to analyze", 2000)
            return
        try:
            arr = store.get(layer.buffer_id)
            doc = document
            info = (
                f"{doc.image.width}×{doc.image.height} "
                f"{doc.image.color_space} {doc.image.bit_depth}-bit"
            )
            dlg = ImageStatsDialog.from_buffer(arr, image_info=info, parent=self)
            dlg.show()
        except Exception as exc:
            self.statusBar().showMessage(f"Statistics error: {exc}", 3000)

    def _export_image(self) -> None:
        """Export the active document to an image file (File > Export As)."""
        if self._controller.document is None:
            self.statusBar().showMessage("No active document", 2000)
            return
        dlg = ExportDialog(self)
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return
        fmt = dlg.selected_format()
        quality = dlg.selected_quality()
        ext_map = {
            "png": "*.png", "jpeg": "*.jpg *.jpeg", "bmp": "*.bmp",
            "tiff": "*.tiff *.tif", "ppm": "*.ppm",
        }
        filter_str = f"{fmt.upper()} Files ({ext_map.get(fmt, '*.' + fmt)})"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export Image", "", filter_str
        )
        if not path_str:
            return
        path = Path(path_str)
        if not path.suffix:
            path = path.with_suffix(f".{fmt}")
        try:
            self._controller.export_image(path, quality=quality)
            self.statusBar().showMessage(f"Exported → {path.name}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _place_image(self) -> None:
        """Place an image file as a new layer (File > Place Image)."""
        if self._controller.document is None:
            self.statusBar().showMessage("No active document — open an image first", 3000)
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Place Image as Layer",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.webp *.ppm)",
        )
        if not path_str:
            return
        try:
            doc = self._controller.place_image(Path(path_str))
            self._show_document(doc, f"Place {Path(path_str).stem}", ())
            self.statusBar().showMessage(
                f"Placed '{Path(path_str).name}' as new layer", 2000
            )
        except Exception as exc:
            QMessageBox.critical(self, "Place Error", str(exc))

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About DIP Studio",
            "<b>DIP Studio</b><br/>"
            "Professional Digital Image Processing &amp; Computer Vision Studio<br/><br/>"
            "Architecture: Clean layers — Domain / Application / Infrastructure / Processing / Rendering / Presentation<br/>"
            "Version: 0.1.0"
        )
