"""Grouped tool selector for the editor's presentation layer."""

from math import ceil, sqrt

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QToolButton,
    QWidget,
)

from dip_studio.application.tool_registry import ToolDefinition
from dip_studio.presentation.vector_icons import icon_for


class ToolPanel(QWidget):
    """Displays tool groups and emits the selected tool name."""

    toolSelected = Signal(str)

    _GROUPS = (
        ("General", ("select",)),
        (
            "Selection",
            ("selection", "ellipse_selection", "lasso", "polygon_selection", "color_selection"),
        ),
        ("Transform", ("crop", "move", "transform", "rotate")),
        ("Filter", ("blur", "edge")),
        ("Paint", ("gradient", "brush", "pencil", "eraser", "fill")),
        ("Retouch", ("clone",)),
        ("Navigation", ("hand", "zoom")),
        ("Sampling", ("eyedropper",)),
        ("Vector", ("text", "shape")),
        ("Analysis", ("histogram", "threshold", "morphology", "segment")),
    )

    def __init__(self, tools: tuple[ToolDefinition, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toolsPanel")
        self.setMinimumWidth(66)
        self.setMaximumWidth(78)
        self._tools_by_id = {tool.id: tool for tool in tools}
        self._tools_by_name = {tool.name: tool for tool in tools}
        self._tool_buttons: dict[str, QToolButton] = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        layout = QGridLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(4)

        row = 0
        for group_name, tool_ids in self._GROUPS:
            group_tools = tuple(
                self._tools_by_id[tool_id]
                for tool_id in tool_ids
                if tool_id in self._tools_by_id
            )
            if not group_tools:
                continue
            container, button = self._make_group_button(group_name, group_tools)
            for tool in group_tools:
                self._tool_buttons[tool.name] = button
            self._tool_group.addButton(button)
            layout.addWidget(container, row, 0, Qt.AlignmentFlag.AlignHCenter)
            row += 1
        layout.setRowStretch(row, 1)

        if tools:
            self.select_tool(tools[0].name, emit=False)

    def select_tool(self, name: str, *, emit: bool = True) -> None:
        tool = self._tools_by_name.get(name)
        button = self._tool_buttons.get(name)
        if tool is None or button is None:
            return
        button.setChecked(True)
        button.setIcon(icon_for(tool.id))
        button.setToolTip(f"{tool.name}\n{tool.description}")
        if emit:
            self.toolSelected.emit(name)

    def selected_tool(self) -> ToolDefinition | None:
        for name, button in self._tool_buttons.items():
            if button.isChecked():
                return self._tools_by_name[name]
        return None

    def _make_group_button(
        self, group_name: str, tools: tuple[ToolDefinition, ...]
    ) -> tuple[QWidget, QToolButton]:
        button = QToolButton(self)
        button.setObjectName("toolButton")
        button.setCheckable(True)
        button.setAutoRaise(False)
        button.setIcon(icon_for(tools[0].id))
        button.setIconSize(QSize(17, 17))
        button.setFixedSize(44, 44)
        button.clicked.connect(lambda _checked=False, name=tools[0].name: self.toolSelected.emit(name))
        if len(tools) == 1:
            return button, button

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("toolGridPopup")
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        popup_layout = QGridLayout(popup)
        popup_layout.setContentsMargins(6, 6, 6, 6)
        popup_layout.setHorizontalSpacing(4)
        popup_layout.setVerticalSpacing(4)
        columns = max(2, ceil(sqrt(len(tools))))
        for tool in tools:
            shortcut = f" [{tool.shortcut}]" if tool.shortcut else ""
            tool_button = QToolButton(popup)
            tool_button.setObjectName("toolGridItem")
            tool_button.setIcon(icon_for(tool.id))
            tool_button.setIconSize(QSize(20, 20))
            tool_button.setFixedSize(34, 34)
            tool_button.setToolTip(f"{tool.name}{shortcut}\n{tool.description}")
            tool_button.clicked.connect(
                lambda _checked=False, name=tool.name, panel=popup: (
                    panel.hide(),
                    self.toolSelected.emit(name),
                )
            )
            index = tools.index(tool)
            popup_layout.addWidget(tool_button, index // columns, index % columns)
        arrow = QToolButton(self)
        arrow.setObjectName("toolGroupArrow")
        arrow.setText("◢")
        arrow.setToolTip(f"Choose a {group_name} tool")
        arrow.setFixedSize(12, 12)
        arrow.clicked.connect(
            lambda _checked=False, popup=popup, control=arrow: self._show_tool_grid(
                popup, control
            )
        )
        container = QWidget(self)
        container.setObjectName("toolGroupContainer")
        container.setFixedSize(44, 44)
        button.setParent(container)
        arrow.setParent(container)
        button.move(0, 0)
        arrow.move(31, 31)
        button.raise_()
        arrow.raise_()
        button.setToolTip(f"{group_name} — click the corner arrow to choose a tool")
        return container, button

    @staticmethod
    def _show_tool_grid(popup: QFrame, control: QToolButton) -> None:
        popup.adjustSize()
        popup.move(control.mapToGlobal(control.rect().bottomLeft()))
        popup.show()
        popup.raise_()
        popup.activateWindow()
