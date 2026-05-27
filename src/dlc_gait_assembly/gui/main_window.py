from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    widget_factory: Callable[[], QWidget] | None = None
    enabled: bool = False
    description: str = ""
    status: str = "Coming soon"
    accent: str = "#94a3b8"


TOOL_SPECS = [
    ToolSpec(
        "video_processing",
        "Video Processing",
        VideoEditorWidget,
        True,
        "Bulk edits, trims, crops, inversions, enhancements, and H.264 export.",
        "Ready",
        "#0891b2",
    ),
    ToolSpec(
        "manual_calibration",
        "Manual Calibration",
        description="Set up calibration references and scale checks.",
        accent="#7c3aed",
    ),
    ToolSpec(
        "data_preprocessing",
        "Data Preprocessing",
        description="Prepare tracking outputs before gait assembly.",
        accent="#16a34a",
    ),
    ToolSpec(
        "gait_parameter_assembly",
        "Gait Parameter Assembly",
        description="Assemble stride, stance, swing, and gait summary outputs.",
        accent="#ea580c",
    ),
]


class MainWindow(QMainWindow):
    def __init__(self, initial_tool_id: str | None = None):
        super().__init__()
        self.setWindowTitle("DLC Gait Assembler")
        self.resize(1280, 820)
        self._active_tool: QWidget | None = None
        self._active_tool_id: str | None = None
        self._tool_widgets: dict[str, QWidget] = {}
        self._stack = QStackedWidget()
        self._main_menu = MainMenuWidget(TOOL_SPECS)
        self._main_menu.tool_requested.connect(self._open_tool)
        self._stack.addWidget(self._main_menu)
        self.setCentralWidget(self._stack)
        self._build_navigation()
        if initial_tool_id is None:
            self._show_main_menu()
        else:
            self._open_tool(initial_tool_id)

    def closeEvent(self, event):
        for tool in self._tool_widgets.values():
            if hasattr(tool, "can_close") and not tool.can_close(self):
                event.ignore()
                return

        self._release_all_tools()

        super().closeEvent(event)

    def _build_navigation(self) -> None:
        navigation = self.menuBar().addMenu("Navigation")
        main_menu_action = navigation.addAction("Main Menu")
        main_menu_action.triggered.connect(self._show_main_menu)
        navigation.addSeparator()

        for spec in TOOL_SPECS:
            action = navigation.addAction(spec.label)
            action.setEnabled(spec.enabled)
            if spec.enabled:
                action.triggered.connect(lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id))

    def _show_main_menu(self) -> None:
        if not self._can_leave_active_tool():
            return

        self._active_tool = None
        self._active_tool_id = None
        self.setWindowTitle("DLC Gait Assembler")
        self._stack.setCurrentWidget(self._main_menu)

    def _open_tool(self, tool_id: str) -> None:
        if not self._can_leave_active_tool():
            return

        spec = self._tool_spec(tool_id)
        if spec.widget_factory is None or not spec.enabled:
            return

        tool = self._tool_widgets.get(tool_id)
        if tool is None:
            tool = spec.widget_factory()
            self._tool_widgets[tool_id] = tool
            self._stack.addWidget(tool)

        self._active_tool = tool
        self._active_tool_id = tool_id
        self.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self._stack.setCurrentWidget(tool)

    def _tool_spec(self, tool_id: str) -> ToolSpec:
        for spec in TOOL_SPECS:
            if spec.id == tool_id:
                return spec
        raise ValueError(f"Unknown tool: {tool_id}")

    def _can_leave_active_tool(self) -> bool:
        if self._active_tool is None or not hasattr(self._active_tool, "can_close"):
            return True
        return bool(self._active_tool.can_close(self))

    def _release_all_tools(self) -> None:
        for tool in self._tool_widgets.values():
            if hasattr(tool, "release_resources"):
                tool.release_resources()
        self._tool_widgets.clear()
        self._active_tool = None
        self._active_tool_id = None


