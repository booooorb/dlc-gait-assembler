from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPauseAnimation,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
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
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
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
from dlc_gait_assembly.gui.gait_analysis.ladder_window import LadderAnalysisWidget
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget
from dlc_gait_assembly.gui.knee_correction import KneeCorrectionWidget
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.widgets import CurrentPageStackedWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget

WORKFLOW_ROW_HEIGHT = 44
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
MANUAL_STAGE_ICONS = {
    "manual_calibration": "calibration-grid",
    "video_processing": "film",
    "deeplabcut": "joints",
    "knee_correction": "knee",
    "gait_parameter_analysis": "gait",
    "pca_random_forest": "chart",
}
PARTNER_WEBSITES = {
    "choforcelab.png": "https://www.choforcelab.ca",
    "NERVES_Logo.png": "https://nerves.bme.utah.edu",
}
MINIMUM_WINDOW_SIZE = QSize(1100, 640)
DEFAULT_WINDOW_SIZE = QSize(1440, 900)
WINDOW_SCREEN_MARGIN = 64
MAIN_MENU_ICON_ASSET_DIR = Path(__file__).resolve().parents[3] / "assets" / "images" / "main_menu_icons"
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

    if icon_name == "automated":
        painter.drawEllipse(QRectF(1.8, 1.8, 14.4, 14.4))
        path = QPainterPath()
        path.moveTo(7.1, 5.2)
        path.lineTo(13.0, 9.0)
        path.lineTo(7.1, 12.8)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawPath(path)
    elif icon_name == "runway":
        path = QPainterPath()
        path.moveTo(5.0, 16.0)
        path.lineTo(7.1, 2.0)
        path.moveTo(13.0, 16.0)
        path.lineTo(10.9, 2.0)
        painter.drawPath(path)
        for y in (5.0, 9.0, 13.0):
            painter.drawLine(QPointF(8.4, y), QPointF(9.6, y))
    elif icon_name == "profiles":
        painter.setBrush(Qt.NoBrush)
        for top, inset in ((2.4, 0.0), (6.4, 0.8), (10.4, 1.6)):
            painter.drawRoundedRect(QRectF(2.4 + inset, top, 13.2 - inset * 2, 4.2), 1.2, 1.2)
    elif icon_name == "manual":
        painter.setBrush(Qt.NoBrush)
        for y, knob_x in ((4.0, 6.0), (9.0, 12.0), (14.0, 8.5)):
            painter.drawLine(QPointF(2.5, y), QPointF(15.5, y))
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(knob_x, y), 2.0, 2.0)
            painter.setBrush(Qt.NoBrush)
    elif icon_name == "ladder":
        painter.drawLine(QPointF(4.0, 2.0), QPointF(4.0, 16.0))
        painter.drawLine(QPointF(14.0, 2.0), QPointF(14.0, 16.0))
        for y in (4.0, 7.5, 11.0, 14.5):
            painter.drawLine(QPointF(4.0, y), QPointF(14.0, y))

    painter.end()
    return QIcon(pixmap)


