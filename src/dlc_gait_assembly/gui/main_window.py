from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
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
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget
from dlc_gait_assembly.gui.knee_correction import KneeCorrectionWidget
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.widgets import CurrentPageStackedWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget

WORKFLOW_ROW_HEIGHT = 64
APP_TOOLBAR_HEIGHT = 64
MAIN_MENU_LOGO_HEIGHT = 24
MAIN_MENU_LOGO_MAX_WIDTH = 104
BRAND_LOGO_HEIGHT = 34
BRAND_LOGO_MAX_WIDTH = 160
BRAND_LOGO_FILENAMES = {
    "light": "DLC-Gait-Assembler-logo-light-original-clean.png",
    "dark": "DLC-Gait-Assembler-logo-dark-original-clean.png",
}
MANUAL_STAGE_DISPLAY_LABELS = {
    "manual_calibration": "Calibration",
    "video_processing": "Video\nprocessing",
    "deeplabcut": "DeepLabCut",
    "knee_correction": "Knee\ncorrection",
    "gait_parameter_analysis": "Gait\nanalysis",
    "pca_random_forest": "PCA + random\nforest",
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
        self._automated_workspace_page = "run"
        self._tool_widgets: dict[str, QWidget] = {}
        self._stack = CurrentPageStackedWidget()
        self._main_menu = MainMenuWidget(TOOL_SPECS)
        self._main_menu.tool_requested.connect(self._open_tool)
        self._main_menu.automated_requested.connect(self._show_automated_pipeline)
        self._main_menu.manual_requested.connect(self._show_main_menu)
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "_primary_navigation_highlight"):
            self._snap_primary_navigation_highlight()
        if getattr(self, "_manual_stage_expanded", False):
            self._position_manual_stage_rail()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "_manual_stage_expanded", False):
            self._position_manual_stage_rail()

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

        manual_pipeline_group = QFrame(primary_row)
        manual_pipeline_group.setObjectName("ManualPipelineGroup")
        manual_pipeline_layout = QHBoxLayout(manual_pipeline_group)
        manual_pipeline_layout.setContentsMargins(0, 0, 0, 0)
        manual_pipeline_layout.setSpacing(0)

        manual_tools_button = QToolButton(manual_pipeline_group)
        manual_tools_button.setObjectName("ManualPipelineButton")
        manual_tools_button.setText("Manual")
        manual_tools_button.setProperty("navigationRole", "manual")
        manual_tools_button.setToolTip("Open the manual pipeline and its stages.")
        manual_tools_button.setCursor(Qt.PointingHandCursor)
        manual_tools_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        manual_tools_button.setFixedWidth(106)
        manual_tools_button.clicked.connect(
            lambda _checked=False: self._manual_navigation_clicked()
        )
        self._manual_tools_button = manual_tools_button
        manual_pipeline_layout.addWidget(manual_tools_button)

        navigation_highlight = QFrame(primary_row)
        navigation_highlight.setObjectName("PrimaryNavigationHighlight")
        navigation_highlight.setProperty("navigationRole", "automated")
        navigation_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        navigation_highlight.hide()
        navigation_highlight.lower()
        self._primary_navigation_highlight = navigation_highlight
        self._primary_navigation_animation = QPropertyAnimation(
            navigation_highlight,
            b"geometry",
            self,
        )
        self._primary_navigation_animation.setDuration(230)
        self._primary_navigation_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )
        self._primary_row = primary_row
        self._primary_layout = primary_layout
        self._primary_navigation_layout = navigation_layout

        manual_stage_frame = QFrame(primary_row)
        manual_stage_frame.setObjectName("ManualStageExpansion")
        manual_stage_layout = QHBoxLayout(manual_stage_frame)
        manual_stage_layout.setContentsMargins(6, 3, 6, 3)
        manual_stage_layout.setSpacing(0)
        self._manual_stage_buttons: dict[str, QPushButton] = {}
        for index, spec in enumerate(TOOL_SPECS):
            button = QPushButton(MANUAL_STAGE_DISPLAY_LABELS[spec.id])
            button.setObjectName("ManualStageButton")
            button.setProperty("manualStage", spec.id)
            button.setProperty("activeStage", False)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            button.setEnabled(spec.enabled)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(spec.label)
            if spec.enabled:
                button.clicked.connect(
                    lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id)
                )
            self._manual_stage_buttons[spec.id] = button
            manual_stage_layout.addWidget(button)
            if index < len(TOOL_SPECS) - 1:
                separator = QLabel(">")
                separator.setObjectName("ManualStageSeparator")
                separator.setAlignment(Qt.AlignCenter)
                manual_stage_layout.addWidget(separator)
        manual_stage_frame.hide()
        self._manual_stage_frame = manual_stage_frame
        self._manual_stage_expanded = False
        primary_layout.addWidget(manual_pipeline_group)
        self._manual_pipeline_group = manual_pipeline_group
        self._manual_stage_animation = QPropertyAnimation(
            manual_stage_frame,
            b"geometry",
            self,
        )
        self._manual_stage_animation.setDuration(260)
        self._manual_stage_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._manual_stage_animation.finished.connect(
            self._manual_stage_animation_finished
        )

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

        shell_layout.addWidget(toolbar)
        shell_layout.addWidget(self._stack, 1)
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
                QFrame#PrimaryNavigationHighlight {
                    border: 1px solid transparent;
                    border-bottom-width: 3px;
                    border-radius: 6px;
                }
                QFrame#PrimaryNavigationHighlight[navigationRole="automated"] {
                    background: NAV_RUN_FILL;
                    border-bottom-color: {theme.TOOL_1};
                }
                QFrame#PrimaryNavigationHighlight[navigationRole="profiles"] {
                    background: NAV_PROFILES_FILL;
                    border-bottom-color: {theme.TOOL_2};
                }
                QFrame#PrimaryNavigationHighlight[navigationRole="manual"] {
                    background: NAV_MANUAL_FILL;
                    border-bottom-color: {theme.TOOL_3};
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
                    background: transparent;
                    border-bottom-color: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QPushButton#TopAutomationButton[navigationRole="profiles"][activeNavigation="true"] {
                    background: transparent;
                    border-bottom-color: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QToolButton#ManualPipelineButton[activeManual="true"] {
                    background: transparent;
                    border-bottom-color: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QFrame#ManualStageExpansion {
                    background: transparent;
                    border: 0;
                }
                QFrame#ManualPipelineGroup {
                    background: transparent;
                    border: 0;
                }
                QPushButton#ManualStageButton {
                    background: transparent;
                    border: 0;
                    border-radius: 0;
                    color: {theme.CONNECTOR};
                    font-size: 9px;
                    font-weight: 650;
                    min-height: 40px;
                    max-height: 40px;
                    padding: 0 1px;
                }
                QPushButton#ManualStageButton:hover {
                    background: transparent;
                    color: {theme.TEXT};
                }
                QPushButton#ManualStageButton[activeStage="true"] {
                    background: transparent;
                    color: {theme.TOOL_3};
                    font-weight: 700;
                }
                QLabel#ManualStageSeparator {
                    background: transparent;
                    border: 0;
                    color: {theme.TOOL_3};
                    font-size: 14px;
                    font-weight: 700;
                    padding: 0 1px;
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
            self._toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT)
            return

        self._manual_stage_expanded = expanded
        animation = self._manual_stage_animation
        animation.stop()
        if expanded:
            target = self._manual_stage_target_geometry()
            start = QRect(target.x(), target.y(), 0, target.height())
            self._manual_stage_frame.setGeometry(start)
            self._manual_stage_frame.show()
            self._manual_stage_frame.raise_()
            animation.setStartValue(start)
            animation.setEndValue(target)
        else:
            start = self._manual_stage_frame.geometry()
            animation.setStartValue(start)
            animation.setEndValue(QRect(start.x(), start.y(), 0, start.height()))
        animation.start()
        self._toolbar.setFixedHeight(APP_TOOLBAR_HEIGHT)

    def _manual_stage_target_geometry(self) -> QRect:
        self._primary_layout.activate()
        anchor = self._manual_tools_button.mapTo(
            self._primary_row, self._manual_tools_button.rect().topRight()
        )
        x = anchor.x() + 8
        settings_left = self._settings_button.mapTo(
            self._primary_row, self._settings_button.rect().topLeft()
        ).x()
        width = min(420, max(0, settings_left - x - 12))
        height = 50
        return QRect(x, (APP_TOOLBAR_HEIGHT - height) // 2, width, height)

    def _position_manual_stage_rail(self) -> None:
        if self._manual_stage_animation.state() == QPropertyAnimation.State.Running:
            return
        self._manual_stage_frame.setGeometry(self._manual_stage_target_geometry())
        self._manual_stage_frame.raise_()

    def _manual_stage_animation_finished(self) -> None:
        if self._manual_stage_expanded:
            self._position_manual_stage_rail()
            if not self._automation_menu_active and not self._home_menu_active:
                self._snap_primary_navigation_highlight()
            return
        self._manual_stage_frame.hide()

    def _manual_navigation_clicked(self) -> None:
        manual_active = not self._home_menu_active and not self._automation_menu_active
        if manual_active and self._manual_stage_expanded:
            self._set_manual_pipeline_expanded(False)
            return
        self._show_main_menu()

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
        self._animate_primary_navigation_highlight()

    def _animate_primary_navigation_highlight(self) -> None:
        target_button, role = self._active_primary_navigation_target()
        highlight = self._primary_navigation_highlight
        animation = self._primary_navigation_animation
        if target_button is None:
            animation.stop()
            highlight.hide()
            return

        target_geometry = self._primary_navigation_target_geometry(target_button)
        self._style_primary_navigation_highlight(role)

        if highlight.isHidden() or not self.isVisible():
            animation.stop()
            highlight.setGeometry(target_geometry)
            highlight.show()
            highlight.lower()
            return

        animation.stop()
        animation.setStartValue(highlight.geometry())
        animation.setEndValue(target_geometry)
        highlight.show()
        highlight.lower()
        animation.start()

    def _snap_primary_navigation_highlight(self) -> None:
        target_button, role = self._active_primary_navigation_target()
        if target_button is None:
            self._primary_navigation_animation.stop()
            self._primary_navigation_highlight.hide()
            return
        self._primary_navigation_animation.stop()
        self._style_primary_navigation_highlight(role)
        self._primary_navigation_highlight.setGeometry(
            self._primary_navigation_target_geometry(target_button)
        )
        self._primary_navigation_highlight.show()
        self._primary_navigation_highlight.lower()

    def _primary_navigation_target_geometry(self, target_button):
        self._primary_navigation_layout.activate()
        self._primary_layout.activate()
        top_left = target_button.mapTo(self._primary_row, target_button.rect().topLeft())
        return target_button.rect().translated(top_left)

    def _style_primary_navigation_highlight(self, role: str) -> None:
        highlight = self._primary_navigation_highlight
        if highlight.property("navigationRole") == role:
            return
        highlight.setProperty("navigationRole", role)
        highlight.style().unpolish(highlight)
        highlight.style().polish(highlight)

    def _active_primary_navigation_target(self):
        if self._automation_menu_active:
            if self._automated_workspace_page == "profiles":
                return self._automation_profiles_button, "profiles"
            return self._automation_run_button, "automated"
        if not self._home_menu_active:
            return self._manual_tools_button, "manual"
        return None, ""

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

        home_layout.addStretch(2)
        self.automated_choice_button = automated_button
        self.manual_choice_button = manual_button
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
            self.automated_choice_button.setIconSize(QSize(18, 18))
            self.manual_choice_button.setIconSize(QSize(18, 18))


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
