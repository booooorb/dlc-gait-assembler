from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui.deeplabcut.window import DeepLabCutWidget
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget
from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget


MAIN_MENU_CONTENT_WIDTH = 1080
WORKFLOW_ROW_HEIGHT = 78
APP_TOOLBAR_HEIGHT = 50
MAIN_MENU_LOGO_HEIGHT = 24
MAIN_MENU_LOGO_MAX_WIDTH = 104

HEADER_STAGE_LABELS = {
    "manual_calibration": "Calibration",
    "video_processing": "Video processing",
    "deeplabcut": "DeepLabCut",
    "gait_parameter_analysis": "Gait analysis",
    "pca_random_forest": "PCA / RF",
}


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    widget_factory: Callable[[], QWidget] | None = None
    enabled: bool = False
    description: str = ""


TOOL_SPECS = [
    ToolSpec(
        "manual_calibration",
        "Calibration",
        ManualCalibrationWidget,
        True,
        description="Set measurement references and check spatial scale.",
    ),
    ToolSpec(
        "video_processing",
        "Video Processing",
        VideoEditorWidget,
        True,
        "Prepare videos, regions, trims, enhancements, and H.264 export.",
    ),
    ToolSpec(
        "deeplabcut",
        "DeepLabCut",
        DeepLabCutWidget,
        True,
        description="Train, evaluate, and analyze pose estimation projects.",
    ),
    ToolSpec(
        "gait_parameter_analysis",
        "Gait Parameter Analysis",
        GaitAnalysisWidget,
        True,
        description="Assemble stride, stance, swing, and gait outputs.",
    ),
    ToolSpec(
        "pca_random_forest",
        "PCA and Random Forest Analysis",
        PcaRandomForestWidget,
        True,
        description="Reduce gait features and build classification models.",
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
        self._build_shell()
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

    def apply_theme(self) -> None:
        self._apply_shell_style()
        self._main_menu._apply_style()
        for tool in self._tool_widgets.values():
            apply_style = getattr(tool, "_apply_style", None)
            if apply_style is not None:
                apply_style()
        self._refresh_stage_navigation()
        self.update()

    def _build_shell(self) -> None:
        shell = QWidget()
        shell.setObjectName("AppShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("AppToolbar")
        toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(18, 0, 16, 0)
        toolbar_layout.setSpacing(0)

        home_button = QPushButton("DLC Gait Assembler")
        home_button.setObjectName("HomeNavigationButton")
        home_button.setCursor(Qt.PointingHandCursor)
        home_button.setToolTip("Return to the workflow")
        home_button.clicked.connect(self._show_main_menu)
        toolbar_layout.addWidget(home_button)

        divider = QFrame()
        divider.setObjectName("ToolbarDivider")
        divider.setFrameShape(QFrame.VLine)
        toolbar_layout.addWidget(divider)

        self._stage_navigation_buttons: dict[str, QPushButton] = {}
        for spec in TOOL_SPECS:
            button = QPushButton(HEADER_STAGE_LABELS[spec.id])
            button.setObjectName("StageNavigationButton")
            button.setProperty("activeStage", False)
            button.setEnabled(spec.enabled)
            button.setCursor(Qt.PointingHandCursor if spec.enabled else Qt.ArrowCursor)
            button.setToolTip(spec.label)
            button.setAccessibleName(f"Open {spec.label}")
            if spec.enabled:
                button.clicked.connect(lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id))
            self._stage_navigation_buttons[spec.id] = button
            toolbar_layout.addWidget(button)

        toolbar_layout.addStretch(1)

        partner_marks = QFrame()
        partner_marks.setObjectName("PartnerMarks")
        partner_layout = QHBoxLayout(partner_marks)
        partner_layout.setContentsMargins(8, 3, 8, 3)
        partner_layout.setSpacing(10)
        partner_layout.addWidget(_main_menu_logo_label("choforcelab.png"))
        partner_layout.addWidget(_main_menu_logo_label("NERVES_Logo.png"))
        toolbar_layout.addWidget(partner_marks)

        shell_layout.addWidget(toolbar)
        shell_layout.addWidget(self._stack, 1)
        self.setCentralWidget(shell)
        self._shell = shell
        self._apply_shell_style()

    def _apply_shell_style(self) -> None:
        self._shell.setStyleSheet(
            theme.stylesheet(
                """
                QWidget#AppShell {
                    background: {theme.BACKGROUND};
                    color: {theme.TEXT};
                }
                QFrame#AppToolbar {
                    background: {theme.SURFACE};
                    border: 0;
                    border-bottom: 1px solid {theme.BORDER};
                }
                QPushButton#HomeNavigationButton {
                    background: transparent;
                    border: 0;
                    border-radius: 0;
                    color: {theme.TEXT};
                    font-size: 15px;
                    font-weight: 650;
                    padding: 4px 0;
                    margin-right: 12px;
                }
                QPushButton#HomeNavigationButton:hover {
                    color: {theme.CONNECTOR};
                }
                QFrame#ToolbarDivider {
                    background: {theme.BORDER};
                    border: 0;
                    min-width: 1px;
                    max-width: 1px;
                    min-height: 18px;
                    max-height: 18px;
                    margin-right: 4px;
                }
                QPushButton#StageNavigationButton {
                    background: transparent;
                    border: 0;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                    font-weight: 550;
                    min-height: 48px;
                    padding: 0 9px;
                }
                QPushButton#StageNavigationButton:hover {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QPushButton#StageNavigationButton:focus {
                    border: 0;
                    border-bottom: 2px solid {theme.TOOL_1};
                    color: {theme.TEXT};
                }
                QPushButton#StageNavigationButton[activeStage="true"] {
                    border: 0;
                    border-bottom: 2px solid {theme.TOOL_1};
                    color: {theme.TEXT};
                    font-weight: 650;
                }
                QFrame#PartnerMarks {
                    background: {theme.LOGO_SURFACE};
                    border: 1px solid {theme.LOGO_BORDER};
                    border-radius: 2px;
                    margin-left: 10px;
                }
                QLabel#MainMenuLogo {
                    background: transparent;
                }
                """
            )
        )

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
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

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
        self._refresh_stage_navigation()
        self._show_widget(tool)

    def _refresh_stage_navigation(self) -> None:
        for tool_id, button in self._stage_navigation_buttons.items():
            button.setProperty("activeStage", tool_id == self._active_tool_id)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _tool_spec(self, tool_id: str) -> ToolSpec:
        for spec in TOOL_SPECS:
            if spec.id == tool_id:
                return spec
        raise ValueError(f"Unknown tool: {tool_id}")

    def _can_leave_active_tool(self) -> bool:
        if self._active_tool is None or not hasattr(self._active_tool, "can_close"):
            return True
        return bool(self._active_tool.can_close(self))

    def _show_widget(self, widget: QWidget) -> None:
        self._stack.setCurrentWidget(widget)

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
        self.setObjectName("MainMenuWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._tools = tools
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 36)
        root.setSpacing(0)

        content = QWidget()
        content.setObjectName("MenuContent")
        content.setMinimumWidth(840)
        content.setMaximumWidth(MAIN_MENU_CONTENT_WIDTH)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        section_title = QLabel("Workflow")
        section_title.setObjectName("WorkflowTitle")
        content_layout.addWidget(section_title)

        workflow_list = QFrame()
        workflow_list.setObjectName("WorkflowList")
        list_layout = QVBoxLayout(workflow_list)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        for index, spec in enumerate(self._tools):
            step = WorkflowStep(index + 1, spec)
            if spec.enabled:
                step.clicked.connect(self.tool_requested.emit)
            list_layout.addWidget(step)
            if index < len(self._tools) - 1:
                separator = QFrame()
                separator.setObjectName("WorkflowSeparator")
                separator.setFrameShape(QFrame.HLine)
                list_layout.addWidget(separator)

        content_layout.addWidget(workflow_list)
        root.addWidget(content, 0, Qt.AlignHCenter)
        root.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
            QWidget#MainMenuWidget {
                background: {theme.BACKGROUND};
                color: {theme.TEXT};
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QFrame#WorkflowSeparator {
                border: 0;
                background: {theme.BORDER};
                min-height: 1px;
                max-height: 1px;
            }
            QLabel#WorkflowTitle {
                color: {theme.TEXT};
                font-size: 20px;
                font-weight: 650;
            }
            QFrame#WorkflowList {
                background: {theme.SURFACE};
                border: 0;
                border-top: 1px solid {theme.BORDER};
                border-bottom: 1px solid {theme.BORDER};
                border-radius: 0;
            }
            QFrame#WorkflowStep {
                background: transparent;
                border: 0;
            }
            QFrame#WorkflowStep[enabledStep="true"]:hover {
                background: {theme.PANEL};
            }
            QFrame#WorkflowStep[enabledStep="false"] {
                background: {theme.BACKGROUND};
            }
            QLabel#StepIndex {
                color: {theme.CONNECTOR};
                font-size: 13px;
                font-weight: 600;
                min-width: 28px;
            }
            QLabel#StepIndex[enabledStep="false"] {
                color: {theme.BORDER};
            }
            QLabel#StepTitle {
                color: {theme.TEXT};
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#StepTitle[enabledStep="false"] {
                color: {theme.CONNECTOR};
            }
            QLabel#StepDescription {
                color: {theme.CONNECTOR};
                font-size: 12px;
            }
            QLabel#StepDescription[enabledStep="false"] {
                color: {theme.BORDER};
            }
            QPushButton#OpenToolButton {
                background: {theme.SURFACE};
                border: 1px solid {theme.BORDER};
                border-radius: 3px;
                color: {theme.TEXT};
                min-width: 60px;
                padding: 6px 12px;
            }
            QPushButton#OpenToolButton:hover {
                background: {theme.PRIMARY};
                border-color: {theme.PRIMARY};
                color: {theme.PRIMARY_TEXT};
            }
            QPushButton#OpenToolButton:disabled {
                background: {theme.BACKGROUND};
                color: {theme.CONNECTOR};
            }
            """
            )
        )


def _main_menu_logo_label(filename: str) -> QLabel:
    label = QLabel()
    label.setObjectName("MainMenuLogo")
    label.setAlignment(Qt.AlignCenter)
    path = Path(__file__).resolve().parents[3] / "assets" / "images" / filename
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        scale = max(1.0, QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() is not None else 1.0)
        scaled = pixmap.scaled(
            round(MAIN_MENU_LOGO_MAX_WIDTH * scale),
            round(MAIN_MENU_LOGO_HEIGHT * scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(scale)
        label.setPixmap(scaled)
        label.setFixedSize(round(scaled.width() / scale), round(scaled.height() / scale))
    return label


class WorkflowStep(QFrame):
    clicked = Signal(str)

    def __init__(self, index: int, spec: ToolSpec):
        super().__init__()
        self._spec = spec
        self.setObjectName("WorkflowStep")
        self.setProperty("enabledStep", spec.enabled)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(WORKFLOW_ROW_HEIGHT)
        if spec.enabled:
            self.setCursor(Qt.PointingHandCursor)
            if spec.description:
                self.setToolTip(spec.description)
        else:
            self.setToolTip("Not available yet.")
        self._build_ui(index, spec)

    def _build_ui(self, index: int, spec: ToolSpec) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 12, 16, 12)
        root.setSpacing(14)

        number = QLabel(str(index))
        number.setObjectName("StepIndex")
        number.setProperty("enabledStep", spec.enabled)
        number.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        number.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(number)

        text_block = QWidget()
        text_block.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_layout = QVBoxLayout(text_block)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title = QLabel(spec.label)
        title.setObjectName("StepTitle")
        title.setProperty("enabledStep", spec.enabled)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(title)

        description = QLabel(spec.description)
        description.setObjectName("StepDescription")
        description.setProperty("enabledStep", spec.enabled)
        description.setWordWrap(True)
        description.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(description)
        root.addWidget(text_block, 1)

        open_button = QPushButton("Open" if spec.enabled else "Unavailable")
        open_button.setObjectName("OpenToolButton")
        open_button.setEnabled(spec.enabled)
        if spec.enabled:
            open_button.clicked.connect(lambda: self.clicked.emit(spec.id))
        root.addWidget(open_button, 0, Qt.AlignVCenter)

    def mouseReleaseEvent(self, event) -> None:
        if self._spec.enabled and event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._spec.id)
            event.accept()
            return

        super().mouseReleaseEvent(event)
