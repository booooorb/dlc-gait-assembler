from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.deeplabcut.window import DeepLabCutWidget
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget
from dlc_gait_assembly.gui.shared.widgets import CurrentPageStackedWidget


WORKFLOW_ROW_HEIGHT = 78
APP_TOOLBAR_HEIGHT = 60
MAIN_MENU_LOGO_HEIGHT = 24
MAIN_MENU_LOGO_MAX_WIDTH = 104

HEADER_STAGE_LABELS = {
    "manual_calibration": "Calibration",
    "video_processing": "Video",
    "deeplabcut": "DeepLabCut",
    "gait_parameter_analysis": "Gait",
    "pca_random_forest": "PCA/RF",
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
    theme_mode_requested = Signal(str)

    def __init__(self, initial_tool_id: str | None = None, initial_theme_mode: str = "light"):
        super().__init__()
        self.setWindowTitle("DLC Gait Assembler")
        self.setMinimumSize(1100, 640)
        self.resize(1360, 860)
        self._active_tool: QWidget | None = None
        self._active_tool_id: str | None = None
        self._automation_menu_active = False
        self._automated_workspace_page = "run"
        self._tool_widgets: dict[str, QWidget] = {}
        self._stack = CurrentPageStackedWidget()
        self._main_menu = MainMenuWidget(TOOL_SPECS)
        self._main_menu.tool_requested.connect(self._open_tool)
        self._main_menu.pipeline_tabs.currentChanged.connect(self._pipeline_tab_changed)
        self._main_menu.automated_profiles.workspace_changed.connect(
            self._automated_workspace_changed
        )
        self._stack.addWidget(self._main_menu)
        self._build_shell(initial_theme_mode)
        if initial_tool_id is None:
            self._show_automated_pipeline()
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
        for logo in self.findChildren(PartnerLogoLabel):
            logo.apply_theme()
        self._main_menu._apply_style()
        for tool in self._tool_widgets.values():
            apply_style = getattr(tool, "_apply_style", None)
            if apply_style is not None:
                apply_style()
        self._refresh_stage_navigation()
        self.update()

    def set_theme_mode(self, mode: str) -> None:
        action = self._theme_actions.get(mode)
        if action is not None:
            action.setChecked(True)

    def _build_shell(self, initial_theme_mode: str) -> None:
        shell = QWidget()
        shell.setObjectName("AppShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("AppToolbar")
        toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)

        primary_row = QFrame()
        primary_row.setObjectName("PrimaryToolbarRow")
        primary_layout = QHBoxLayout(primary_row)
        primary_layout.setContentsMargins(16, 0, 16, 0)
        primary_layout.setSpacing(0)

        home_button = QPushButton("DLC Gait Assembler")
        home_button.setObjectName("HomeNavigationButton")
        home_button.setCursor(Qt.PointingHandCursor)
        home_button.setToolTip("Open the automated pipeline")
        home_button.clicked.connect(self._show_automated_pipeline)
        primary_layout.addWidget(home_button)

        divider = QFrame()
        divider.setObjectName("ToolbarDivider")
        divider.setFrameShape(QFrame.VLine)
        primary_layout.addWidget(divider)

        automated_label = QLabel("AUTOMATED PIPELINE")
        automated_label.setObjectName("AutomationGroupLabel")
        primary_layout.addWidget(automated_label)
        self._automation_run_button = QPushButton("Run")
        self._automation_run_button.setObjectName("TopAutomationButton")
        self._automation_run_button.setProperty("activeNavigation", True)
        self._automation_run_button.clicked.connect(self._show_automated_pipeline)
        primary_layout.addWidget(self._automation_run_button)
        self._automation_profiles_button = QPushButton("Profiles")
        self._automation_profiles_button.setObjectName("TopAutomationButton")
        self._automation_profiles_button.setProperty("activeNavigation", False)
        self._automation_profiles_button.clicked.connect(self._show_automated_profiles)
        primary_layout.addWidget(self._automation_profiles_button)

        pipeline_divider = QFrame()
        pipeline_divider.setObjectName("PipelineGroupDivider")
        pipeline_divider.setFrameShape(QFrame.VLine)
        primary_layout.addWidget(pipeline_divider)

        manual_tools_button = QToolButton()
        manual_tools_button.setObjectName("ManualPipelineButton")
        manual_tools_button.setText("MANUAL PIPELINE  ›")
        manual_tools_button.setToolTip("Expand backup tools and editors used to create automation inputs.")
        manual_tools_button.setCheckable(True)
        manual_tools_button.toggled.connect(self._set_manual_pipeline_expanded)
        self._manual_tools_button = manual_tools_button
        primary_layout.addWidget(manual_tools_button)

        manual_stage_frame = QFrame()
        manual_stage_frame.setObjectName("ManualStageExpansion")
        manual_stage_layout = QHBoxLayout(manual_stage_frame)
        manual_stage_layout.setContentsMargins(4, 0, 0, 0)
        manual_stage_layout.setSpacing(2)
        self._manual_stage_buttons: dict[str, QPushButton] = {}
        overview_button = QPushButton("Overview")
        overview_button.setObjectName("ManualStageButton")
        overview_button.setProperty("manualStage", "manual_overview")
        overview_button.setProperty("activeStage", False)
        overview_button.clicked.connect(self._show_main_menu)
        self._manual_stage_buttons["manual_overview"] = overview_button
        manual_stage_layout.addWidget(overview_button)
        self._stage_navigation_buttons = {}
        for spec in TOOL_SPECS:
            button = QPushButton(HEADER_STAGE_LABELS[spec.id])
            button.setObjectName("ManualStageButton")
            button.setProperty("manualStage", spec.id)
            button.setProperty("activeStage", False)
            button.setEnabled(spec.enabled)
            button.setToolTip(spec.label)
            if spec.enabled:
                button.clicked.connect(
                    lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id)
                )
            self._manual_stage_buttons[spec.id] = button
            self._stage_navigation_buttons[spec.id] = button
            manual_stage_layout.addWidget(button)
        manual_stage_frame.setVisible(False)
        self._manual_stage_frame = manual_stage_frame
        primary_layout.addWidget(manual_stage_frame)

        primary_layout.addStretch(1)

        settings_button = QToolButton()
        settings_button.setObjectName("SettingsButton")
        settings_button.setText("Settings")
        settings_button.setAccessibleName("Application settings")
        settings_button.setCursor(Qt.PointingHandCursor)
        settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_menu = QMenu(settings_button)
        self._build_theme_actions(settings_menu, initial_theme_mode)
        settings_button.setMenu(settings_menu)
        self._settings_button = settings_button
        self._settings_menu = settings_menu
        primary_layout.addWidget(settings_button)

        partner_marks = QFrame()
        partner_marks.setObjectName("PartnerMarks")
        partner_layout = QHBoxLayout(partner_marks)
        partner_layout.setContentsMargins(8, 4, 8, 4)
        partner_layout.setSpacing(12)
        partner_layout.addWidget(_main_menu_logo_label("choforcelab.png"))
        partner_layout.addWidget(_main_menu_logo_label("NERVES_Logo.png"))
        primary_layout.addWidget(partner_marks)
        self._partner_marks = partner_marks
        toolbar_layout.addWidget(primary_row, 0)

        shell_layout.addWidget(toolbar)
        shell_layout.addWidget(self._stack, 1)
        self.setCentralWidget(shell)
        self._shell = shell
        self._toolbar = toolbar
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
                QFrame#PrimaryToolbarRow {
                    background: {theme.SURFACE};
                    border: 0;
                }
                QFrame#ContextToolbarRow {
                    background: {theme.PANEL};
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
                    margin-right: 10px;
                }
                QFrame#PipelineGroupDivider {
                    background: {theme.BORDER};
                    border: 0;
                    min-width: 1px;
                    max-width: 1px;
                    min-height: 24px;
                    max-height: 24px;
                    margin: 0 12px;
                }
                QLabel#AutomationGroupLabel {
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 750;
                    padding-right: 5px;
                }
                QPushButton#TopAutomationButton {
                    background: transparent;
                    border: 0;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    color: {theme.CONNECTOR};
                    min-height: 42px;
                    padding: 0 12px;
                }
                QPushButton#TopAutomationButton:hover {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QPushButton#TopAutomationButton[activeNavigation="true"] {
                    background: transparent;
                    border-bottom-color: {theme.TOOL_1};
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QToolButton#ManualPipelineButton {
                    background: transparent;
                    border: 0;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 750;
                    min-height: 42px;
                    padding: 0 10px;
                }
                QToolButton#ManualPipelineButton:hover {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QToolButton#ManualPipelineButton:checked {
                    background: transparent;
                    border-bottom-color: {theme.TOOL_1};
                    color: {theme.TEXT};
                }
                QToolButton#ManualPipelineButton[activeManual="true"] {
                    background: transparent;
                    border-bottom-color: {theme.TOOL_1};
                    color: {theme.TEXT};
                }
                QFrame#ManualStageExpansion {
                    background: transparent;
                    border: 0;
                    margin-left: 4px;
                }
                QPushButton#ManualStageButton {
                    background: transparent;
                    border: 0;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                    min-height: 42px;
                    padding: 0 10px;
                }
                QPushButton#ManualStageButton:hover {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QPushButton#ManualStageButton[activeStage="true"] {
                    background: transparent;
                    border-bottom-color: {theme.TOOL_1};
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QToolButton#SettingsButton {
                    background: transparent;
                    border: 1px solid {theme.BORDER};
                    border-radius: 3px;
                    color: {theme.TEXT};
                    min-height: 26px;
                    padding: 2px 8px;
                }
                QToolButton#SettingsButton:hover,
                QToolButton#SettingsButton:open {
                    background: {theme.PANEL};
                    border-color: {theme.TEXT};
                }
                QFrame#PartnerMarks {
                    background: transparent;
                    border: 0;
                    margin-left: 10px;
                }
                QLabel#MainMenuLogo {
                    background: transparent;
                }
                """
            )
        )

    def _build_theme_actions(self, settings_menu: QMenu, initial_theme_mode: str) -> None:
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self._theme_actions = {}
        for label, mode in (("Light mode", "light"), ("Dark mode", "dark")):
            action = settings_menu.addAction(label)
            action.setCheckable(True)
            action.setData(mode)
            action.setChecked(mode == initial_theme_mode)
            action.triggered.connect(
                lambda checked=False, selected_mode=mode: self._request_theme_mode(
                    selected_mode, checked
                )
            )
            theme_group.addAction(action)
            self._theme_actions[mode] = action
        self._theme_action_group = theme_group

    def _request_theme_mode(self, mode: str, checked: bool) -> None:
        if checked:
            self.theme_mode_requested.emit(mode)

    def _set_manual_pipeline_expanded(self, expanded: bool) -> None:
        if expanded and self.width() < 1360:
            self.resize(1360, self.height())
        self._manual_stage_frame.setVisible(expanded)
        self._manual_tools_button.setText(
            "MANUAL PIPELINE  ‹" if expanded else "MANUAL PIPELINE  ›"
        )

    def _show_main_menu(self) -> None:
        if not self._can_leave_active_tool():
            return

        self._active_tool = None
        self._active_tool_id = None
        self._automation_menu_active = False
        self._manual_tools_button.setChecked(True)
        self._main_menu.pipeline_tabs.setCurrentIndex(0)
        self.setWindowTitle("DLC Gait Assembler")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_automated_pipeline(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._active_tool = None
        self._active_tool_id = None
        self._automation_menu_active = True
        self._automated_workspace_page = "run"
        self._manual_tools_button.setChecked(False)
        self._main_menu.pipeline_tabs.setCurrentIndex(1)
        self._main_menu.automated_profiles._show_automation_menu()
        self.setWindowTitle("DLC Gait Assembler - Automated pipeline")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_automated_profiles(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._active_tool = None
        self._active_tool_id = None
        self._automation_menu_active = True
        self._automated_workspace_page = "profiles"
        self._manual_tools_button.setChecked(False)
        self._main_menu.pipeline_tabs.setCurrentIndex(1)
        self._main_menu.automated_profiles._show_profile_configuration()
        self.setWindowTitle("DLC Gait Assembler - Manage automated profiles")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _automated_workspace_changed(self, page: str) -> None:
        self._automated_workspace_page = page
        if not self._automation_menu_active:
            return
        self.setWindowTitle(
            "DLC Gait Assembler - Manage automated profiles"
            if page == "profiles"
            else "DLC Gait Assembler - Automated pipeline"
        )
        self._refresh_stage_navigation()

    def _pipeline_tab_changed(self, index: int) -> None:
        if self._stack.currentWidget() is not self._main_menu:
            return
        self._automation_menu_active = index == 1
        if not self._automation_menu_active:
            self._active_tool_id = None
        self.setWindowTitle(
            "DLC Gait Assembler - Automated pipeline"
            if self._automation_menu_active
            else "DLC Gait Assembler"
        )
        self._refresh_stage_navigation()

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
        self._automation_menu_active = False
        self._manual_tools_button.setChecked(True)
        self.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self._refresh_stage_navigation()
        self._show_widget(tool)

    def _refresh_stage_navigation(self) -> None:
        self._automation_run_button.setProperty(
            "activeNavigation",
            self._automation_menu_active and self._automated_workspace_page == "run",
        )
        self._automation_profiles_button.setProperty(
            "activeNavigation",
            self._automation_menu_active and self._automated_workspace_page == "profiles",
        )
        manual_active = not self._automation_menu_active
        self._manual_tools_button.setProperty("activeManual", manual_active)
        active_manual_stage = self._active_tool_id or ("manual_overview" if manual_active else None)
        for stage_id, stage_button in self._manual_stage_buttons.items():
            stage_button.setProperty("activeStage", stage_id == active_manual_stage)
            stage_button.style().unpolish(stage_button)
            stage_button.style().polish(stage_button)
            stage_button.update()
        for button in (
            self._automation_run_button,
            self._automation_profiles_button,
            self._manual_tools_button,
        ):
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
        self._automation_menu_active = False


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
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(0)

        content = QWidget()
        content.setObjectName("MenuContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        section_title = QLabel("Manual pipeline workflow")
        section_title.setObjectName("WorkflowTitle")
        content_layout.addWidget(section_title)
        self.section_title = section_title

        pipeline_tabs = QTabWidget()
        pipeline_tabs.setObjectName("PipelineTabs")
        pipeline_tabs.setDocumentMode(True)
        pipeline_tabs.tabBar().setExpanding(True)
        pipeline_tabs.tabBar().hide()
        pipeline_tabs.setAccessibleName("Pipeline type")

        manual_page = QWidget()
        manual_page.setObjectName("ManualPipelinePage")
        manual_layout = QVBoxLayout(manual_page)
        manual_layout.setContentsMargins(0, 8, 0, 0)
        manual_layout.addWidget(self._workflow_list(self._tools, connect_tools=True))
        pipeline_tabs.addTab(manual_page, "Manual pipeline")

        automated_page = QWidget()
        automated_page.setObjectName("AutomatedPipelinePage")
        automated_layout = QVBoxLayout(automated_page)
        automated_layout.setContentsMargins(0, 8, 0, 0)
        self.automated_profiles = AutomatedPipelineProfilesWidget()
        automated_layout.addWidget(self.automated_profiles)
        pipeline_tabs.addTab(automated_page, "Automated pipeline")

        self.pipeline_tabs = pipeline_tabs
        pipeline_tabs.currentChanged.connect(self._update_pipeline_heading)
        content_layout.addWidget(pipeline_tabs)

        root.addWidget(content, 1)

    def _update_pipeline_heading(self, index: int) -> None:
        self.section_title.setVisible(index == 0)
        if index == 0:
            self.section_title.setText("Manual pipeline workflow")

    def _workflow_list(self, tools: list[ToolSpec], connect_tools: bool) -> QFrame:
        workflow_list = QFrame()
        workflow_list.setObjectName("WorkflowList")
        list_layout = QVBoxLayout(workflow_list)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        for index, spec in enumerate(tools):
            step = WorkflowStep(index + 1, spec)
            if connect_tools and spec.enabled:
                step.clicked.connect(self.tool_requested.emit)
            list_layout.addWidget(step)
            if index < len(tools) - 1:
                separator = QFrame()
                separator.setObjectName("WorkflowSeparator")
                separator.setFrameShape(QFrame.HLine)
                list_layout.addWidget(separator)
        return workflow_list

    def _apply_style(self) -> None:
        if hasattr(self, "automated_profiles"):
            self.automated_profiles._apply_style()
        pipeline_tab_style = """
            QTabWidget#PipelineTabs {
                background: {theme.PANEL};
            }
            QTabWidget#PipelineTabs::pane {
                background: {theme.BACKGROUND};
                border: 0;
                border-top: 1px solid {theme.BORDER};
            }
            QTabWidget#PipelineTabs QTabBar::tab {
                background: {theme.PANEL};
            }
            QTabWidget#PipelineTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
            }
        """
        self.setStyleSheet(
            theme.stylesheet(
                pipeline_tab_style
                + """
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
                font-size: 16px;
                font-weight: 600;
            }
            QWidget#ManualPipelinePage, QWidget#AutomatedPipelinePage {
                background: transparent;
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


