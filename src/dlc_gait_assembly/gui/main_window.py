from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QPointF,
    QRectF,
    QSize,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QActionGroup,
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.gui.deeplabcut.window import DeepLabCutWidget
from dlc_gait_assembly.gui.gait_analysis.settings import SINGLE_SIDE_VIEW_MODE_LABEL
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget
from dlc_gait_assembly.gui.knee_correction import KneeCorrectionWidget
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.widgets import CurrentPageStackedWidget
from dlc_gait_assembly.gui.tutorial import (
    TUTORIAL_STEPS,
    TutorialAssets,
    TutorialBar,
    TutorialGuideStep,
    TutorialSpotlightOverlay,
)
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget
from dlc_gait_assembly.services.analysis_manifests import (
    knee_settings_from_manifest,
    video_settings_from_manifest,
)

WORKFLOW_ROW_HEIGHT = 64
APP_TOOLBAR_HEIGHT = 64
MANUAL_TOOLBAR_HEIGHT = 52
TUTORIAL_TOOLBAR_HEIGHT = 76
MAIN_MENU_LOGO_HEIGHT = 24
MAIN_MENU_LOGO_MAX_WIDTH = 104
BRAND_LOGO_HEIGHT = 34
BRAND_LOGO_MAX_WIDTH = 160
BRAND_LOGO_FILENAMES = {
    "light": "DLC-Gait-Assembler-logo-light-original-clean.png",
    "dark": "DLC-Gait-Assembler-logo-dark-original-clean.png",
}
PARTNER_WEBSITES = {
    "choforcelab.png": "https://www.choforcelab.ca",
    "NERVES_Logo.png": "https://nerves.bme.utah.edu",
}
MINIMUM_WINDOW_SIZE = QSize(1100, 640)
DEFAULT_WINDOW_SIZE = QSize(1440, 900)
WINDOW_SCREEN_MARGIN = 64
HEADER_STAGE_LABELS = {
    "manual_calibration": "Calibration",
    "video_processing": "Video processing",
    "deeplabcut": "DeepLabCut",
    "knee_correction": "Knee correction",
    "gait_parameter_analysis": "Gait analysis",
    "pca_random_forest": "PCA + random forest",
}