def _menu_asset_pixmap(name: str, size: int) -> QPixmap:
    """Load a reference-derived main-menu illustration at a crisp UI size."""
    source = QPixmap(str(MAIN_MENU_ICON_ASSET_DIR / f"{name}.png"))
    if source.isNull():
        return source
    return source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class MenuIllustrationLabel(QLabel):
    """Aspect-fit a high-resolution menu illustration without affecting layout size."""

    def __init__(self, asset_name: str, accessible_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("WorkspaceChoiceIllustration")
        self.setAccessibleName(accessible_name)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(178)
        self._source_pixmap = QPixmap(str(MAIN_MENU_ICON_ASSET_DIR / f"{asset_name}.png"))
        self._rendered_size = QSize()
        self._render_for_size(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(360, 178)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_for_size(self.contentsRect().size())

    def _render_for_size(self, target_size: QSize) -> None:
        if self._source_pixmap.isNull() or target_size.isEmpty() or target_size == self._rendered_size:
            return
        self._rendered_size = target_size
        self.setPixmap(
            self._source_pixmap.scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )


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

LADDER_TOOL_SPEC = ToolSpec(
    "ladder_analysis",
    "Ladder Analysis",
    LadderAnalysisWidget,
    True,
    description="Detect, review, and export ladder-rung footfall events.",
)


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
        self._main_menu.runway_requested.connect(self._show_runway_menu)
        self._main_menu.automated_requested.connect(self._show_automated_pipeline)
        self._main_menu.manual_requested.connect(self._show_main_menu)
        self._main_menu.pipeline_tabs.currentChanged.connect(self._pipeline_tab_changed)
        self._main_menu.automated_profiles.workspace_changed.connect(self._automated_workspace_changed)
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
            self._apply_tool_surface_depth(tool)
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
            self._snap_manual_stage_highlight()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "_manual_stage_expanded", False):
            self._snap_manual_stage_highlight()

    def _build_shell(self, initial_theme_mode: str) -> None:
        shell = QWidget()
        shell.setObjectName("AppShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("AppToolbar")
        toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT)
        toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)

        primary_row = QFrame()
        primary_row.setObjectName("PrimaryToolbarRow")
        primary_row.setFixedHeight(APP_TOOLBAR_HEIGHT)
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

        runway_button = QToolButton()
        runway_button.setObjectName("RunwayNavigationButton")
        runway_button.setText("Runway  ›")
        runway_button.setProperty("activeNavigation", False)
        runway_button.setProperty("navigationRole", "runway")
        runway_button.setCursor(Qt.PointingHandCursor)
        runway_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        runway_button.setToolTip("Show automated, profile, and manual runway workflows.")
        runway_button.clicked.connect(lambda _checked=False: self._toggle_runway_options())
        navigation_layout.addWidget(runway_button)
        self._runway_button = runway_button

        runway_options = QFrame()
        runway_options.setObjectName("RunwayOptions")
        runway_options_layout = QHBoxLayout(runway_options)
        runway_options_layout.setContentsMargins(9, 0, 9, 0)
        runway_options_layout.setSpacing(4)

        automation_group_label = QLabel("AUTOMATION")
        automation_group_label.setObjectName("RunwayGroupLabel")
        runway_options_layout.addWidget(automation_group_label)

        automated_button = QPushButton("Automated")
        automated_button.setObjectName("RunwayOptionButton")
        automated_button.setProperty("runwayOption", "automated")
        automated_button.setCursor(Qt.PointingHandCursor)
        automated_button.clicked.connect(self._show_automated_pipeline)
        runway_options_layout.addWidget(automated_button)
        self._automation_run_button = automated_button

        profiles_button = QPushButton("Profiles")
        profiles_button.setObjectName("RunwayOptionButton")
        profiles_button.setProperty("runwayOption", "profiles")
        profiles_button.setCursor(Qt.PointingHandCursor)
        profiles_button.clicked.connect(self._show_automated_profiles)
        runway_options_layout.addWidget(profiles_button)
        self._automation_profiles_button = profiles_button

        runway_group_divider = QFrame()
        runway_group_divider.setObjectName("RunwayGroupDivider")
        runway_group_divider.setFrameShape(QFrame.VLine)
        runway_options_layout.addWidget(runway_group_divider)

        manual_group_label = QLabel("MANUAL")
        manual_group_label.setObjectName("RunwayManualLabel")
        runway_options_layout.addWidget(manual_group_label)
        runway_options_layout.addSpacing(8)

        manual_button = QToolButton()
        manual_button.setObjectName("RunwayManualButton")
        manual_button.setText("Manual")
        manual_button.setCursor(Qt.PointingHandCursor)
        manual_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        manual_button.setToolTip("Slide down the manual runway stages.")
        manual_button.clicked.connect(self._show_main_menu)
        runway_options_layout.addWidget(manual_button)
        self._runway_manual_button = manual_button
        runway_mode_highlight = QFrame(runway_options)
        runway_mode_highlight.setObjectName("RunwayModeHighlight")
        runway_mode_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        runway_mode_highlight.hide()
        self._runway_mode_highlight = runway_mode_highlight
        self._runway_mode_highlight_animation = QPropertyAnimation(
            runway_mode_highlight, b"geometry", self
        )
        self._runway_mode_highlight_animation.setDuration(220)
        self._runway_mode_highlight_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        runway_options.setFixedHeight(46)
        runway_options.setMaximumWidth(0)
        runway_options.hide()
        navigation_layout.addWidget(runway_options, 0, Qt.AlignVCenter)
        self._runway_options = runway_options
        self._runway_options_expanded = False
        self._runway_options_animation = QPropertyAnimation(runway_options, b"maximumWidth", self)
        self._runway_options_animation.setDuration(230)
        self._runway_options_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._runway_options_animation.finished.connect(self._runway_options_animation_finished)

        ladder_button = QPushButton("Ladder")
        ladder_button.setObjectName("LadderNavigationButton")
        ladder_button.setProperty("activeNavigation", False)
        ladder_button.setProperty("navigationRole", "ladder")
        ladder_button.setCursor(Qt.PointingHandCursor)
        ladder_button.setToolTip("Open ladder analysis.")
        ladder_button.clicked.connect(lambda _checked=False: self._open_tool(LADDER_TOOL_SPEC.id))
        navigation_layout.addWidget(ladder_button)
        self._ladder_button = ladder_button
        primary_layout.addWidget(primary_navigation)
        self._primary_navigation = primary_navigation

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
        manual_tools_button.clicked.connect(lambda _checked=False: self._manual_navigation_clicked())
        self._manual_tools_button = manual_tools_button
        manual_tools_button.hide()

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
        self._primary_navigation_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._primary_row = primary_row
        self._primary_layout = primary_layout
        self._primary_navigation_layout = navigation_layout

        manual_stage_frame = QFrame(toolbar)
        manual_stage_frame.setObjectName("ManualStageExpansion")
        manual_stage_layout = QHBoxLayout(manual_stage_frame)
        manual_stage_layout.setContentsMargins(8, 2, 8, 2)
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
            button.setIcon(interface_icon(MANUAL_STAGE_ICONS[spec.id], theme.TOOL_3))
            button.setIconSize(QSize(15, 15))
            if spec.enabled:
                button.clicked.connect(lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id))
            self._manual_stage_buttons[spec.id] = button
            manual_stage_layout.addWidget(button)
            if index < len(TOOL_SPECS) - 1:
                separator = QLabel(">")
                separator.setObjectName("ManualStageSeparator")
                separator.setAlignment(Qt.AlignCenter)
                manual_stage_layout.addWidget(separator)
        manual_stage_highlight = QFrame(manual_stage_frame)
        manual_stage_highlight.setObjectName("ManualStageHighlight")
        manual_stage_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        manual_stage_highlight.hide()
        self._manual_stage_highlight = manual_stage_highlight
        self._manual_stage_highlight_animation = QPropertyAnimation(
            manual_stage_highlight,
            b"geometry",
            self,
        )
        self._manual_stage_highlight_animation.setDuration(220)
        self._manual_stage_highlight_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        manual_stage_frame.hide()
        manual_stage_frame.setMaximumHeight(0)
        self._manual_stage_frame = manual_stage_frame
        self._manual_stage_expanded = False
        manual_pipeline_group.hide()
        self._manual_pipeline_group = manual_pipeline_group
        self._manual_stage_animation = QPropertyAnimation(
            manual_stage_frame,
            b"maximumHeight",
            self,
        )
        self._manual_stage_animation.setDuration(210)
        self._manual_stage_animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        self._manual_stage_animation.finished.connect(self._manual_stage_animation_finished)
        self._toolbar_height_animation = QPropertyAnimation(toolbar, b"minimumHeight", self)
        self._toolbar_height_animation.setDuration(210)
        self._toolbar_height_animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        self._toolbar_max_height_animation = QPropertyAnimation(toolbar, b"maximumHeight", self)
        self._toolbar_max_height_animation.setDuration(210)
        self._toolbar_max_height_animation.setEasingCurve(QEasingCurve.Type.OutQuart)

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
                    background-image: url({theme.BACKGROUND_TEXTURE});
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
                QFrame#PrimaryNavigationHighlight[navigationRole="runway"] {
                    background: NAV_PARENT_FILL;
                    border-bottom-color: {theme.CONNECTOR};
                }
                QFrame#PrimaryNavigationHighlight[navigationRole="ladder"] {
                    background: NAV_PROFILES_FILL;
                    border-bottom-color: {theme.TOOL_2};
                }
                QToolButton#RunwayNavigationButton,
                QPushButton#LadderNavigationButton,
                QPushButton#RunwayOptionButton,
                QToolButton#RunwayManualButton,
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
                QToolButton#RunwayNavigationButton:hover,
                QPushButton#LadderNavigationButton:hover,
                QPushButton#RunwayOptionButton:hover,
                QToolButton#RunwayManualButton:hover,
                QToolButton#RunwayManualButton:open,
                QToolButton#ManualPipelineButton:hover {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QToolButton#RunwayNavigationButton[activeNavigation="true"] {
                    background: transparent;
                    border-color: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QPushButton#LadderNavigationButton[activeNavigation="true"] {
                    background: transparent;
                    border-bottom-color: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QFrame#RunwayOptions {
                    background: RUNWAY_GROUP_FILL;
                    border: 1px solid RUNWAY_GROUP_BORDER;
                    border-radius: 7px;
                }
                QLabel#RunwayGroupLabel,
                QLabel#RunwayManualLabel {
                    background: transparent;
                    border: 0;
                    color: {theme.CONNECTOR};
                    font-size: 8px;
                    font-weight: 700;
                    padding: 0 2px;
                }
                QLabel#RunwayManualLabel {
                    color: {theme.TOOL_3};
                }
                QFrame#RunwayGroupDivider {
                    background: {theme.BORDER};
                    border: 0;
                    min-width: 1px;
                    max-width: 1px;
                    min-height: 24px;
                    max-height: 24px;
                    margin: 0 4px;
                }
                QPushButton#RunwayOptionButton[runwayOption="automated"] {
                    color: {theme.TOOL_1};
                    border-color: transparent;
                    background: transparent;
                }
                QPushButton#RunwayOptionButton[runwayOption="profiles"] {
                    color: {theme.TOOL_2};
                    border-color: transparent;
                    background: transparent;
                }
                QToolButton#RunwayManualButton {
                    color: {theme.TOOL_3};
                    border-color: transparent;
                    background: transparent;
                }
                QPushButton#RunwayOptionButton[runwayOption="automated"][activeNavigation="true"] {
                    background: transparent;
                    border-color: transparent;
                    font-weight: 700;
                }
                QPushButton#RunwayOptionButton[runwayOption="profiles"][activeNavigation="true"] {
                    background: transparent;
                    border-color: transparent;
                    font-weight: 700;
                }
                QToolButton#RunwayManualButton[activeNavigation="true"] {
                    background: transparent;
                    border-color: transparent;
                    font-weight: 700;
                }
                QFrame#RunwayModeHighlight {
                    background: transparent;
                    border: 0;
                    border-radius: 6px;
                }
                QFrame#RunwayModeHighlight[runwayMode="automated"] {
                    background: COLOR_AUTO_FILL;
                    border-bottom: 3px solid {theme.TOOL_1};
                }
                QFrame#RunwayModeHighlight[runwayMode="profiles"] {
                    background: COLOR_PROFILES_FILL;
                    border-bottom: 3px solid {theme.TOOL_2};
                }
                QFrame#RunwayModeHighlight[runwayMode="manual"] {
                    background: COLOR_MANUAL_FILL;
                    border-bottom: 3px solid {theme.TOOL_3};
                }
                QToolButton#ManualPipelineButton[activeManual="true"] {
                    background: transparent;
                    border-bottom-color: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QFrame#ManualStageExpansion {
                    background: {theme.PANEL};
                    border: 0;
                    border-top: 1px solid {theme.BORDER};
                    border-bottom: 1px solid {theme.BORDER};
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
                    font-size: 11px;
                    font-weight: 600;
                    min-height: 34px;
                    max-height: 34px;
                    padding: 0 5px;
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
                QFrame#ManualStageHighlight {
                    background: {theme.TOOL_3};
                    border: 0;
                    border-radius: 1px;
                    min-height: 3px;
                    max-height: 3px;
                }
                QLabel#ManualStageSeparator {
                    background: transparent;
                    border: 0;
                    color: {theme.BORDER};
                    font-size: 13px;
                    font-weight: 600;
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
            stylesheet.replace("NAV_HOME_FILL", theme.mix_hex(theme.TOOL_1, theme.SURFACE, 0.9))
            .replace("NAV_RUN_FILL", theme.mix_hex(theme.TOOL_1, theme.SURFACE, 0.84))
            .replace("NAV_PARENT_FILL", theme.mix_hex(theme.CONNECTOR, theme.SURFACE, 0.9))
            .replace("NAV_PROFILES_FILL", theme.mix_hex(theme.TOOL_2, theme.SURFACE, 0.86))
            .replace("NAV_MANUAL_FILL", theme.mix_hex(theme.TOOL_3, theme.SURFACE, 0.86))
            .replace("COLOR_AUTO_BORDER", theme.mix_hex(theme.TOOL_1, theme.BORDER, 0.35))
            .replace("COLOR_AUTO_FILL", theme.mix_hex(theme.TOOL_1, theme.SURFACE, 0.92))
            .replace("COLOR_PROFILES_BORDER", theme.mix_hex(theme.TOOL_2, theme.BORDER, 0.35))
            .replace("COLOR_PROFILES_FILL", theme.mix_hex(theme.TOOL_2, theme.SURFACE, 0.92))
            .replace("COLOR_MANUAL_BORDER", theme.mix_hex(theme.TOOL_3, theme.BORDER, 0.35))
            .replace("COLOR_MANUAL_FILL", theme.mix_hex(theme.TOOL_3, theme.SURFACE, 0.92))
            .replace("RUNWAY_GROUP_BORDER", theme.mix_hex(theme.TOOL_1, theme.BORDER, 0.65))
            .replace("RUNWAY_GROUP_FILL", theme.mix_hex(theme.TOOL_1, theme.SURFACE, 0.95))
            .replace("RUNWAY_SELECTED_FILL", theme.mix_hex(theme.CONNECTOR, theme.SURFACE, 0.9))
            .replace("RUNWAY_SELECTED_BORDER", theme.mix_hex(theme.CONNECTOR, theme.BORDER, 0.45))
            .replace("RUNWAY_SELECTED_ACCENT", theme.CONNECTOR)
        )
        self._shell.setStyleSheet(stylesheet)
        self._apply_navigation_icons()

    def _apply_navigation_icons(self) -> None:
        self._apply_brand_logo()
        navigation_icons = (
            (self._runway_button, "runway", theme.TEXT),
            (self._automation_run_button, "automated", theme.TOOL_1),
            (self._automation_profiles_button, "profiles", theme.TOOL_2),
            (self._ladder_button, "ladder", theme.TOOL_2),
            (self._runway_manual_button, "manual", theme.TOOL_3),
        )
        for button, icon_name, color in navigation_icons:
            button.setIcon(_navigation_icon(icon_name, color))
            button.setIconSize(QSize(18, 18))
        for stage_id, button in self._manual_stage_buttons.items():
            button.setIcon(interface_icon(MANUAL_STAGE_ICONS[stage_id], theme.TOOL_3))
            button.setIconSize(QSize(15, 15))
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
        self._home_button.setIconSize(QSize(round(scaled.width() / scale), round(scaled.height() / scale)))
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
                lambda checked=False, selected_mode=mode: self._request_theme_mode(selected_mode, checked)
            )
            theme_group.addAction(action)
            self._theme_actions[mode] = action
        self._theme_action_group = theme_group

    def _request_theme_mode(self, mode: str, checked: bool) -> None:
        if checked:
            self.theme_mode_requested.emit(mode)

    def _toggle_runway_options(self) -> None:
        if self._runway_options_expanded:
            self._set_runway_options_expanded(False)
            return
        self._show_runway_menu()

    def _set_runway_options_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if self._runway_options_expanded == expanded:
            return
        self._runway_options_expanded = expanded
        self._runway_button.setText("Runway  ‹" if expanded else "Runway  ›")
        runway_workspace_active = self._automation_menu_active or (
            not self._home_menu_active and self._active_tool_id != LADDER_TOOL_SPEC.id
        )
        self._runway_button.setProperty("activeNavigation", expanded or runway_workspace_active)
        animation = self._runway_options_animation
        animation.stop()
        if expanded:
            start_width = self._runway_options.width() if self._runway_options.isVisible() else 0
            self._runway_options.show()
            target_width = self._runway_options.sizeHint().width()
            self._runway_options.setMaximumWidth(start_width)
            animation.setStartValue(start_width)
            animation.setEndValue(target_width)
        else:
            animation.setStartValue(self._runway_options.width())
            animation.setEndValue(0)
        animation.start()
        self._runway_button.setProperty("expanded", self._runway_options_expanded)
        self._runway_button.style().unpolish(self._runway_button)
        self._runway_button.style().polish(self._runway_button)
        self._runway_button.update()

    def _runway_options_animation_finished(self) -> None:
        if self._runway_options_expanded:
            self._runway_options.setMaximumWidth(16_777_215)
            self._snap_runway_mode_highlight()
            self._snap_primary_navigation_highlight()
            return
        self._runway_options.hide()
        self._runway_mode_highlight.hide()
        self._snap_primary_navigation_highlight()

    def _active_runway_mode_button(self):
        if self._automation_menu_active:
            return (
                self._automation_profiles_button
                if self._automated_workspace_page == "profiles"
                else self._automation_run_button
            )
        manual_active = self._active_tool_id in self._manual_stage_buttons or (
            self._stack.currentWidget() is self._main_menu
            and self._main_menu.view_stack.currentWidget() is self._main_menu.workspace_page
            and self._main_menu.pipeline_tabs.currentIndex() == 0
        )
        return self._runway_manual_button if manual_active else None

    def _runway_mode_highlight_target(self) -> QRect | None:
        button = self._active_runway_mode_button()
        if button is None or not button.isVisible():
            return None
        top_left = button.mapTo(self._runway_options, button.rect().topLeft())
        return QRect(top_left.x(), top_left.y(), button.width(), button.height())

    def _style_runway_mode_highlight(self) -> None:
        button = self._active_runway_mode_button()
        if button is self._automation_run_button:
            mode = "automated"
        elif button is self._automation_profiles_button:
            mode = "profiles"
        elif button is self._runway_manual_button:
            mode = "manual"
        else:
            mode = ""
        highlight = self._runway_mode_highlight
        if highlight.property("runwayMode") == mode:
            return
        highlight.setProperty("runwayMode", mode)
        highlight.style().unpolish(highlight)
        highlight.style().polish(highlight)

    def _snap_runway_mode_highlight(self) -> None:
        target = self._runway_mode_highlight_target()
        if target is None:
            self._runway_mode_highlight.hide()
            return
        self._style_runway_mode_highlight()
        self._runway_mode_highlight_animation.stop()
        self._runway_mode_highlight.setGeometry(target)
        self._runway_mode_highlight.show()
        self._runway_mode_highlight.lower()

    def _animate_runway_mode_highlight(self) -> None:
        target = self._runway_mode_highlight_target()
        highlight = self._runway_mode_highlight
        if target is None:
            highlight.hide()
            return
        self._style_runway_mode_highlight()
        animation = self._runway_mode_highlight_animation
        animation.stop()
        if highlight.isHidden() or not self.isVisible():
            highlight.setGeometry(target)
            highlight.show()
            highlight.lower()
            return
        animation.setStartValue(highlight.geometry())
        animation.setEndValue(target)
        highlight.show()
        highlight.lower()
        animation.start()

    def _set_manual_pipeline_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if self._manual_stage_expanded == expanded:
            if expanded and self._manual_stage_frame.isHidden():
                self._manual_stage_frame.show()
                self._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
                self._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
                self._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            elif expanded and self._manual_stage_animation.state() != QPropertyAnimation.State.Running:
                self._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
                self._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
                self._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            elif not expanded and self._manual_stage_animation.state() != QPropertyAnimation.State.Running:
                self._manual_stage_frame.hide()
                self._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT)
                self._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT)
            return

        self._manual_stage_expanded = expanded
        animation = self._manual_stage_animation
        toolbar_animation = self._toolbar_height_animation
        toolbar_max_animation = self._toolbar_max_height_animation
        animation.stop()
        toolbar_animation.stop()
        toolbar_max_animation.stop()
        if expanded:
            self._manual_stage_frame.show()
            self._manual_stage_frame.setMaximumHeight(0)
            animation.setStartValue(0)
            animation.setEndValue(WORKFLOW_ROW_HEIGHT)
            toolbar_animation.setStartValue(self._toolbar.height())
            toolbar_animation.setEndValue(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            toolbar_max_animation.setStartValue(self._toolbar.height())
            toolbar_max_animation.setEndValue(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
        else:
            animation.setStartValue(self._manual_stage_frame.height())
            animation.setEndValue(0)
            toolbar_animation.setStartValue(self._toolbar.height())
            toolbar_animation.setEndValue(APP_TOOLBAR_HEIGHT)
            toolbar_max_animation.setStartValue(self._toolbar.height())
            toolbar_max_animation.setEndValue(APP_TOOLBAR_HEIGHT)
        animation.start()
        toolbar_animation.start()
        toolbar_max_animation.start()

    def _manual_stage_target_geometry(self) -> QRect:
        return QRect(0, APP_TOOLBAR_HEIGHT, self._shell.width(), WORKFLOW_ROW_HEIGHT)

    def _position_manual_stage_rail(self) -> None:
        if self._manual_stage_animation.state() == QPropertyAnimation.State.Running:
            return
        self._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)

    def _manual_stage_animation_finished(self) -> None:
        if self._manual_stage_expanded:
            self._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
            self._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            self._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            self._snap_manual_stage_highlight()
            if not self._automation_menu_active and not self._home_menu_active:
                self._snap_primary_navigation_highlight()
            return
        self._manual_stage_frame.hide()
        self._manual_stage_highlight.hide()
        self._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT)
        self._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT)

    def _manual_stage_highlight_target(self) -> QRect | None:
        button = self._manual_stage_buttons.get(self._active_tool_id or "")
        if button is None or not button.isVisible():
            return None
        top_left = button.mapTo(self._manual_stage_frame, button.rect().bottomLeft())
        row_height = max(self._manual_stage_frame.height(), WORKFLOW_ROW_HEIGHT)
        return QRect(top_left.x() + 4, row_height - 4, max(8, button.width() - 8), 3)

    def _snap_manual_stage_highlight(self) -> None:
        target = self._manual_stage_highlight_target()
        if target is None:
            self._manual_stage_highlight.hide()
            return
        self._manual_stage_highlight_animation.stop()
        self._manual_stage_highlight.setGeometry(target)
        self._manual_stage_highlight.show()
        self._manual_stage_highlight.raise_()

    def _animate_manual_stage_highlight(self) -> None:
        target = self._manual_stage_highlight_target()
        highlight = self._manual_stage_highlight
        if target is None:
            highlight.hide()
            return
        animation = self._manual_stage_highlight_animation
        animation.stop()
        if highlight.isHidden() or not self.isVisible():
            highlight.setGeometry(target)
            highlight.show()
            highlight.raise_()
            return
        animation.setStartValue(highlight.geometry())
        animation.setEndValue(target)
        highlight.show()
        highlight.raise_()
        animation.start()

    def _manual_navigation_clicked(self) -> None:
        manual_active = (
            not self._home_menu_active
            and not self._automation_menu_active
            and self._active_tool_id != LADDER_TOOL_SPEC.id
        )
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
        self._set_runway_options_expanded(False)
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
        self._set_runway_options_expanded(True)
        self._set_manual_pipeline_expanded(True)
        self._main_menu.show_manual()
        self.setWindowTitle("DLC Gait Assembler - Manual pipeline")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_runway_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._active_tool = None
        self._active_tool_id = None
        self._home_menu_active = False
        self._automation_menu_active = False
        self._set_runway_options_expanded(True)
        self._set_manual_pipeline_expanded(False)
        self._main_menu.show_runway_home()
        self.setWindowTitle("DLC Gait Assembler - Runway")
        self._refresh_stage_navigation()
        self._show_widget(self._main_menu)

    def _show_automated_pipeline(self) -> None:
        if not self._can_leave_active_tool():
            return
        self._active_tool = None
        self._active_tool_id = None
        self._home_menu_active = False
        self._automation_menu_active = True
        self._set_runway_options_expanded(True)
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
        self._set_runway_options_expanded(True)
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
        self._set_runway_options_expanded(True)
        self._set_manual_pipeline_expanded(not self._automation_menu_active)
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
            if isinstance(tool, LadderAnalysisWidget):
                tool.back_requested.connect(self._show_home_menu)
            self._tool_widgets[tool_id] = tool
            self._stack.addWidget(tool)
        self._apply_tool_surface_depth(tool)

        is_manual_tool = tool_id in self._manual_stage_buttons
        self._active_tool = tool
        self._active_tool_id = tool_id
        self._home_menu_active = False
        self._automation_menu_active = False
        self._set_runway_options_expanded(is_manual_tool)
        self._set_manual_pipeline_expanded(is_manual_tool)
        self.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self._refresh_stage_navigation()
        self._show_widget(tool)
        if is_manual_tool:
            QTimer.singleShot(240, lambda expected_tool_id=tool_id: self._enforce_manual_row(expected_tool_id))

    def _enforce_manual_row(self, expected_tool_id: str) -> None:
        """Keep manual navigation visible after a newly mounted workspace settles."""
        if self._active_tool_id != expected_tool_id or expected_tool_id not in self._manual_stage_buttons:
            return
        self._manual_stage_animation.stop()
        self._toolbar_height_animation.stop()
        self._toolbar_max_height_animation.stop()
        self._manual_stage_expanded = True
        self._manual_stage_frame.show()
        self._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
        self._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
        self._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
        self._manual_stage_frame.updateGeometry()
        self._toolbar.updateGeometry()
        QTimer.singleShot(0, self._snap_manual_stage_highlight)

    def _apply_tool_surface_depth(self, tool: QWidget) -> None:
        """Use inexpensive tonal elevation on large workspace surfaces."""
        surface_names = {
            "WorkspaceHeader",
            "WorkspaceSidebar",
            "WorkspaceCanvas",
            "OperationsBar",
            "TerminalToolbar",
            "TerminalFrame",
        }
        surfaces = [
            child
            for child in tool.findChildren(QWidget)
            if child.objectName() in surface_names
        ]
        if isinstance(tool, KneeCorrectionWidget):
            surfaces.extend(tool.findChildren(QGroupBox))

        seen: set[int] = set()
        for surface in surfaces:
            identity = id(surface)
            if identity in seen:
                continue
            seen.add(identity)
            newly_elevated = not bool(surface.property("elevatedWorkspaceSurface"))
            surface.setProperty("elevatedWorkspaceSurface", True)
            # QGraphicsDropShadowEffect rasterizes the complete widget subtree on
            # every repaint. These surfaces can contain tables, previews, and
            # hundreds of controls, so their palette contrast provides depth far
            # more cheaply than a live blur.
            if surface.graphicsEffect() is not None:
                surface.setGraphicsEffect(None)
            if newly_elevated:
                surface.style().unpolish(surface)
                surface.style().polish(surface)

    def _refresh_stage_navigation(self) -> None:
        self._home_button.setProperty("activeNavigation", self._home_menu_active)
        runway_active = self._automation_menu_active or (
            not self._home_menu_active and self._active_tool_id != LADDER_TOOL_SPEC.id
        )
        self._runway_button.setProperty("activeNavigation", runway_active)
        self._ladder_button.setProperty("activeNavigation", self._active_tool_id == LADDER_TOOL_SPEC.id)
        self._automation_run_button.setProperty(
            "activeNavigation",
            self._automation_menu_active and self._automated_workspace_page == "run",
        )
        self._automation_profiles_button.setProperty(
            "activeNavigation",
            self._automation_menu_active and self._automated_workspace_page == "profiles",
        )
        self._runway_manual_button.setProperty(
            "activeNavigation",
            self._active_runway_mode_button() is self._runway_manual_button,
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
            self._runway_button,
            self._ladder_button,
            self._automation_run_button,
            self._automation_profiles_button,
            self._runway_manual_button,
            self._manual_tools_button,
        ):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        if self._manual_stage_expanded:
            self._animate_manual_stage_highlight()
        if self._runway_options_expanded:
            self._animate_runway_mode_highlight()
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
        self._primary_navigation_highlight.setGeometry(self._primary_navigation_target_geometry(target_button))
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
        if self._active_tool_id == LADDER_TOOL_SPEC.id:
            return self._ladder_button, "ladder"
        return None, ""

    def _tool_spec(self, tool_id: str) -> ToolSpec:
        for spec in (*TOOL_SPECS, LADDER_TOOL_SPEC):
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
    runway_requested = Signal()
    automated_requested = Signal()
    manual_requested = Signal()

    def __init__(self, tools: list[ToolSpec]):
        super().__init__()
        self.setObjectName("MainMenuWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._tools = tools
        self._entrance_has_run = False
        self._entrance_animation: QParallelAnimationGroup | None = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(0)

        content = QWidget()
        content.setObjectName("MenuContent")
        content.setMaximumWidth(1540)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        view_stack = QStackedWidget()
        view_stack.setObjectName("MainMenuViewStack")

        home_page = QWidget()
        home_page.setObjectName("PipelineHomePage")
        home_layout = QVBoxLayout(home_page)
        home_layout.setContentsMargins(22, 18, 22, 18)
        home_layout.setSpacing(6)
        home_layout.addStretch(1)

        home_title = QLabel("Choose an analysis workspace")
        home_title.setObjectName("HomeTitle")
        home_layout.addWidget(home_title)
        self._home_title = home_title

        choices = QHBoxLayout()
        choices.setSpacing(16)
        choices.setAlignment(Qt.AlignCenter)
        runway_card, runway_button = self._runway_choice_card()
        runway_button.clicked.connect(self.runway_requested.emit)
        choices.addWidget(runway_card, 1)
        ladder_card, ladder_button = self._ladder_choice_card()
        ladder_button.clicked.connect(lambda: self.tool_requested.emit(LADDER_TOOL_SPEC.id))
        choices.addWidget(ladder_card, 1)
        home_layout.addLayout(choices)
        self._runway_choice_card_widget = runway_card
        self._ladder_choice_card_widget = ladder_card
        self.ladder_choice_button = ladder_button

        home_layout.addStretch(1)
        self.runway_choice_button = runway_button
        self.manual_choice_button = runway_button
        self.home_page = home_page
        view_stack.addWidget(home_page)

        runway_home_page = QWidget()
        runway_home_page.setObjectName("RunwayHomePage")
        runway_home_layout = QVBoxLayout(runway_home_page)
        runway_home_layout.setContentsMargins(22, 18, 22, 18)
        runway_home_layout.setSpacing(8)
        runway_home_layout.addStretch(1)
        runway_title = QLabel("Runway workflow")
        runway_title.setObjectName("HomeTitle")
        runway_home_layout.addWidget(runway_title)

        runway_choices = QHBoxLayout()
        runway_choices.setSpacing(10)
        runway_choices.setAlignment(Qt.AlignTop)
        manual_card, manual_button = self._manual_choice_card()
        manual_button.clicked.connect(self.manual_requested.emit)
        runway_choices.addWidget(manual_card, 9)

        handoff = QFrame()
        handoff.setObjectName("PipelineHandoff")
        handoff_layout = QVBoxLayout(handoff)
        handoff_layout.setContentsMargins(4, 0, 4, 0)
        handoff_layout.setSpacing(4)
        handoff_layout.addStretch(1)
        handoff_icon = QLabel()
        handoff_icon.setObjectName("PipelineHandoffIcon")
        handoff_icon.setAlignment(Qt.AlignCenter)
        handoff_icon.setPixmap(interface_icon("gear", theme.TOOL_1, size=34).pixmap(34, 34))
        handoff_layout.addWidget(handoff_icon)
        handoff_title = QLabel("Settings saved")
        handoff_title.setObjectName("PipelineHandoffTitle")
        handoff_title.setAlignment(Qt.AlignCenter)
        handoff_title.setWordWrap(True)
        handoff_layout.addWidget(handoff_title)
        handoff_arrow = QLabel("→")
        handoff_arrow.setObjectName("PipelineHandoffArrow")
        handoff_arrow.setAlignment(Qt.AlignCenter)
        handoff_layout.addWidget(handoff_arrow)
        handoff_layout.addStretch(1)
        runway_choices.addWidget(handoff, 1)

        automated_card, automated_button = self._automated_choice_card()
        automated_button.clicked.connect(self.automated_requested.emit)
        runway_choices.addWidget(automated_card, 4)
        runway_home_layout.addLayout(runway_choices)
        runway_home_layout.addStretch(1)
        self._manual_choice_card_widget = manual_card
        self._pipeline_handoff_widget = handoff
        self._automated_choice_card_widget = automated_card
        self.automated_choice_button = automated_button
        self.runway_manual_choice_button = manual_button
        self.runway_home_page = runway_home_page
        view_stack.addWidget(runway_home_page)

        workspace_page = QWidget()
        workspace_page.setObjectName("PipelineWorkspacePage")
        workspace_layout = QVBoxLayout(workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(10)

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
        manual_layout.setContentsMargins(0, 4, 0, 0)
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
    def _choice_header(role: str, icon_name: str, title: str) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(10)
        graphic = QLabel()
        graphic.setObjectName("PipelineChoiceGraphic")
        graphic.setProperty("pipelineRole", role)
        graphic.setProperty("iconName", icon_name)
        graphic.setAlignment(Qt.AlignCenter)
        graphic.setFixedSize(48, 48)
        header.addWidget(graphic)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("PipelineChoiceTitle")
        copy.addWidget(title_label)
        header.addLayout(copy, 1)
        return header

    def _automated_choice_card(self) -> tuple[QFrame, QPushButton]:
        card = QFrame()
        card.setObjectName("PipelineChoiceCard")
        card.setProperty("pipelineRole", "automated")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addLayout(self._choice_header("automated", "play", "2. Automated runs"))
        flow_widget = QWidget()
        flow_widget.setObjectName("AutomatedFlow")
        flow = QHBoxLayout(flow_widget)
        flow.setContentsMargins(0, 0, 0, 0)
        flow.setSpacing(4)
        automated_steps = (
            ("automation-database", "Manage Profiles", "Save reusable settings."),
            ("automation-gear", "Automate Pipeline", "Process every video."),
            ("automation-report", "Check Results", "Review consistent outputs."),
        )
        for index, (asset_name, title_text, description_text) in enumerate(automated_steps):
            step = QWidget()
            step.setFixedHeight(198)
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(0, 0, 0, 0)
            step_layout.setSpacing(3)
            icon = QLabel()
            icon.setObjectName("AutomationFlowIcon")
            icon.setPixmap(_menu_asset_pixmap(asset_name, 58))
            icon.setAlignment(Qt.AlignCenter)
            icon.setFixedHeight(66)
            step_layout.addWidget(icon)
            title = QLabel(title_text)
            title.setObjectName("AutomationFlowTitle")
            title.setAlignment(Qt.AlignCenter)
            title.setWordWrap(True)
            title.setFixedHeight(40)
            step_layout.addWidget(title)
            description = QLabel(description_text)
            description.setObjectName("AutomationFlowDescription")
            description.setAlignment(Qt.AlignCenter)
            description.setWordWrap(True)
            description.setFixedHeight(48)
            step_layout.addWidget(description)
            output_spacer = QLabel()
            output_spacer.setObjectName("AutomationFlowSpacer")
            output_spacer.setFixedHeight(18)
            step_layout.addWidget(output_spacer)
            step_layout.addStretch(1)
            flow.addWidget(step, 1, Qt.AlignTop)
            if index < 2:
                connector = QLabel("→")
                connector.setObjectName("AutomationConnector")
                flow.addWidget(connector)
        layout.addWidget(flow_widget)
        layout.addStretch(1)
        button = QPushButton("Open automated pipeline")
        button.setObjectName("PipelineChoiceButton")
        button.setProperty("pipelineRole", "automated")
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip("Select a profile and process a batch of videos.")
        layout.addWidget(button)
        return card, button

    def _manual_choice_card(self) -> tuple[QFrame, QPushButton]:
        card = QFrame()
        card.setObjectName("PipelineChoiceCard")
        card.setProperty("pipelineRole", "manual")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addLayout(self._choice_header("manual", "sliders", "1. Manual setup"))
        stages = QHBoxLayout()
        stages.setSpacing(5)
        files = (".json", ".mp4", ".h5 / .csv", ".csv", ".csv", ".pkl / .png")
        stage_names = (
            "Calibration",
            "Video Processing",
            "DeepLabCut",
            "Knee Processing",
            "Gait Analysis",
            "PCA / Random Forest",
        )
        descriptions = (
            "Calibrate cameras and set 3D space.",
            "Crop, filter, and prepare videos.",
            "Track body keypoints with DLC.",
            "Compute knee positions and angles.",
            "Extract gait events and metrics.",
            "Perform PCA and classification.",
        )
        stage_assets = (
            "stage-calibration",
            "stage-video",
            "stage-deeplabcut",
            "stage-knee",
            "stage-gait",
            "stage-analysis",
        )
        for index, _spec in enumerate(self._tools):
            stage = QFrame()
            stage.setObjectName("ManualMiniStage")
            stage.setFixedHeight(198)
            stage_layout = QVBoxLayout(stage)
            stage_layout.setContentsMargins(0, 0, 0, 0)
            stage_layout.setSpacing(3)
            icon = QLabel()
            icon.setObjectName("ManualMiniStageIcon")
            icon.setAlignment(Qt.AlignCenter)
            icon.setPixmap(_menu_asset_pixmap(stage_assets[index], 58))
            icon.setFixedHeight(66)
            stage_layout.addWidget(icon)
            title = QLabel(f"{index + 1}. {stage_names[index]}")
            title.setObjectName("ManualMiniStageTitle")
            title.setAlignment(Qt.AlignCenter)
            title.setWordWrap(True)
            title.setFixedHeight(40)
            stage_layout.addWidget(title)
            description = QLabel(descriptions[index])
            description.setObjectName("ManualMiniStageDescription")
            description.setAlignment(Qt.AlignCenter)
            description.setWordWrap(True)
            description.setFixedHeight(48)
            stage_layout.addWidget(description)
            file_label = QLabel(files[index])
            file_label.setObjectName("ManualMiniStageFile")
            file_label.setAlignment(Qt.AlignCenter)
            stage_layout.addWidget(file_label)
            stages.addWidget(stage, 1, Qt.AlignTop)
            if index < len(self._tools) - 1:
                arrow = QLabel("→")
                arrow.setObjectName("ManualFlowArrow")
                arrow.setAlignment(Qt.AlignCenter)
                stages.addWidget(arrow)
        layout.addLayout(stages)
        layout.addStretch(1)
        button = QPushButton("Open manual pipeline")
        button.setObjectName("PipelineChoiceButton")
        button.setProperty("pipelineRole", "manual")
        button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(button)
        return card, button

    def _runway_choice_card(self) -> tuple[QFrame, QPushButton]:
        card = QFrame()
        card.setObjectName("RunwayChoiceCard")
        card.setProperty("pipelineRole", "runway")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        illustration = MenuIllustrationLabel(
            "runway-mouse",
            "Laboratory mouse walking through a runway enclosure",
            card,
        )
        illustration.setProperty("pipelineRole", "runway")
        layout.addWidget(illustration)
        layout.addLayout(self._choice_header("runway", "runway", "Runway analysis"))
        description = QLabel(
            "Use the full runway workflow with automated runs, reusable profiles, "
            "or the step-by-step manual pipeline."
        )
        description.setObjectName("WorkspaceChoiceDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addStretch(1)

        button = QPushButton("Open Runway")
        button.setObjectName("PipelineChoiceButton")
        button.setProperty("pipelineRole", "manual")
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip("Open Automated, Profiles, and Manual runway workflows.")
        layout.addWidget(button)
        self.runway_choice_illustration = illustration
        return card, button

    def _ladder_choice_card(self) -> tuple[QFrame, QPushButton]:
        card = QFrame()
        card.setObjectName("LadderChoiceCard")
        card.setProperty("pipelineRole", "ladder")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        illustration = MenuIllustrationLabel(
            "ladder-mouse",
            "Laboratory mouse walking across a horizontal ladder",
            card,
        )
        illustration.setProperty("pipelineRole", "ladder")
        layout.addWidget(illustration)
        layout.addLayout(self._choice_header("ladder", "ladder", "Ladder analysis"))
        description = QLabel("Detect paw placements, review slips or falls, and export ladder-rung events.")
        description.setObjectName("WorkspaceChoiceDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addStretch(1)

        button = QPushButton("Open ladder analysis")
        button.setObjectName("PipelineChoiceButton")
        button.setProperty("pipelineRole", "ladder")
        button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(button)
        self.ladder_choice_illustration = illustration
        return card, button

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._entrance_has_run:
            QTimer.singleShot(0, self._start_home_entrance)

    def _start_home_entrance(self) -> None:
        if self._entrance_has_run or not self.isVisible():
            return
        self._entrance_has_run = True
        group = QParallelAnimationGroup(self)
        targets = (
            (self._home_title, 0, False),
            (self._runway_choice_card_widget, 80, True),
            (self._ladder_choice_card_widget, 170, True),
        )
        for widget, delay, add_depth in targets:
            end_position = widget.pos()
            start_position = end_position + QPoint(0, 14)
            widget.move(start_position)
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            sequence = QSequentialAnimationGroup(group)
            if delay:
                sequence.addAnimation(QPauseAnimation(delay, sequence))
            reveal = QParallelAnimationGroup(sequence)
            opacity_animation = QPropertyAnimation(effect, b"opacity", reveal)
            opacity_animation.setDuration(300)
            opacity_animation.setStartValue(0.0)
            opacity_animation.setEndValue(1.0)
            opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            reveal.addAnimation(opacity_animation)
            rise_animation = QPropertyAnimation(widget, b"pos", reveal)
            rise_animation.setDuration(340)
            rise_animation.setStartValue(start_position)
            rise_animation.setEndValue(end_position)
            rise_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            reveal.addAnimation(rise_animation)
            reveal.finished.connect(
                lambda target=widget, depth=add_depth, final=end_position: self._finish_entrance_target(
                    target, depth, final
                )
            )
            sequence.addAnimation(reveal)
            group.addAnimation(sequence)
        self._entrance_animation = group
        group.start()

    def _finish_entrance_target(self, widget: QWidget, add_depth: bool, final_position: QPoint) -> None:
        widget.move(final_position)
        widget.setGraphicsEffect(None)
        if add_depth:
            self._apply_card_depth(widget)

    @staticmethod
    def _apply_card_depth(widget: QWidget) -> None:
        current_effect = widget.graphicsEffect()
        if isinstance(current_effect, QGraphicsDropShadowEffect):
            shadow = current_effect
        elif current_effect is not None:
            # Do not replace the temporary opacity effect used by entrance motion.
            return
        else:
            shadow = QGraphicsDropShadowEffect(widget)
            widget.setGraphicsEffect(shadow)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 120 if theme.IS_DARK else 48))

    def show_home(self) -> None:
        self.view_stack.setCurrentWidget(self.home_page)
        QTimer.singleShot(0, self._apply_home_card_depth)

    def show_runway_home(self) -> None:
        self.view_stack.setCurrentWidget(self.runway_home_page)
        QTimer.singleShot(0, self._apply_runway_home_card_depth)

    def show_manual(self) -> None:
        self.pipeline_tabs.setCurrentIndex(0)
        self.view_stack.setCurrentWidget(self.workspace_page)
        QTimer.singleShot(0, self._apply_workflow_card_depth)

    def show_automated(self) -> None:
        self.pipeline_tabs.setCurrentIndex(1)
        self.view_stack.setCurrentWidget(self.workspace_page)

    def _apply_home_card_depth(self) -> None:
        for card in (self._runway_choice_card_widget, self._ladder_choice_card_widget):
            self._apply_card_depth(card)

    def _apply_runway_home_card_depth(self) -> None:
        for card in (self._manual_choice_card_widget, self._automated_choice_card_widget):
            self._apply_card_depth(card)

    def _apply_workflow_card_depth(self) -> None:
        for card in self.workspace_page.findChildren(QFrame, "WorkflowStep"):
            self._apply_card_depth(card)

    def _update_pipeline_heading(self, index: int) -> None:
        self.section_title.setVisible(index == 0)
        if index == 0:
            self.section_title.setText("Manual pipeline")

    def _workflow_list(self, tools: list[ToolSpec], connect_tools: bool) -> QFrame:
        workflow_list = QFrame()
        workflow_list.setObjectName("WorkflowList")
        workflow_list.setFixedHeight(224)
        list_layout = QGridLayout(workflow_list)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setHorizontalSpacing(10)
        list_layout.setVerticalSpacing(10)

        for index, spec in enumerate(tools):
            step = WorkflowStep(index + 1, spec)
            if connect_tools and spec.enabled:
                step.clicked.connect(self.tool_requested.emit)
            list_layout.addWidget(step, index // 3, index % 3)
            list_layout.setColumnStretch(index % 3, 1)
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
                background-image: url({theme.BACKGROUND_TEXTURE});
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
                background-image: url({theme.BACKGROUND_TEXTURE});
                color: {theme.TEXT};
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QStackedWidget#MainMenuViewStack,
            QWidget#PipelineHomePage,
            QWidget#RunwayHomePage,
            QWidget#PipelineWorkspacePage {
                background: transparent;
                border: 0;
            }
            QLabel#HomeTitle {
                color: {theme.TEXT};
                font-size: 31px;
                font-weight: 750;
                padding-bottom: 2px;
            }
            QFrame#PipelineChoiceCard {
                background: {theme.SURFACE};
                border: 0;
                border-radius: 8px;
                min-height: 390px;
                max-height: 420px;
            }
            QFrame#PipelineChoiceCard[pipelineRole="automated"] {
                background: {theme.SURFACE};
            }
            QFrame#PipelineChoiceCard[pipelineRole="manual"] {
                background: {theme.SURFACE};
            }
            QFrame#RunwayChoiceCard,
            QFrame#LadderChoiceCard {
                background: {theme.SURFACE};
                border: 0;
                border-radius: 8px;
                min-height: 400px;
                max-height: 455px;
            }
            QFrame#LadderChoiceCard {
                background: {theme.SURFACE};
            }
            QLabel#WorkspaceChoiceIllustration {
                background: transparent;
                border: 0;
            }
            QLabel#PipelineChoiceGraphic {
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 10px;
            }
            QLabel#AutomationFlowIcon {
                background: transparent;
                border: 0;
                min-height: 50px;
            }
            QLabel#AutomationFlowTitle {
                color: {theme.TEXT};
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#AutomationFlowDescription {
                color: {theme.CONNECTOR};
                font-size: 11px;
            }
            QLabel#AutomationConnector {
                color: {theme.TOOL_1};
                font-weight: 700;
            }
            QLabel#AutomatedFlowTitle {
                border-top: 1px solid {theme.BORDER};
                color: {theme.TOOL_1};
                font-size: 13px;
                font-weight: 700;
                padding-top: 7px;
            }
            QWidget#AutomatedFlow {
                min-height: 198px;
                max-height: 204px;
            }
            QLabel#ManualFlowTitle {
                border-top: 1px solid {theme.BORDER};
                color: {theme.TOOL_3};
                font-size: 13px;
                font-weight: 700;
                padding-top: 7px;
            }
            QFrame#ManualMiniStage {
                background: transparent;
                border: 0;
                min-width: 70px;
                min-height: 198px;
                max-height: 204px;
            }
            QLabel#ManualMiniStageIcon {
                min-height: 66px;
                max-height: 66px;
            }
            QLabel#ManualMiniStageTitle {
                color: {theme.TEXT};
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#ManualMiniStageDescription {
                color: {theme.CONNECTOR};
                font-size: 11px;
            }
            QLabel#ManualMiniStageFile {
                background: {theme.SOFT};
                border-radius: 3px;
                color: {theme.TOOL_3};
                font-size: 9px;
                font-weight: 650;
                padding: 2px 3px;
            }
            QLabel#ManualFlowArrow {
                color: {theme.TOOL_3};
                font-size: 15px;
                font-weight: 700;
            }
            QFrame#PipelineBenefits {
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 5px;
            }
            QLabel#BenefitCheck {
                border: 1px solid {theme.BORDER};
                border-radius: 7px;
                color: {theme.CONNECTOR};
                font-size: 9px;
                font-weight: 700;
                min-width: 14px;
                max-width: 14px;
                min-height: 14px;
                max-height: 14px;
            }
            QLabel#BenefitCheck[pipelineRole="automated"] {
                color: {theme.TOOL_1};
            }
            QLabel#BenefitCheck[pipelineRole="manual"] {
                color: {theme.TOOL_3};
            }
            QLabel#BenefitText {
                color: {theme.TEXT};
                font-size: 10px;
            }
            QFrame#PipelineHandoff {
                background: transparent;
                border: 0;
                min-width: 86px;
                max-width: 110px;
            }
            QLabel#PipelineHandoffIcon {
                background: transparent;
                border: 0;
                min-height: 46px;
                max-height: 46px;
            }
            QLabel#PipelineHandoffTitle {
                color: {theme.TEXT};
                font-size: 10px;
                font-weight: 700;
            }
            QLabel#PipelineHandoffDetail {
                color: {theme.CONNECTOR};
                font-size: 9px;
            }
            QLabel#PipelineHandoffArrow {
                color: {theme.TOOL_1};
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#PipelineChoiceTitle {
                color: {theme.TEXT};
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#PipelineChoiceDescription {
                color: {theme.CONNECTOR};
                font-size: 13px;
            }
            QLabel#WorkspaceChoiceDescription {
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
            QPushButton#PipelineChoiceButton[pipelineRole="ladder"] {
                border-color: {theme.TOOL_2};
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
                background: transparent;
                border: 0;
            }
            QFrame#WorkflowStep {
                background: {theme.SURFACE};
                border: 0;
                border-radius: 8px;
            }
            QFrame#WorkflowStep[enabledStep="true"]:hover {
                background: {theme.PANEL};
            }
            QFrame#WorkflowStep[enabledStep="false"] {
                background: {theme.BACKGROUND};
            }
            QLabel#StepIndex {
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 12px;
                color: {theme.TOOL_3};
                font-size: 11px;
                font-weight: 750;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
            }
            QLabel#StepGraphic {
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 9px;
                min-width: 40px;
                max-width: 40px;
                min-height: 40px;
                max-height: 40px;
            }
            QLabel#StepIndex[enabledStep="false"] {
                color: {theme.BORDER};
            }
            QLabel#StepTitle {
                color: {theme.TEXT};
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#StepTitle[enabledStep="false"] {
                color: {theme.CONNECTOR};
            }
            QPushButton#OpenToolButton {
                background: transparent;
                border: 0;
                color: {theme.TOOL_3};
                font-weight: 700;
                min-width: 54px;
                padding: 4px 0;
            }
            QPushButton#OpenToolButton:hover {
                background: transparent;
                color: {theme.TEXT};
            }
            QPushButton#OpenToolButton:disabled {
                background: {theme.BACKGROUND};
                color: {theme.CONNECTOR};
            }
            """
            )
        )
        if hasattr(self, "runway_choice_button"):
            self.runway_choice_button.setIcon(_navigation_icon("runway", theme.TOOL_1))
            self.runway_choice_button.setIconSize(QSize(18, 18))
            self.ladder_choice_button.setIcon(interface_icon("ladder", theme.TOOL_2))
            self.ladder_choice_button.setIconSize(QSize(18, 18))
            self.automated_choice_button.setIcon(_navigation_icon("automated", theme.TOOL_1))
            self.automated_choice_button.setIconSize(QSize(18, 18))
            self.runway_manual_choice_button.setIcon(_navigation_icon("manual", theme.TOOL_3))
            self.runway_manual_choice_button.setIconSize(QSize(18, 18))
        for step in self.findChildren(WorkflowStep):
            step.apply_theme()
        for graphic in self.findChildren(QLabel, "PipelineChoiceGraphic"):
            role = graphic.property("pipelineRole")
            color = theme.TOOL_1 if role == "automated" else theme.TOOL_2 if role == "ladder" else theme.TOOL_3
            if role == "runway":
                graphic.setPixmap(_navigation_icon("runway", theme.TOOL_1).pixmap(30, 30))
            else:
                graphic.setPixmap(interface_icon(graphic.property("iconName"), color, size=30).pixmap(30, 30))
        if self._entrance_has_run and (
            self._entrance_animation is None
            or self._entrance_animation.state() != QParallelAnimationGroup.State.Running
        ):
            self._apply_card_depth(self._runway_choice_card_widget)
            self._apply_card_depth(self._ladder_choice_card_widget)
            self._apply_card_depth(self._manual_choice_card_widget)
            self._apply_card_depth(self._automated_choice_card_widget)


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
        self.setFixedHeight(107)
        if spec.enabled:
            self.setCursor(Qt.PointingHandCursor)
            if spec.description:
                self.setToolTip(spec.description)
        else:
            self.setToolTip("Not available yet.")
        self._build_ui(index, spec)

    def _build_ui(self, index: int, spec: ToolSpec) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(8)

        heading = QHBoxLayout()
        heading.setSpacing(10)

        self.graphic = QLabel()
        self.graphic.setObjectName("StepGraphic")
        self.graphic.setAlignment(Qt.AlignCenter)
        self.graphic.setFixedSize(40, 40)
        self.graphic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        heading.addWidget(self.graphic)

        title = QLabel(spec.label)
        title.setObjectName("StepTitle")
        title.setProperty("enabledStep", spec.enabled)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        heading.addWidget(title, 1)
        root.addLayout(heading)

        root.addStretch(1)

        open_button = QPushButton("Open" if spec.enabled else "Unavailable")
        open_button.setObjectName("OpenToolButton")
        open_button.setEnabled(spec.enabled)
        if spec.enabled:
            open_button.clicked.connect(lambda: self.clicked.emit(spec.id))
        root.addWidget(open_button, 0, Qt.AlignRight)
        self.apply_theme()

    def apply_theme(self) -> None:
        color = theme.TOOL_3 if self._spec.enabled else theme.BORDER
        self.graphic.setPixmap(interface_icon(MANUAL_STAGE_ICONS[self._spec.id], color, size=26).pixmap(26, 26))

    def mouseReleaseEvent(self, event) -> None:
        if self._spec.enabled and event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._spec.id)
            event.accept()
            return

        super().mouseReleaseEvent(event)
