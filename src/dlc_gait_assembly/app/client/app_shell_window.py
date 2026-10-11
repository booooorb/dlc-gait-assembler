"""Own the main window, content host, theme propagation, and page cleanup."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QWidget

from dlc_gait_assembly.app.business.app_navigation_routes import AppNavigationState
from dlc_gait_assembly.app.client.app_branding_widgets import PartnerLogoLabel
from dlc_gait_assembly.app.client.app_credits_menu import AppCreditsMenu
from dlc_gait_assembly.app.client.app_header_navigation import AppHeaderNavigation
from dlc_gait_assembly.app.client.app_navigation_animations import AppNavigationAnimations
from dlc_gait_assembly.app.client.app_route_controller import AppRouteController
from dlc_gait_assembly.app.client.app_shell_styles import (
    DEFAULT_WINDOW_SIZE,
    MINIMUM_WINDOW_SIZE,
    WINDOW_SCREEN_MARGIN,
    AppShellStyle,
)
from dlc_gait_assembly.shared.client.qt_page_stack import CurrentPageStackedWidget


class MainWindow(QMainWindow):
    theme_mode_requested = Signal(str)

    def __init__(
        self,
        initial_tool_id: str | None = None,
        initial_theme_mode: str = "light",
        *,
        tool_specs,
        ladder_spec,
        menu_factory,
    ):
        super().__init__()
        self.navigation = AppNavigationState()
        self.header = AppHeaderNavigation(self)
        self.credits = AppCreditsMenu(self)
        self.styling = AppShellStyle(self)
        self.routes = AppRouteController(self)
        self.animations = AppNavigationAnimations(self)
        self._tool_specs = tool_specs
        self._ladder_spec = ladder_spec
        self._menu_factory = menu_factory
        self.setWindowTitle("DLC Gait Assembler")
        self.setMinimumSize(MINIMUM_WINDOW_SIZE)
        self.resize(self._screen_aware_initial_size())
        self._active_tool: QWidget | None = None
        self.navigation.tool_id: str | None = None
        self.navigation.home_active = True
        self.navigation.automatic_active = False
        self.navigation.automatic_page = "run"
        self._tool_widgets: dict[str, QWidget] = {}
        self._stack = CurrentPageStackedWidget()
        self._main_menu = self._menu_factory(self._tool_specs)
        self._main_menu.tool_requested.connect(self.routes._open_tool)
        self._main_menu.runway_requested.connect(self.routes._show_runway_menu)
        self._main_menu.automated_requested.connect(self.routes._show_automated_pipeline)
        self._main_menu.profiles_requested.connect(self.routes._show_automated_profiles)
        self._main_menu.manual_requested.connect(self.routes._show_main_menu)
        self._main_menu.pipeline_tabs.currentChanged.connect(self.routes._pipeline_tab_changed)
        self._main_menu.automated_profiles.workspace_changed.connect(self.routes._automated_workspace_changed)
        self._main_menu.automated_profiles.manual_tool_requested.connect(self.routes._open_tool)
        self._stack.addWidget(self._main_menu)
        self.header._build_shell(initial_theme_mode)
        if initial_tool_id is None:
            self.routes._show_home_menu()
        else:
            self.routes._open_tool(initial_tool_id)

    def closeEvent(self, event):
        for tool in self._tool_widgets.values():
            if not tool.can_close(self):
                event.ignore()
                return
        self._main_menu.automated_profiles.close()
        self.routes._release_all_tools()
        super().closeEvent(event)

    def apply_theme(self) -> None:
        self.styling._apply_shell_style()
        for logo in self.findChildren(PartnerLogoLabel):
            logo.apply_theme()
        self._main_menu._apply_style()
        for tool in self._tool_widgets.values():
            tool.apply_theme()
            self.styling._apply_tool_surface_depth(tool)
        self.routes._refresh_stage_navigation()
        self.update()

    def set_theme_mode(self, mode: str) -> None:
        action = self._theme_actions.get(mode)
        if action is not None:
            action.setChecked(True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "_primary_navigation_highlight"):
            self.animations._snap_primary_navigation_highlight()
        if getattr(self, "_manual_stage_expanded", False):
            self.animations._snap_manual_stage_highlight()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "_manual_stage_expanded", False):
            self.animations._snap_manual_stage_highlight()
        if hasattr(self, "_settings_button"):
            style = Qt.ToolButtonIconOnly if self.width() < 1240 else Qt.ToolButtonTextBesideIcon
            self._settings_button.setToolButtonStyle(style)
            self._credits_button.setToolButtonStyle(style)
        if hasattr(self, "_runway_mode_highlight"):
            QTimer.singleShot(0, self.animations._snap_runway_mode_highlight)

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            if watched in (
                self._runway_options,
                self._automation_run_button,
                self._automation_profiles_button,
                self._runway_manual_button,
            ):
                QTimer.singleShot(0, self.animations._settle_runway_highlight)
        return super().eventFilter(watched, event)

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
            max(MINIMUM_WINDOW_SIZE.width(), min(DEFAULT_WINDOW_SIZE.width(), usable_width)),
            max(MINIMUM_WINDOW_SIZE.height(), min(DEFAULT_WINDOW_SIZE.height(), usable_height)),
        )