class MainMenuWidget(QWidget):
    tool_requested = Signal(str)

    def __init__(self, tools: list[ToolSpec]):
        super().__init__()
        self._tools = tools
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 44, 56, 52)
        root.setSpacing(24)

        header_panel = QFrame()
        header_panel.setObjectName("MainMenuHeader")
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(28, 24, 28, 24)
        header_layout.setSpacing(8)

        eyebrow = QLabel("GAIT WORKSPACE")
        eyebrow.setObjectName("MainMenuEyebrow")
        header_layout.addWidget(eyebrow)

        header = QLabel("DLC Gait Assembler")
        header.setObjectName("MainMenuTitle")
        header_layout.addWidget(header)

        subtitle = QLabel("Select a module to continue.")
        subtitle.setObjectName("MainMenuSubtitle")
        header_layout.addWidget(subtitle)

        root.addWidget(header_panel)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)

        section_header = QLabel("Modules")
        section_header.setObjectName("SectionHeader")
        root.insertWidget(1, section_header)

        root.addStretch(1)

        for index, spec in enumerate(self._tools):
            button = MenuCard(spec)
            if spec.enabled:
                button.clicked.connect(self.tool_requested.emit)
            grid.addWidget(button, index // 2, index % 2)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f4f6f8;
                color: #111827;
                font-size: 13px;
            }
            QFrame#MainMenuHeader {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 8px;
            }
            QLabel#MainMenuEyebrow {
                color: #0891b2;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#MainMenuTitle {
                color: #0f172a;
                font-size: 30px;
                font-weight: 800;
            }
            QLabel#MainMenuSubtitle {
                color: #475569;
                font-size: 14px;
            }
            QLabel#SectionHeader {
                color: #334155;
                font-size: 13px;
                font-weight: 800;
                padding-top: 4px;
            }
            QFrame#MenuCard {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 8px;
            }
            QFrame#MenuCard[enabledCard="true"]:hover {
                border-color: #0891b2;
                background: #f2fbfc;
            }
            QFrame#MenuCard[enabledCard="false"] {
                background: #eef1f5;
                border-color: #dbe1ea;
            }
            QLabel#CardTitle {
                color: #111827;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#CardDescription {
                color: #526173;
                font-size: 12px;
            }
            QLabel#CardStatus {
                border-radius: 8px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#CardStatus[enabledCard="true"] {
                color: #0e7490;
                background: #cffafe;
            }
            QLabel#CardStatus[enabledCard="false"] {
                color: #94a3b8;
                background: #e2e8f0;
            }
            QLabel#DisabledTitle {
                color: #64748b;
                font-size: 17px;
                font-weight: 700;
            }
            """
        )


class MenuCard(QFrame):
    clicked = Signal(str)

    def __init__(self, spec: ToolSpec):
        super().__init__()
        self._spec = spec
        self.setObjectName("MenuCard")
        self.setProperty("enabledCard", spec.enabled)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if spec.enabled:
            self.setCursor(Qt.PointingHandCursor)
        if not spec.enabled:
            self.setToolTip("Not available yet.")
        self._build_ui(spec)

    def _build_ui(self, spec: ToolSpec) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        accent = QLabel()
        accent.setFixedSize(10, 10)
        accent.setStyleSheet(f"background: {spec.accent}; border-radius: 5px;")
        top_row.addWidget(accent, 0, Qt.AlignTop)

        title = QLabel(spec.label)
        title.setObjectName("CardTitle" if spec.enabled else "DisabledTitle")
        top_row.addWidget(title, 1)

        status = QLabel(spec.status)
        status.setObjectName("CardStatus")
        status.setProperty("enabledCard", spec.enabled)
        top_row.addWidget(status, 0, Qt.AlignRight)
        root.addLayout(top_row)

        description = QLabel(spec.description)
        description.setObjectName("CardDescription")
        description.setWordWrap(True)
        root.addWidget(description)
        root.addStretch(1)

    def mousePressEvent(self, event) -> None:
        if self._spec.enabled and event.button() == Qt.LeftButton:
            self.clicked.emit(self._spec.id)
        super().mousePressEvent(event)
