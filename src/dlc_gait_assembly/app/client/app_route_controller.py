"""Select application pages and enforce their public leave and resource-release contracts."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QWidget

from dlc_gait_assembly.app.business.app_navigation_routes import AppRoute
from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
from dlc_gait_assembly.app.client.app_shell_styles import APP_TOOLBAR_HEIGHT, WORKFLOW_ROW_HEIGHT


class AppRouteController:
    """AppRouteController operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

    def _show_home_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        menu = self.view._main_menu
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = True
        self.view.navigation.automatic_active = False
        self.view.animations._set_manual_pipeline_expanded(False)
        menu.view_stack.setCurrentWidget(menu.home_page)
        self.view.setWindowTitle("DLC Gait Assembler")
        self._show_widget(menu)
        self._refresh_stage_navigation()

    def _open_manual_workspace(self) -> None:
        if not self.view.workflows.ensure_profile(self._open_manual_workspace):
            return
        if self.view._active_tool is not None and self.view.navigation.route is AppRoute.MANUAL:
            return
        tools = [spec.id for spec in self.view._tool_specs if spec.enabled and spec.widget_factory is not None]
        if tools:
            previous = self.view.workflows.workspace_state.get("route")
            self._open_tool(previous if previous in tools else tools[0])

    def _show_automated_pipeline(self) -> None:
        self._open_automation("run")

    def _show_automated_profiles(self) -> None:
        self._open_automation("profiles")

    def _open_automation(self, page: str) -> None:
        if not self.view.workflows.ensure_profile(lambda: self._open_automation(page)):
            return
        if not self._can_leave_active_tool():
            return
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = True
        self.view.animations._set_manual_pipeline_expanded(False)
        self.view._main_menu.show_automated()
        self._show_widget(self.view._main_menu)
        profiles = self.view._main_menu.automated_profiles.profiles
        if page == "profiles":
            profiles._show_profile_configuration()
        else:
            profiles._show_automation_menu()

    def _automated_workspace_changed(self, page: str) -> None:
        self.view.navigation.automatic_page = page
        if not self.view.navigation.automatic_active:
            return
        self.view.setWindowTitle(
            "DLC Gait Assembler - Automation settings"
            if page == "profiles"
            else "DLC Gait Assembler - Automated pipeline"
        )
        self._refresh_stage_navigation()

    def _open_tool(self, tool_id: str) -> None:
        if not self.view.workflows.ensure_profile(lambda: self._open_tool(tool_id)):
            return
        if not self._can_leave_active_tool():
            return
        spec = self._tool_spec(tool_id)
        if spec.widget_factory is None or not spec.enabled:
            return
        tool = self.view._tool_widgets.get(tool_id)
        if tool is None:
            tool = spec.widget_factory()
            if spec.connect_back is not None:
                spec.connect_back(tool, self._show_home_menu)
            self.view._tool_widgets[tool_id] = tool
            self.view._stack.addWidget(tool)
            try:
                self.view.workflows.attach_page(tool_id, tool)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.view._tool_widgets.pop(tool_id)
                self.view._stack.removeWidget(tool)
                tool.release_resources()
                tool.deleteLater()
                QMessageBox.warning(self.view, "Could not load workflow settings", f"{spec.label}: {exc}")
                return
        self.view.styling._apply_tool_surface_depth(tool)
        is_manual_tool = tool_id in self.view._manual_stage_buttons
        self.view._active_tool = tool
        self.view.navigation.tool_id = tool_id
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = False
        self.view.animations._set_manual_pipeline_expanded(is_manual_tool)
        self.view.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self._refresh_stage_navigation()
        self._show_widget(tool)
        if is_manual_tool:
            QTimer.singleShot(240, lambda expected_tool_id=tool_id: self._enforce_manual_row(expected_tool_id))

    def _enforce_manual_row(self, expected_tool_id: str) -> None:
        """Keep manual navigation visible after a newly mounted workspace settles."""
        if self.view.navigation.tool_id != expected_tool_id or expected_tool_id not in self.view._manual_stage_buttons:
            return
        self.view._manual_stage_animation.stop()
        self.view._toolbar_height_animation.stop()
        self.view._toolbar_max_height_animation.stop()
        self.view._manual_stage_expanded = True
        self.view._manual_stage_frame.show()
        self.view._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
        self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
        self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
        self.view._manual_stage_frame.updateGeometry()
        self.view._toolbar.updateGeometry()
        QTimer.singleShot(0, self.view.animations._snap_manual_stage_highlight)

    def _refresh_stage_navigation(self) -> None:
        navigation = self.view.navigation
        home_active = navigation.home_active and self.view._stack.currentWidget() is self.view._main_menu
        self.view._home_button.setProperty("activeNavigation", home_active)
        self.view._manual_tools_button.setProperty("activeNavigation", navigation.route is AppRoute.MANUAL)
        self.view._ladder_button.setProperty("activeNavigation", navigation.tool_id == self.view._ladder_spec.id)
        self.view._automation_run_button.setProperty(
            "activeNavigation", navigation.automatic_active and navigation.automatic_page == "run"
        )
        self.view._automation_profiles_button.setProperty(
            "activeNavigation", navigation.automatic_active and navigation.automatic_page == "profiles"
        )
        for stage_id, stage_button in self.view._manual_stage_buttons.items():
            stage_button.setProperty("activeStage", stage_id == self.view.navigation.tool_id)
            stage_button.style().unpolish(stage_button)
            stage_button.style().polish(stage_button)
            stage_button.update()
        for button in (self.view._home_button, *self.view._primary_navigation_buttons):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        if self.view._manual_stage_expanded:
            self.view.animations._animate_manual_stage_highlight()
        self.view.animations._animate_primary_navigation_highlight()

    def _tool_spec(self, tool_id: str) -> ToolSpec:
        for spec in (*self.view._tool_specs, self.view._ladder_spec):
            if spec.id == tool_id:
                return spec
        raise ValueError(f"Unknown tool: {tool_id}")

    def _can_leave_active_tool(self) -> bool:
        if self.view._active_tool is None:
            return True
        return bool(self.view._active_tool.can_close(self.view))

    def _show_widget(self, widget: QWidget) -> None:
        self.view._stack.setCurrentWidget(widget)

    def _release_all_tools(self) -> None:
        for tool in self.view._tool_widgets.values():
            tool.release_resources()
        self.view._tool_widgets.clear()
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = True
        self.view.navigation.automatic_active = False