def _navigation_icon(icon_name: str, color: str) -> QIcon:
    """Draw a crisp, theme-aware icon for a primary navigation destination."""
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    accent = QColor(color)
    painter.setPen(QPen(accent, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    if icon_name == "run":
        painter.drawEllipse(QRectF(1.8, 1.8, 14.4, 14.4))
        path = QPainterPath()
        path.moveTo(7.1, 5.2)
        path.lineTo(13.0, 9.0)
        path.lineTo(7.1, 12.8)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawPath(path)
    elif icon_name == "profiles":
        painter.setBrush(Qt.NoBrush)
        for top, inset in ((2.4, 0.0), (6.4, 0.8), (10.4, 1.6)):
            painter.drawRoundedRect(
                QRectF(2.4 + inset, top, 13.2 - inset * 2, 4.2), 1.2, 1.2
            )
    elif icon_name == "manual":
        painter.setBrush(Qt.NoBrush)
        for y, knob_x in ((4.0, 6.0), (9.0, 12.0), (14.0, 8.5)):
            painter.drawLine(QPointF(2.5, y), QPointF(15.5, y))
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(knob_x, y), 2.0, 2.0)
            painter.setBrush(Qt.NoBrush)

    painter.end()
    return QIcon(pixmap)


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
        "knee_correction",
        "Knee Correction",
        KneeCorrectionWidget,
        True,
        description="Correct knee coordinates in paired DeepLabCut CSV and H5 labels.",
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
        self.setMinimumSize(MINIMUM_WINDOW_SIZE)
        self.resize(self._screen_aware_initial_size())
        self._active_tool: QWidget | None = None
        self._active_tool_id: str | None = None
        self._home_menu_active = True
        self._automation_menu_active = False
        self._tutorial_active = False
        self._tutorial_transitioning = False
        self._tutorial_step_index = -1
        self._tutorial_guide_steps: tuple[TutorialGuideStep, ...] = ()
        self._tutorial_guide_index = -1
        self._tutorial_profile_draft_loaded = False
        self._tutorial_assets = TutorialAssets.from_project_root(
            Path(__file__).resolve().parents[3]
        )
        self._automated_workspace_page = "run"
        self._tool_widgets: dict[str, QWidget] = {}
        self._stack = CurrentPageStackedWidget()
        self._main_menu = MainMenuWidget(TOOL_SPECS)
        self._main_menu.tool_requested.connect(self._open_tool)
        self._main_menu.automated_requested.connect(self._show_automated_pipeline)
        self._main_menu.manual_requested.connect(self._show_main_menu)
        self._main_menu.tutorial_requested.connect(self._start_tutorial)
        self._main_menu.pipeline_tabs.currentChanged.connect(self._pipeline_tab_changed)
        self._main_menu.automated_profiles.workspace_changed.connect(
            self._automated_workspace_changed
        )
        self._main_menu.automated_profiles.manual_tool_requested.connect(self._open_tool)
        self._stack.addWidget(self._main_menu)
        self._build_shell(initial_theme_mode)
        if initial_tool_id is None:
            self._show_home_menu()
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
        self._tutorial_bar.apply_theme()
        self._tutorial_spotlight.apply_theme()
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
        primary_layout.setContentsMargins(20, 0, 16, 0)
        primary_layout.setSpacing(10)

        home_button = QPushButton()
        home_button.setObjectName("HomeNavigationButton")
        home_button.setAccessibleName("DLC Gait Assembler home")
        home_button.setCursor(Qt.PointingHandCursor)
        home_button.setFixedSize(BRAND_LOGO_MAX_WIDTH + 8, 44)
        home_button.setToolTip("Open the main menu")
        home_button.clicked.connect(self._show_home_menu)
        self._home_button = home_button
        primary_layout.addWidget(home_button)

        divider = QFrame()
        divider.setObjectName("ToolbarDivider")
        divider.setFrameShape(QFrame.VLine)
        primary_layout.addWidget(divider)

        primary_navigation = QFrame()
        primary_navigation.setObjectName("PrimaryNavigation")
        primary_navigation.setAccessibleName("Primary navigation")
        navigation_layout = QHBoxLayout(primary_navigation)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(4)

        self._automation_run_button = QPushButton("Automated")
        self._automation_run_button.setObjectName("TopAutomationButton")
        self._automation_run_button.setProperty("activeNavigation", False)
        self._automation_run_button.setProperty("navigationRole", "automated")
        self._automation_run_button.setCursor(Qt.PointingHandCursor)
        self._automation_run_button.setToolTip(
            "Open the automation run screen to select a saved profile, queue source "
            "videos, and monitor pipeline progress."
        )
        self._automation_run_button.clicked.connect(self._show_automated_pipeline)
        navigation_layout.addWidget(self._automation_run_button)
        self._automation_profiles_button = QPushButton("Profiles")
        self._automation_profiles_button.setObjectName("TopAutomationButton")
        self._automation_profiles_button.setProperty("activeNavigation", False)
        self._automation_profiles_button.setProperty("navigationRole", "profiles")
        self._automation_profiles_button.setCursor(Qt.PointingHandCursor)
        self._automation_profiles_button.setToolTip(
            "Create and manage reusable automation profiles containing processing, "
            "DeepLabCut, calibration, and gait-analysis inputs."
        )
        self._automation_profiles_button.clicked.connect(self._show_automated_profiles)
        navigation_layout.addWidget(self._automation_profiles_button)
        primary_layout.addWidget(primary_navigation)
        self._primary_navigation = primary_navigation

        manual_divider = QFrame()
        manual_divider.setObjectName("ManualNavigationDivider")
        manual_divider.setFrameShape(QFrame.VLine)
        primary_layout.addWidget(manual_divider)

        manual_tools_button = QToolButton()
        manual_tools_button.setObjectName("ManualPipelineButton")
        manual_tools_button.setText("Manual")
        manual_tools_button.setProperty("navigationRole", "manual")
        manual_tools_button.setToolTip("Open the manual pipeline and its stages.")
        manual_tools_button.setCursor(Qt.PointingHandCursor)
        manual_tools_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        manual_tools_button.clicked.connect(lambda _checked=False: self._show_main_menu())
        self._manual_tools_button = manual_tools_button
        primary_layout.addWidget(manual_tools_button)

        manual_stage_frame = QFrame()
        manual_stage_frame.setObjectName("ManualStageExpansion")
        manual_stage_frame.setFixedHeight(MANUAL_TOOLBAR_HEIGHT)
        manual_stage_layout = QHBoxLayout(manual_stage_frame)
        manual_stage_layout.setContentsMargins(20, 6, 20, 6)
        manual_stage_layout.setSpacing(6)
        manual_stage_title = QLabel("Manual pipeline")
        manual_stage_title.setObjectName("ManualStageTitle")
        manual_stage_layout.addWidget(manual_stage_title)
        self._manual_stage_buttons: dict[str, QPushButton] = {}
        for spec in TOOL_SPECS:
            button = QPushButton(HEADER_STAGE_LABELS[spec.id])
            button.setObjectName("ManualStageButton")
            button.setProperty("manualStage", spec.id)
            button.setProperty("activeStage", False)
            button.setEnabled(spec.enabled)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(spec.label)
            if spec.enabled:
                button.clicked.connect(
                    lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id)
                )
            self._manual_stage_buttons[spec.id] = button
            manual_stage_layout.addWidget(button, 1)
        manual_stage_frame.hide()
        self._manual_stage_frame = manual_stage_frame
        self._manual_stage_expanded = False

        tutorial_bar = TutorialBar()
        tutorial_bar.previous_requested.connect(self._previous_tutorial_step)
        tutorial_bar.next_requested.connect(self._next_tutorial_step)
        tutorial_bar.exit_requested.connect(self._finish_tutorial)
        tutorial_bar.hide()
        self._tutorial_bar = tutorial_bar

        primary_layout.addStretch(1)

        settings_button = QToolButton()
        settings_button.setObjectName("SettingsButton")
        settings_button.setText("Settings")
        settings_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
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
        toolbar_layout.addWidget(manual_stage_frame, 0)
        toolbar_layout.addWidget(tutorial_bar, 0)

        shell_layout.addWidget(toolbar)
        shell_layout.addWidget(self._stack, 1)
        tutorial_spotlight = TutorialSpotlightOverlay(self._stack)
        tutorial_spotlight.apply_requested.connect(self._apply_tutorial_guide_value)
        self._tutorial_spotlight = tutorial_spotlight
        self.setCentralWidget(shell)
        self._shell = shell
        self._toolbar = toolbar
        self._apply_shell_style()

    def _apply_shell_style(self) -> None:
        stylesheet = theme.stylesheet(
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
                    border-radius: 6px;
                    padding: 0 4px;
                }
                QPushButton#HomeNavigationButton:hover {
                    background: {theme.PANEL};
                }
                QPushButton#HomeNavigationButton[activeNavigation="true"] {
                    background: NAV_HOME_FILL;
                }
                QFrame#ToolbarDivider {
                    background: {theme.BORDER};
                    border: 0;
                    min-width: 1px;
                    max-width: 1px;
                    min-height: 22px;
                    max-height: 22px;
                    margin: 0 2px;
                }
                QFrame#ManualNavigationDivider {
                    background: {theme.BORDER};
                    border: 0;
                    min-width: 1px;
                    max-width: 1px;
                    min-height: 24px;
                    max-height: 24px;
                    margin: 0 1px;
                }
                QFrame#PrimaryNavigation {
                    background: transparent;
                    border: 0;
                }
                QPushButton#TopAutomationButton,
                QToolButton#ManualPipelineButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-bottom-width: 3px;
                    border-radius: 6px;
                    color: {theme.CONNECTOR};
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 36px;
                    max-height: 36px;
                    padding: 0 12px;
                }
                QPushButton#TopAutomationButton:hover,
                QToolButton#ManualPipelineButton:hover {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QPushButton#TopAutomationButton[navigationRole="automated"][activeNavigation="true"] {
                    background: NAV_RUN_FILL;
                    border-bottom-color: {theme.TOOL_1};
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QPushButton#TopAutomationButton[navigationRole="profiles"][activeNavigation="true"] {
                    background: NAV_PROFILES_FILL;
                    border-bottom-color: {theme.TOOL_2};
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QToolButton#ManualPipelineButton[activeManual="true"] {
                    background: NAV_MANUAL_FILL;
                    border-bottom-color: {theme.TOOL_3};
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QFrame#ManualStageExpansion {
                    background: {theme.PANEL};
                    border: 0;
                    border-top: 1px solid {theme.BORDER};
                    border-bottom: 1px solid {theme.BORDER};
                }
                QLabel#ManualStageTitle {
                    color: {theme.TEXT};
                    font-size: 12px;
                    font-weight: 700;
                    padding-right: 8px;
                }
                QPushButton#ManualStageButton {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-bottom: 2px solid {theme.BORDER};
                    border-radius: 4px;
                    color: {theme.TEXT};
                    font-size: 12px;
                    min-height: 36px;
                    max-height: 36px;
                    padding: 0 10px;
                }
                QPushButton#ManualStageButton:hover {
                    background: {theme.SOFT};
                    border-color: {theme.TOOL_3};
                    color: {theme.TEXT};
                }
                QPushButton#ManualStageButton[activeStage="true"] {
                    background: NAV_MANUAL_FILL;
                    border-bottom-color: {theme.TOOL_3};
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QToolButton#SettingsButton {
                    background: transparent;
                    border: 1px solid {theme.BORDER};
                    border-radius: 6px;
                    color: {theme.TEXT};
                    font-size: 12px;
                    min-height: 32px;
                    padding: 1px 11px;
                }
                QToolButton#SettingsButton:hover,
                QToolButton#SettingsButton:open {
                    background: {theme.SURFACE};
                    border-color: {theme.CONNECTOR};
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
        stylesheet = (
            stylesheet.replace(
                "NAV_HOME_FILL", theme.mix_hex(theme.TOOL_1, theme.SURFACE, 0.9)
            )
            .replace(
                "NAV_RUN_FILL", theme.mix_hex(theme.TOOL_1, theme.SURFACE, 0.84)
            )
            .replace(
                "NAV_PROFILES_FILL", theme.mix_hex(theme.TOOL_2, theme.SURFACE, 0.86)
            )
            .replace(
                "NAV_MANUAL_FILL", theme.mix_hex(theme.TOOL_3, theme.SURFACE, 0.86)
            )
        )
        self._shell.setStyleSheet(stylesheet)
        self._apply_navigation_icons()

    def _apply_navigation_icons(self) -> None:
        self._apply_brand_logo()
        navigation_icons = (
            (self._automation_run_button, "run", theme.TOOL_1),
            (self._automation_profiles_button, "profiles", theme.TOOL_2),
            (self._manual_tools_button, "manual", theme.TOOL_3),
        )
        for button, icon_name, color in navigation_icons:
            button.setIcon(_navigation_icon(icon_name, color))
            button.setIconSize(QSize(18, 18))
        self._settings_button.setIcon(interface_icon("gear", theme.TEXT))
        self._settings_button.setIconSize(QSize(16, 16))

    def _apply_brand_logo(self) -> None:
        logo_theme = "dark" if theme.IS_DARK else "light"
        filename = BRAND_LOGO_FILENAMES[logo_theme]
        path = Path(__file__).resolve().parents[3] / "assets" / "images" / filename
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._home_button.setIcon(QIcon())
            return

        content_bounds = QRegion(pixmap.mask()).boundingRect()
        if content_bounds.isValid() and not content_bounds.isEmpty():
            pixmap = pixmap.copy(content_bounds)
        screen = QGuiApplication.primaryScreen()
        scale = max(1.0, screen.devicePixelRatio() if screen is not None else 1.0)
        scaled = pixmap.scaled(
            round(BRAND_LOGO_MAX_WIDTH * scale),
            round(BRAND_LOGO_HEIGHT * scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(scale)
        self._home_button.setIcon(QIcon(scaled))
        self._home_button.setIconSize(
            QSize(round(scaled.width() / scale), round(scaled.height() / scale))
        )
        self._brand_logo_filename = filename

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
        expanded = bool(expanded)
        self._manual_tools_button.setText("Manual")
        if self._manual_stage_expanded == expanded:
            if not self._tutorial_active:
                self._manual_stage_frame.setVisible(expanded)
                self._toolbar.setFixedHeight(
                    APP_TOOLBAR_HEIGHT + MANUAL_TOOLBAR_HEIGHT
                    if expanded
                    else APP_TOOLBAR_HEIGHT
                )
            return

        self._manual_stage_expanded = expanded
        if expanded:
            self._manual_stage_frame.show()
            self._toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT + MANUAL_TOOLBAR_HEIGHT)
        else:
            self._manual_stage_frame.hide()
            self._toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT)

    def _start_tutorial(self) -> None:
        missing = self._tutorial_assets.missing_paths()
        if missing:
            QMessageBox.warning(
                self,
                "Tutorial assets are missing",
                "The tutorial cannot start because these files were not found:\n\n"
                + "\n".join(path.name for path in missing),
            )
            return

        self._tutorial_active = True
        self._clear_tutorial_guide()
        self._show_tutorial_step(0)

    def _show_tutorial_step(self, index: int) -> None:
        if not self._tutorial_active or not 0 <= index < len(TUTORIAL_STEPS):
            return

        self._clear_tutorial_guide()
        step = TUTORIAL_STEPS[index]
        self._tutorial_transitioning = True
        tool: QWidget | None = None
        try:
            if step.key == "automated":
                self._show_automated_pipeline()
                tool = self._main_menu.automated_profiles
            elif step.key == "automated_profiles":
                self._show_automated_profiles()
                tool = self._main_menu.automated_profiles
            else:
                self._open_tool(step.key)
                if self._active_tool_id != step.key:
                    return
                tool = self._active_tool
            self._load_tutorial_assets(step.key, tool)
        finally:
            self._tutorial_transitioning = False

        self._tutorial_step_index = index
        self._tutorial_bar.set_step(index, TUTORIAL_STEPS)
        self._manual_stage_frame.hide()
        self._tutorial_bar.show()
        self._toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT + TUTORIAL_TOOLBAR_HEIGHT)
        self.setWindowTitle(f"DLC Gait Assembler - Tutorial - {step.title}")
        self._begin_tutorial_guide(step.key, tool)

    def _load_tutorial_assets(self, step_key: str, tool: QWidget | None) -> None:
        if tool is None:
            return
        assets = self._tutorial_assets
        if step_key == "manual_calibration":
            tool._add_media_paths([assets.preview_video])
        elif step_key == "video_processing":
            tool._add_video_paths([assets.preview_video])
            tool.preview_title.setToolTip(
                f"Tutorial comparison output: {assets.processed_preview_video.name}"
            )
        elif step_key == "deeplabcut":
            if not getattr(tool, "_tutorial_assets_announced", False):
                tool._terminal.append_output(
                    "\n[Tutorial] Precomputed DeepLabCut example:\n"
                    f"  Video: {assets.analyzed_video.name}\n"
                    f"  CSV:   {assets.coordinate_csv.name}\n"
                    f"  H5:    {assets.coordinate_h5.name}\n"
                )
                tool._tutorial_assets_announced = True
        elif step_key == "knee_correction":
            tool._add_paths(
                [assets.analyzed_video, assets.coordinate_csv, assets.coordinate_h5]
            )
        elif step_key == "gait_parameter_analysis":
            runway = tool.kinematics_widget
            runway.input_mode_combo.setCurrentText(SINGLE_SIDE_VIEW_MODE_LABEL)
            runway._add_csv_paths([assets.coordinate_csv])
            item = runway.file_list.item(0)
            if item is not None:
                item.setText(assets.coordinate_csv.name)
                item.setToolTip(
                    "Tutorial source dataset:\n"
                    f"Video: {assets.analyzed_video.name}\n"
                    f"CSV: {assets.coordinate_csv.name}\n"
                    f"H5: {assets.coordinate_h5.name}"
                )
        elif step_key == "automated_profiles":
            tool._show_new_profile()
            tool.profile_name.setText("Tutorial manifest profile")
            tool._set_manifest_source(assets.processing_manifest)
            tool._calibration_source = assets.calibration_map.resolve()
            tool._set_analysis_manifest_source(assets.gait_manifest)
            tool._set_knee_manifest_source(assets.knee_manifest)
            tool._refresh_paths()
            self._tutorial_profile_draft_loaded = True
        elif step_key == "automated":
            tool._show_automation_menu()
            tool._add_video_paths([assets.preview_video])

    def _begin_tutorial_guide(self, step_key: str, tool: QWidget | None) -> None:
        if tool is None:
            return
        if step_key == "video_processing":
            guides = self._video_tutorial_guides(tool)
        elif step_key == "knee_correction":
            guides = self._knee_tutorial_guides(tool)
        elif step_key == "automated_profiles":
            guides = self._profile_tutorial_guides(tool)
        elif step_key == "automated":
            guides = self._automated_run_tutorial_guides(tool)
        else:
            guides = ()
        if not guides:
            return
        self._tutorial_guide_steps = tuple(guides)
        self._tutorial_guide_index = 0
        self._show_current_tutorial_guide()

    def _show_current_tutorial_guide(self) -> None:
        if not self._tutorial_guide_steps or self._tutorial_guide_index < 0:
            return
        guide = self._tutorial_guide_steps[self._tutorial_guide_index]
        if guide.prepare is not None:
            guide.prepare()
        target = guide.target()
        if target is None:
            self._tutorial_spotlight.clear_guide()
            return
        step = TUTORIAL_STEPS[self._tutorial_step_index]
        self._tutorial_bar.title_label.setText(f"{step.title}  ·  {guide.title}")
        self._tutorial_bar.instruction_label.setText(
            "Follow the arrow, match the target value, then choose Check and continue."
        )
        self._tutorial_bar.next_button.setText("Check and continue")
        self._tutorial_bar.next_button.setToolTip(
            "Verify the highlighted tutorial setting and continue."
        )
        self._tutorial_bar.previous_button.setEnabled(
            self._tutorial_step_index > 0 or self._tutorial_guide_index > 0
        )
        self._tutorial_spotlight.set_guide(
            target,
            index=self._tutorial_guide_index,
            total=len(self._tutorial_guide_steps),
            title=guide.title,
            instruction=guide.instruction,
            expected=guide.expected,
            can_apply=guide.apply_value is not None,
        )

    def _apply_tutorial_guide_value(self) -> None:
        if not self._tutorial_guide_steps or self._tutorial_guide_index < 0:
            return
        guide = self._tutorial_guide_steps[self._tutorial_guide_index]
        if guide.apply_value is None:
            return
        guide.apply_value()
        self._show_current_tutorial_guide()
        if guide.matches():
            self._tutorial_spotlight.show_feedback(
                "Matched. Choose Check and continue.", success=True
            )
        else:
            self._tutorial_spotlight.show_feedback(
                "The value could not be applied. Adjust the highlighted control manually."
            )

    def _clear_tutorial_guide(self) -> None:
        self._tutorial_guide_steps = ()
        self._tutorial_guide_index = -1
        if hasattr(self, "_tutorial_spotlight"):
            self._tutorial_spotlight.clear_guide()

    def _video_tutorial_guides(
        self, tool: VideoEditorWidget
    ) -> tuple[TutorialGuideStep, ...]:
        options, _trims = video_settings_from_manifest(
            self._tutorial_assets.processing_manifest
        )
        enhancements = options.enhancements
        return (
            TutorialGuideStep(
                "Open Regions",
                "The Regions tool defines one processed output for each camera view. "
                "Choose it before editing the crop rectangles.",
                "Regions is selected",
                lambda: tool.crop_tool_button,
                lambda: tool.crop_tool_button.isChecked(),
                lambda: tool._activate_tool_button(tool.crop_tool_button, "crop"),
            ),
            TutorialGuideStep(
                "Create the three views",
                "Create and name Right, Left, and Bottom, then set their edges from the "
                "manifest. Only Right is flipped vertically. You may enter the pixel "
                "edges manually or apply the exact normalized regions.",
                self._video_crop_target_text(tool, options),
                lambda: tool.settings_panel,
                lambda: self._video_regions_match(tool, options),
                lambda: self._apply_video_regions(tool, options),
                lambda: tool._activate_tool_button(tool.crop_tool_button, "crop"),
            ),
            TutorialGuideStep(
                "Open Enhancements",
                "Enhancements affect both the live preview and exported videos. Choose "
                "this tool to reveal the numeric controls.",
                "Enhancements is selected",
                lambda: tool.enhancements_tool_button,
                lambda: tool.enhancements_tool_button.isChecked(),
                lambda: tool._activate_tool_button(
                    tool.enhancements_tool_button, "enhancements"
                ),
            ),
            self._video_enhancement_guide(
                tool,
                "exposure",
                "Set exposure",
                "Raise exposure slightly to recover detail without changing brightness.",
                enhancements.exposure,
            ),
            self._video_enhancement_guide(
                tool,
                "sharpening",
                "Set sharpening",
                "Add modest edge sharpening for clearer tracked landmarks.",
                enhancements.sharpening,
            ),
            self._video_enhancement_guide(
                tool,
                "cas",
                "Set CAS",
                "Apply a small contrast-adaptive sharpening value after the main "
                "sharpening adjustment.",
                enhancements.cas,
            ),
            TutorialGuideStep(
                "Set export quality",
                "CRF controls H.264 quality. Lower values keep more detail and create "
                "larger files.",
                f"CRF {options.crf}",
                lambda: tool.crf_spin,
                lambda: tool.crf_spin.value() == options.crf,
                lambda: tool.crf_spin.setValue(options.crf),
            ),
            TutorialGuideStep(
                "Set encoding preset",
                "The preset controls encoding effort. Slow is appropriate for reusable "
                "analysis files when export time is less important than compression.",
                f"Preset {options.preset}",
                lambda: tool.preset_combo,
                lambda: tool.preset_combo.currentText() == options.preset,
                lambda: tool.preset_combo.setCurrentText(options.preset),
            ),
            TutorialGuideStep(
                "Review before processing",
                "The manifest has no inversion or saved trim ranges. Once all highlighted "
                "values match, this button would process the tutorial video. The tutorial "
                "does not start a long export.",
                "3 crop regions · Exposure 0.18 · Sharpening 0.16 · CAS 0.06 · "
                "CRF 16 · slow",
                lambda: tool.process_button,
                lambda: self._video_manifest_matches(tool, options),
                lambda: self._apply_complete_video_manifest(tool, options),
            ),
        )

    def _video_enhancement_guide(
        self,
        tool: VideoEditorWidget,
        field: str,
        title: str,
        instruction: str,
        expected: float,
    ) -> TutorialGuideStep:
        return TutorialGuideStep(
            title,
            instruction,
            f"{expected:.2f}",
            lambda: tool.settings_panel._enhancement_controls.get(field, {}).get(
                "spin"
            ),
            lambda: abs(
                getattr(tool.preview.enhancement_settings(), field) - expected
            )
            < 0.0001,
            lambda: self._set_video_enhancement(tool, field, expected),
            lambda: self._prepare_video_enhancement(tool, field),
        )

    @staticmethod
    def _prepare_video_enhancement(tool: VideoEditorWidget, field: str) -> None:
        tool._activate_tool_button(tool.enhancements_tool_button, "enhancements")
        control = tool.settings_panel._enhancement_controls.get(field, {}).get("spin")
        if control is not None:
            tool.settings_panel._scroll.ensureWidgetVisible(control, 0, 80)

    @staticmethod
    def _set_video_enhancement(
        tool: VideoEditorWidget, field: str, value: float
    ) -> None:
        MainWindow._prepare_video_enhancement(tool, field)
        control = tool.settings_panel._enhancement_controls.get(field, {}).get("spin")
        if control is not None:
            control.setValue(value)

    @staticmethod
    def _apply_video_regions(tool: VideoEditorWidget, options) -> None:
        tool.preview.set_crop_regions(options.crop_regions)
        tool.preview.set_invert_regions(options.invert_rects)
        tool.settings_panel.refresh()

    @staticmethod
    def _video_crop_target_text(tool: VideoEditorWidget, options) -> str:
        snapshot = tool.preview.region_snapshots()
        width = snapshot["width"]
        height = snapshot["height"]
        if width <= 0 or height <= 0:
            return (
                "Right 0–31.43% (vertical flip), Left 31.63–60.39%, "
                "Bottom 60.80–99.01%"
            )
        descriptions = []
        for region in options.crop_regions:
            rect = region.rect.clamped()
            left = round(rect.x * width)
            top = round(rect.y * height)
            right = round((rect.x + rect.width) * width)
            bottom = round((rect.y + rect.height) * height)
            suffix = " · Flip vertical" if region.flip_vertical else ""
            descriptions.append(
                f"{region.name}: L{left} T{top} R{right} B{bottom}{suffix}"
            )
        return "  •  ".join(descriptions)

    @staticmethod
    def _video_regions_match(tool: VideoEditorWidget, options) -> bool:
        current = tool.preview.crop_regions()
        expected = options.crop_regions
        if len(current) != len(expected):
            return False
        for actual, target in zip(current, expected, strict=True):
            if (
                actual.name != target.name
                or actual.flip_horizontal != target.flip_horizontal
                or actual.flip_vertical != target.flip_vertical
            ):
                return False
            for field in ("x", "y", "width", "height"):
                if abs(getattr(actual.rect, field) - getattr(target.rect, field)) > 0.001:
                    return False
        return True

    @classmethod
    def _video_manifest_matches(cls, tool: VideoEditorWidget, options) -> bool:
        if not cls._video_regions_match(tool, options):
            return False
        current = tool.preview.enhancement_settings()
        for field in (
            "sharpening",
            "cas",
            "brightness",
            "contrast",
            "exposure",
            "black_level",
            "tone_scale",
            "input_black",
            "input_white",
            "output_black",
            "output_white",
        ):
            if abs(getattr(current, field) - getattr(options.enhancements, field)) > 0.001:
                return False
        return (
            not tool.preview.invert_regions()
            and not any(tool._trim_ranges_by_video.values())
            and tool.crf_spin.value() == options.crf
            and tool.preset_combo.currentText() == options.preset
        )

    @staticmethod
    def _apply_complete_video_manifest(tool: VideoEditorWidget, options) -> None:
        tool.preview.set_crop_regions(options.crop_regions)
        tool.preview.set_invert_regions(options.invert_rects)
        tool.preview.set_enhancements(options.enhancements)
        tool._trim_ranges_by_video.clear()
        tool.crf_spin.setValue(options.crf)
        tool.preset_combo.setCurrentText(options.preset)
        tool.settings_panel.refresh()
        tool._refresh_trim_context()

    def _knee_tutorial_guides(
        self, tool: KneeCorrectionWidget
    ) -> tuple[TutorialGuideStep, ...]:
        settings = knee_settings_from_manifest(self._tutorial_assets.knee_manifest)
        return (
            TutorialGuideStep(
                "Confirm the paired dataset",
                "Knee correction needs a video and matching DLC CSV/H5 pair. The tutorial "
                "has already grouped the three files into one dataset.",
                "1 paired dataset · Ready",
                lambda: tool.pair_table,
                lambda: len(tool._pairs) == 1 and tool._pairs[0].is_paired,
            ),
            TutorialGuideStep(
                "Load the calibration scale",
                "Knee segment lengths are stored in centimeters, so import the calibration "
                "map that produced the manifest's pixel scale.",
                f"{settings.pixels_per_cm:.3f} px/cm",
                lambda: tool.calibration_map_button,
                lambda: tool._pixels_per_cm is not None
                and abs(tool._pixels_per_cm - settings.pixels_per_cm) < 0.0001,
                lambda: tool._set_calibration_map(self._tutorial_assets.calibration_map),
                lambda: tool.settings_tabs.setCurrentIndex(0),
            ),
            TutorialGuideStep(
                "Set femur length",
                "Enter the measured hip-to-knee distance used to reconstruct the knee.",
                f"{settings.hip_knee_length_cm:.1f} cm",
                lambda: tool.hip_knee_length,
                lambda: abs(
                    tool.hip_knee_length.value() - settings.hip_knee_length_cm
                )
                < 0.0001,
                lambda: tool.hip_knee_length.setValue(
                    settings.hip_knee_length_cm
                ),
                lambda: tool.settings_tabs.setCurrentIndex(0),
            ),
            TutorialGuideStep(
                "Set tibia/fibula length",
                "Enter the measured knee-to-ankle distance from the knee manifest.",
                f"{settings.knee_ankle_length_cm:.1f} cm",
                lambda: tool.knee_ankle_length,
                lambda: abs(
                    tool.knee_ankle_length.value() - settings.knee_ankle_length_cm
                )
                < 0.0001,
                lambda: tool.knee_ankle_length.setValue(
                    settings.knee_ankle_length_cm
                ),
                lambda: tool.settings_tabs.setCurrentIndex(0),
            ),
            TutorialGuideStep(
                "Open label selection",
                "The label tab controls which hip, knee, and ankle landmarks are used and "
                "how low-confidence frames are handled.",
                "Label selection tab",
                lambda: tool.settings_tabs.tabBar(),
                lambda: tool.settings_tabs.currentIndex() == 1,
                lambda: tool.settings_tabs.setCurrentIndex(1),
            ),
            TutorialGuideStep(
                "Set confidence cutoff",
                "Coordinates below this likelihood are not trusted for correction.",
                f"{settings.likelihood_threshold:.2f}",
                lambda: tool.likelihood_threshold,
                lambda: abs(
                    tool.likelihood_threshold.value()
                    - settings.likelihood_threshold
                )
                < 0.0001,
                lambda: tool.likelihood_threshold.setValue(
                    settings.likelihood_threshold
                ),
                lambda: tool.settings_tabs.setCurrentIndex(1),
            ),
            TutorialGuideStep(
                "Keep the generated label",
                "Corrected coordinates are written under this body-part name.",
                settings.output_knee_bodypart,
                lambda: tool.generated_knee_label_edit,
                lambda: tool.generated_knee_label_edit.text().strip()
                == settings.output_knee_bodypart,
                lambda: tool.generated_knee_label_edit.setText(
                    settings.output_knee_bodypart
                ),
                lambda: tool.settings_tabs.setCurrentIndex(1),
            ),
            TutorialGuideStep(
                "Use automatic direction",
                "Automatic direction uses the old knee position and frame-to-frame "
                "continuity to choose the correct geometric solution.",
                "Auto from old knee / continuity",
                lambda: tool.knee_direction_combo,
                lambda: tool.knee_direction_combo.currentData()
                == settings.knee_direction,
                lambda: tool.knee_direction_combo.setCurrentIndex(
                    tool.knee_direction_combo.findData(settings.knee_direction)
                ),
                lambda: tool.settings_tabs.setCurrentIndex(1),
            ),
            TutorialGuideStep(
                "Review before correction",
                "The manifest leaves hip, knee, and ankle labels on automatic detection. "
                "This button would generate corrected CSV/H5 copies; the tutorial stops "
                "before writing outputs.",
                "All knee manifest settings match",
                lambda: tool.run_button,
                lambda: self._knee_manifest_matches(tool, settings),
                lambda: self._apply_complete_knee_manifest(tool, settings),
            ),
        )

    @staticmethod
    def _knee_manifest_matches(tool: KneeCorrectionWidget, settings) -> bool:
        current = tool._settings()
        return (
            abs(current.hip_knee_length_cm - settings.hip_knee_length_cm) < 0.0001
            and abs(current.knee_ankle_length_cm - settings.knee_ankle_length_cm)
            < 0.0001
            and abs(current.pixels_per_cm - settings.pixels_per_cm) < 0.0001
            and abs(current.likelihood_threshold - settings.likelihood_threshold)
            < 0.0001
            and current.knee_bodyparts == settings.knee_bodyparts
            and current.hip_bodypart == settings.hip_bodypart
            and current.ankle_bodypart == settings.ankle_bodypart
            and current.output_knee_bodypart == settings.output_knee_bodypart
            and current.knee_direction == settings.knee_direction
        )

    def _apply_complete_knee_manifest(
        self, tool: KneeCorrectionWidget, settings
    ) -> None:
        if (
            tool._pixels_per_cm is None
            or abs(tool._pixels_per_cm - settings.pixels_per_cm) >= 0.0001
        ):
            tool._set_calibration_map(self._tutorial_assets.calibration_map)
        tool.hip_knee_length.setValue(settings.hip_knee_length_cm)
        tool.knee_ankle_length.setValue(settings.knee_ankle_length_cm)
        tool.likelihood_threshold.setValue(settings.likelihood_threshold)
        tool.generated_knee_label_edit.setText(settings.output_knee_bodypart)
        tool.knee_label_combo.setCurrentIndex(0)
        tool.hip_label_combo.setCurrentIndex(0)
        tool.ankle_label_combo.setCurrentIndex(0)
        tool.knee_direction_combo.setCurrentIndex(
            tool.knee_direction_combo.findData(settings.knee_direction)
        )

    def _profile_tutorial_guides(
        self, tool: AutomatedPipelineProfilesWidget
    ) -> tuple[TutorialGuideStep, ...]:
        assets = self._tutorial_assets
        return (
            TutorialGuideStep(
                "Name the profile",
                "A clear profile name identifies the complete reusable setup without "
                "changing any source files.",
                "Tutorial manifest profile",
                lambda: tool.profile_name,
                lambda: tool.profile_name.text() == "Tutorial manifest profile",
                lambda: tool.profile_name.setText("Tutorial manifest profile"),
            ),
            TutorialGuideStep(
                "Load video settings",
                "Step 1 reads the processing manifest and creates the Right, Left, and "
                "Bottom model slots from its named crop regions.",
                f"{assets.processing_manifest.name} · Right → Left → Bottom",
                lambda: tool.manifest_path_label,
                lambda: tool._manifest_source == assets.processing_manifest.resolve(),
                lambda: tool._set_manifest_source(assets.processing_manifest),
                lambda: tool.configuration_tabs.setCurrentIndex(0),
            ),
            TutorialGuideStep(
                "Assign DLC models",
                "A real profile needs one trained DeepLabCut config or project for each "
                "detected region. The tutorial has no model projects, so these slots stay "
                "empty and the draft is not saved.",
                "One model for Right, Left, and Bottom",
                lambda: tool.models_scroll,
                lambda: True,
                prepare=lambda: tool.configuration_tabs.setCurrentIndex(1),
            ),
            TutorialGuideStep(
                "Load analysis manifests",
                "Step 3 includes gait and knee correction, then reuses the tutorial "
                "calibration map, gait manifest, and knee manifest.",
                "Gait analysis + Knee correction · all three files selected",
                lambda: tool.configuration_tabs,
                lambda: self._profile_tutorial_draft_matches(tool),
                lambda: self._load_tutorial_profile_draft(tool),
                lambda: tool.configuration_tabs.setCurrentIndex(2),
            ),
            TutorialGuideStep(
                "Save a reusable profile",
                "After supplying real DLC model projects, Save validates and copies the "
                "profile assets into app-managed storage. This tutorial intentionally "
                "leaves the incomplete example as an unsaved draft.",
                "Save only after every readiness item is selected",
                lambda: tool.save_profile_button,
                lambda: True,
            ),
        )

    def _load_tutorial_profile_draft(
        self, tool: AutomatedPipelineProfilesWidget
    ) -> None:
        assets = self._tutorial_assets
        tool._set_manifest_source(assets.processing_manifest)
        tool._calibration_source = assets.calibration_map.resolve()
        tool._set_analysis_manifest_source(assets.gait_manifest)
        tool._set_knee_manifest_source(assets.knee_manifest)
        tool._refresh_paths()

    def _profile_tutorial_draft_matches(
        self, tool: AutomatedPipelineProfilesWidget
    ) -> bool:
        assets = self._tutorial_assets
        return (
            tool.include_gait_analysis_button.isChecked()
            and tool.include_knee_correction_button.isChecked()
            and tool._manifest_source == assets.processing_manifest.resolve()
            and tool._calibration_source == assets.calibration_map.resolve()
            and tool._analysis_manifest_source == assets.gait_manifest.resolve()
            and tool._knee_manifest_source == assets.knee_manifest.resolve()
        )

    def _automated_run_tutorial_guides(
        self, tool: AutomatedPipelineProfilesWidget
    ) -> tuple[TutorialGuideStep, ...]:
        return (
            TutorialGuideStep(
                "Choose a saved profile",
                "The run page loads saved profiles from the Profile selector. The tutorial "
                "draft was not saved because it has no trained DLC model projects.",
                "Select the profile for this camera and analysis setup",
                lambda: tool.profile_selector,
                lambda: True,
            ),
            TutorialGuideStep(
                "Queue source videos",
                "Add or drag videos here. The trimmed tutorial clip is already queued as "
                "an example and remains unchanged on disk.",
                f"1 queued video · {self._tutorial_assets.preview_video.name}",
                lambda: tool.video_list,
                lambda: self._tutorial_assets.preview_video.resolve()
                in tool._video_paths,
                lambda: tool._add_video_paths([self._tutorial_assets.preview_video]),
            ),
            TutorialGuideStep(
                "Run the combined pipeline",
                "Run pipeline applies the selected profile from video processing through "
                "its enabled analysis stages. The tutorial does not launch external "
                "DeepLabCut or write outputs.",
                "A saved profile + queued videos, then Run pipeline",
                lambda: tool.run_pipeline_button,
                lambda: True,
            ),
        )

    def _next_tutorial_step(self) -> None:
        if not self._tutorial_active:
            return
        if self._tutorial_guide_steps:
            guide = self._tutorial_guide_steps[self._tutorial_guide_index]
            if not guide.matches():
                self._tutorial_spotlight.show_feedback(
                    "This setting does not match yet. Adjust the highlighted control or "
                    'choose "Set for me", then try again.'
                )
                return
            if self._tutorial_guide_index < len(self._tutorial_guide_steps) - 1:
                self._tutorial_guide_index += 1
                self._show_current_tutorial_guide()
                return
            self._clear_tutorial_guide()
        if self._tutorial_step_index >= len(TUTORIAL_STEPS) - 1:
            self._finish_tutorial()
            return
        self._show_tutorial_step(self._tutorial_step_index + 1)

    def _previous_tutorial_step(self) -> None:
        if not self._tutorial_active:
            return
        if self._tutorial_guide_steps and self._tutorial_guide_index > 0:
            self._tutorial_guide_index -= 1
            self._show_current_tutorial_guide()
        elif self._tutorial_step_index > 0:
            self._show_tutorial_step(self._tutorial_step_index - 1)

    def _finish_tutorial(self) -> None:
        if not self._tutorial_active:
            return
        self._tutorial_active = False
        self._tutorial_step_index = -1
        self._clear_tutorial_guide()
        self._restore_profiles_after_tutorial()
        self._tutorial_bar.hide()
        self._tutorial_transitioning = True
        try:
            self._show_home_menu()
        finally:
            self._tutorial_transitioning = False

    def _cancel_tutorial_for_navigation(self) -> None:
        if not self._tutorial_active or self._tutorial_transitioning:
            return
        self._tutorial_active = False
        self._tutorial_step_index = -1
        self._clear_tutorial_guide()
        self._restore_profiles_after_tutorial()
        self._tutorial_bar.hide()

    def _restore_profiles_after_tutorial(self) -> None:
        if not self._tutorial_profile_draft_loaded:
            return
        self._tutorial_profile_draft_loaded = False
        self._main_menu.automated_profiles._refresh_profiles()

    @staticmethod
    def _screen_aware_initial_size() -> QSize:
        """Return a generous display-aware default above the supported minimum."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return DEFAULT_WINDOW_SIZE
        available = screen.availableGeometry()
        usable_width = available.width() - WINDOW_SCREEN_MARGIN
        usable_height = available.height() - WINDOW_SCREEN_MARGIN
        return QSize(
            max(
                MINIMUM_WINDOW_SIZE.width(),
                min(DEFAULT_WINDOW_SIZE.width(), usable_width),
            ),
            max(
                MINIMUM_WINDOW_SIZE.height(),
                min(DEFAULT_WINDOW_SIZE.height(), usable_height),
            ),
        )

    def _show_home_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._cancel_tutorial_for_navigation()

        self._active_tool = None
        self._active_tool_id = None
        self._home_menu_active = True
        self._automation_menu_active = False
        self._set_manual_pipeline_expanded(False)
        self._main_menu.show_home()
        self.setWindowTitle("DLC Gait Assembler")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_main_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._cancel_tutorial_for_navigation()

        self._active_tool = None
        self._active_tool_id = None
        self._home_menu_active = False
        self._automation_menu_active = False
        self._set_manual_pipeline_expanded(True)
        self._main_menu.show_manual()
        self.setWindowTitle("DLC Gait Assembler - Manual pipeline")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_automated_pipeline(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._cancel_tutorial_for_navigation()
        self._active_tool = None
        self._active_tool_id = None
        self._home_menu_active = False
        self._automation_menu_active = True
        self._automated_workspace_page = "run"
        self._set_manual_pipeline_expanded(False)
        self._main_menu.show_automated()
        self._main_menu.automated_profiles._show_automation_menu()
        self.setWindowTitle("DLC Gait Assembler - Automated pipeline")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_automated_profiles(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._cancel_tutorial_for_navigation()
        self._active_tool = None
        self._active_tool_id = None
        self._home_menu_active = False
        self._automation_menu_active = True
        self._automated_workspace_page = "profiles"
        self._set_manual_pipeline_expanded(False)
        self._main_menu.show_automated()
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
        self._home_menu_active = False
        self._automation_menu_active = index == 1
        if not self._automation_menu_active:
            self._active_tool_id = None
        self.setWindowTitle(
            "DLC Gait Assembler - Automated pipeline"
            if self._automation_menu_active
            else "DLC Gait Assembler - Manual pipeline"
        )
        self._refresh_stage_navigation()

    def _open_tool(self, tool_id: str) -> None:
        if not self._can_leave_active_tool():
            return
        self._cancel_tutorial_for_navigation()

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
        self._home_menu_active = False
        self._automation_menu_active = False
        self._set_manual_pipeline_expanded(True)
        self.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self._refresh_stage_navigation()
        self._show_widget(tool)

    def _refresh_stage_navigation(self) -> None:
        self._home_button.setProperty("activeNavigation", self._home_menu_active)
        self._automation_run_button.setProperty(
            "activeNavigation",
            self._automation_menu_active and self._automated_workspace_page == "run",
        )
        self._automation_profiles_button.setProperty(
            "activeNavigation",
            self._automation_menu_active and self._automated_workspace_page == "profiles",
        )
        manual_active = not self._home_menu_active and not self._automation_menu_active
        self._manual_tools_button.setProperty("activeManual", manual_active)
        for stage_id, stage_button in self._manual_stage_buttons.items():
            stage_button.setProperty("activeStage", stage_id == self._active_tool_id)
            stage_button.style().unpolish(stage_button)
            stage_button.style().polish(stage_button)
            stage_button.update()
        for button in (
            self._home_button,
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
        self._home_menu_active = True
        self._automation_menu_active = False


class MainMenuWidget(QWidget):
    tool_requested = Signal(str)
    automated_requested = Signal()
    manual_requested = Signal()
    tutorial_requested = Signal()

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
        content.setMaximumWidth(1280)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        view_stack = QStackedWidget()
        view_stack.setObjectName("MainMenuViewStack")

        home_page = QWidget()
        home_page.setObjectName("PipelineHomePage")
        home_layout = QVBoxLayout(home_page)
        home_layout.setContentsMargins(24, 24, 24, 24)
        home_layout.setSpacing(12)
        home_layout.addStretch(1)

        home_eyebrow = QLabel("PIPELINE WORKSPACE")
        home_eyebrow.setObjectName("HomeEyebrow")
        home_layout.addWidget(home_eyebrow)
        home_title = QLabel("Choose how you want to work")
        home_title.setObjectName("HomeTitle")
        home_layout.addWidget(home_title)
        home_description = QLabel(
            "Run the complete workflow automatically, or open the manual pipeline "
            "to work through each tool stage by stage."
        )
        home_description.setObjectName("HomeDescription")
        home_description.setWordWrap(True)
        home_layout.addWidget(home_description)

        choices = QHBoxLayout()
        choices.setSpacing(18)
        automated_card, automated_button = self._pipeline_choice_card(
            role="automated",
            eyebrow="AUTOMATED PIPELINE",
            title="Run a complete workflow",
            description=(
                "Select a saved profile, add videos, and monitor every processing "
                "stage from one workspace."
            ),
            action="Open automated pipeline",
        )
        automated_button.clicked.connect(self.automated_requested.emit)
        choices.addWidget(automated_card, 1)
        manual_card, manual_button = self._pipeline_choice_card(
            role="manual",
            eyebrow="MANUAL PIPELINE",
            title="Work stage by stage",
            description=(
                "Open calibration, video processing, DeepLabCut, correction, gait, "
                "and analysis tools individually."
            ),
            action="Open manual pipeline",
        )
        manual_button.clicked.connect(self.manual_requested.emit)
        choices.addWidget(manual_card, 1)
        home_layout.addLayout(choices)

        tutorial_card = QFrame()
        tutorial_card.setObjectName("TutorialChoiceCard")
        tutorial_layout = QHBoxLayout(tutorial_card)
        tutorial_layout.setContentsMargins(20, 14, 16, 14)
        tutorial_layout.setSpacing(16)
        tutorial_copy = QVBoxLayout()
        tutorial_copy.setContentsMargins(0, 0, 0, 0)
        tutorial_copy.setSpacing(2)
        tutorial_title = QLabel("New here? Follow the complete walkthrough")
        tutorial_title.setObjectName("TutorialChoiceTitle")
        tutorial_copy.addWidget(tutorial_title)
        tutorial_description = QLabel(
            "Use the included example videos and DLC files through the manual "
            "pipeline, then see how the automated workflow brings the stages together."
        )
        tutorial_description.setObjectName("TutorialChoiceDescription")
        tutorial_description.setWordWrap(True)
        tutorial_copy.addWidget(tutorial_description)
        tutorial_layout.addLayout(tutorial_copy, 1)
        tutorial_button = QPushButton("Run tutorial")
        tutorial_button.setObjectName("TutorialChoiceButton")
        tutorial_button.setCursor(Qt.PointingHandCursor)
        tutorial_button.setToolTip(
            "Start a guided walkthrough using the files in assets/tutorial."
        )
        tutorial_button.clicked.connect(self.tutorial_requested.emit)
        tutorial_layout.addWidget(tutorial_button)
        home_layout.addWidget(tutorial_card)

        home_layout.addStretch(2)
        self.automated_choice_button = automated_button
        self.manual_choice_button = manual_button
        self.tutorial_choice_button = tutorial_button
        self.home_page = home_page
        view_stack.addWidget(home_page)

        workspace_page = QWidget()
        workspace_page.setObjectName("PipelineWorkspacePage")
        workspace_layout = QVBoxLayout(workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(16)

        section_title = QLabel("Manual pipeline")
        section_title.setObjectName("WorkflowTitle")
        workspace_layout.addWidget(section_title)
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
        workspace_layout.addWidget(pipeline_tabs)
        self.workspace_page = workspace_page
        view_stack.addWidget(workspace_page)

        self.view_stack = view_stack
        content_layout.addWidget(view_stack)

        # Give the workspace a stable width based on the window, rather than its
        # current page's size hint. Pipeline previews must not make this centered
        # container grow or shrink while a run is in progress.
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        content_row.addStretch(1)
        content_row.addWidget(content, 100)
        content_row.addStretch(1)
        root.addLayout(content_row, 1)
        self._content = content

    @staticmethod
    def _pipeline_choice_card(
        *,
        role: str,
        eyebrow: str,
        title: str,
        description: str,
        action: str,
    ) -> tuple[QFrame, QPushButton]:
        card = QFrame()
        card.setObjectName("PipelineChoiceCard")
        card.setProperty("pipelineRole", role)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        type_label = QLabel(eyebrow)
        type_label.setObjectName("PipelineChoiceType")
        type_label.setProperty("pipelineRole", role)
        layout.addWidget(type_label)
        title_label = QLabel(title)
        title_label.setObjectName("PipelineChoiceTitle")
        layout.addWidget(title_label)
        description_label = QLabel(description)
        description_label.setObjectName("PipelineChoiceDescription")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        layout.addStretch(1)
        button = QPushButton(action)
        button.setObjectName("PipelineChoiceButton")
        button.setProperty("pipelineRole", role)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(description)
        layout.addWidget(button)
        return card, button

    def show_home(self) -> None:
        self.view_stack.setCurrentWidget(self.home_page)

    def show_manual(self) -> None:
        self.pipeline_tabs.setCurrentIndex(0)
        self.view_stack.setCurrentWidget(self.workspace_page)

    def show_automated(self) -> None:
        self.pipeline_tabs.setCurrentIndex(1)
        self.view_stack.setCurrentWidget(self.workspace_page)

    def _update_pipeline_heading(self, index: int) -> None:
        self.section_title.setVisible(index == 0)
        if index == 0:
            self.section_title.setText("Manual pipeline")

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
            QStackedWidget#MainMenuViewStack,
            QWidget#PipelineHomePage,
            QWidget#PipelineWorkspacePage {
                background: transparent;
                border: 0;
            }
            QLabel#HomeEyebrow {
                color: {theme.TOOL_1};
                font-size: 11px;
                font-weight: 750;
            }
            QLabel#HomeTitle {
                color: {theme.TEXT};
                font-size: 28px;
                font-weight: 750;
            }
            QLabel#HomeDescription {
                color: {theme.CONNECTOR};
                font-size: 14px;
                max-width: 760px;
                padding-bottom: 10px;
            }
            QFrame#PipelineChoiceCard {
                background: {theme.SURFACE};
                border: 2px solid {theme.BORDER};
                border-radius: 8px;
                min-height: 220px;
            }
            QFrame#PipelineChoiceCard[pipelineRole="automated"] {
                border-color: {theme.TOOL_1};
            }
            QFrame#PipelineChoiceCard[pipelineRole="manual"] {
                border-color: {theme.TOOL_3};
            }
            QLabel#PipelineChoiceType {
                font-size: 11px;
                font-weight: 750;
            }
            QLabel#PipelineChoiceType[pipelineRole="automated"] {
                color: {theme.TOOL_1};
            }
            QLabel#PipelineChoiceType[pipelineRole="manual"] {
                color: {theme.TOOL_3};
            }
            QLabel#PipelineChoiceTitle {
                color: {theme.TEXT};
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#PipelineChoiceDescription {
                color: {theme.CONNECTOR};
                font-size: 13px;
            }
            QPushButton#PipelineChoiceButton {
                background: {theme.BACKGROUND};
                border: 1px solid {theme.BORDER};
                border-radius: 5px;
                color: {theme.TEXT};
                font-size: 13px;
                font-weight: 700;
                min-height: 38px;
                padding: 0 14px;
            }
            QPushButton#PipelineChoiceButton[pipelineRole="automated"] {
                border-color: {theme.TOOL_1};
            }
            QPushButton#PipelineChoiceButton[pipelineRole="manual"] {
                border-color: {theme.TOOL_3};
            }
            QPushButton#PipelineChoiceButton:hover {
                background: {theme.PANEL};
                border-color: {theme.TEXT};
            }
            QFrame#TutorialChoiceCard {
                background: {theme.PANEL};
                border: 1px solid {theme.TOOL_2};
                border-radius: 7px;
            }
            QLabel#TutorialChoiceTitle {
                color: {theme.TEXT};
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#TutorialChoiceDescription {
                color: {theme.CONNECTOR};
                font-size: 12px;
            }
            QPushButton#TutorialChoiceButton {
                background: {theme.SURFACE};
                border: 1px solid {theme.TOOL_2};
                border-radius: 5px;
                color: {theme.TEXT};
                font-size: 13px;
                font-weight: 700;
                min-height: 36px;
                min-width: 130px;
                padding: 0 14px;
            }
            QPushButton#TutorialChoiceButton:hover {
                background: {theme.SOFT};
                border-color: {theme.TEXT};
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
        if hasattr(self, "automated_choice_button"):
            self.automated_choice_button.setIcon(
                _navigation_icon("run", theme.TOOL_1)
            )
            self.manual_choice_button.setIcon(
                _navigation_icon("manual", theme.TOOL_3)
            )
            self.tutorial_choice_button.setIcon(
                _navigation_icon("run", theme.TOOL_2)
            )
            self.automated_choice_button.setIconSize(QSize(18, 18))
            self.manual_choice_button.setIconSize(QSize(18, 18))
            self.tutorial_choice_button.setIconSize(QSize(18, 18))


class PartnerLogoLabel(QLabel):
    def __init__(self, filename: str):
        super().__init__()
        self.setObjectName("MainMenuLogo")
        self.setAccessibleName("Cho Force Lab logo" if filename == "choforcelab.png" else "NERVES Lab logo")
        self._website_url = QUrl(PARTNER_WEBSITES[filename])
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(f"Open {self._website_url.host()} in your browser")
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

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            QDesktopServices.openUrl(self._website_url)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            QDesktopServices.openUrl(self._website_url)
            event.accept()
            return
        super().keyPressEvent(event)


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