class PartnerLogoLabel(QLabel):
    def __init__(self, filename: str):
        super().__init__()
        self.setObjectName("MainMenuLogo")
        self.setAccessibleName("Cho Force Lab logo" if filename == "choforcelab.png" else "NERVES Lab logo")
        self.setAlignment(Qt.AlignCenter)
        self._plain_pixmap = QPixmap()
        self._outlined_pixmap = QPixmap()
        self._load_pixmaps(filename)
        self.apply_theme()

    def _load_pixmaps(self, filename: str) -> None:
        path = Path(__file__).resolve().parents[3] / "assets" / "images" / filename
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return

        screen = QGuiApplication.primaryScreen()
        scale = max(1.0, screen.devicePixelRatio() if screen is not None else 1.0)
        scaled = pixmap.scaled(
            round(MAIN_MENU_LOGO_MAX_WIDTH * scale),
            round(MAIN_MENU_LOGO_HEIGHT * scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        outline_width = max(1, round(2 * scale))
        self._plain_pixmap = QPixmap(scaled)
        self._outlined_pixmap = _pixmap_with_outline(scaled, QColor("#FFFFFF"), outline_width)
        self._plain_pixmap.setDevicePixelRatio(scale)
        self._outlined_pixmap.setDevicePixelRatio(scale)

    def apply_theme(self) -> None:
        pixmap = self._outlined_pixmap if theme.IS_DARK else self._plain_pixmap
        if pixmap.isNull():
            return
        self.setPixmap(pixmap)
        scale = pixmap.devicePixelRatio()
        self.setFixedSize(round(pixmap.width() / scale), round(pixmap.height() / scale))


def _pixmap_with_outline(source: QPixmap, color: QColor, width: int) -> QPixmap:
    width = max(1, width)
    silhouette = QPixmap(source.size())
    silhouette.fill(Qt.transparent)
    silhouette_painter = QPainter(silhouette)
    silhouette_painter.drawPixmap(0, 0, source)
    silhouette_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    silhouette_painter.fillRect(silhouette.rect(), color)
    silhouette_painter.end()

    outlined = QPixmap(source.width() + width * 2, source.height() + width * 2)
    outlined.fill(Qt.transparent)
    painter = QPainter(outlined)
    for y_offset in range(-width, width + 1):
        for x_offset in range(-width, width + 1):
            if x_offset * x_offset + y_offset * y_offset <= width * width:
                painter.drawPixmap(width + x_offset, width + y_offset, silhouette)
    painter.drawPixmap(width, width, source)
    painter.end()
    return outlined


def _main_menu_logo_label(filename: str) -> QLabel:
    return PartnerLogoLabel(filename)


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
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(16)

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
