"""Select application pages and enforce their public leave and resource-release contracts."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
from dlc_gait_assembly.app.client.app_shell_styles import APP_TOOLBAR_HEIGHT, WORKFLOW_ROW_HEIGHT
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_from_manual import combine_manual_snapshots


class AppRouteController:
    """AppRouteController operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

    def _manual_navigation_clicked(self) -> None:
        manual_active = (
            not self.view.navigation.home_active
            and (not self.view.navigation.automatic_active)
            and (self.view.navigation.tool_id != self.view._ladder_spec.id)
        )
        if manual_active and self.view._manual_stage_expanded:
            self.view.animations._set_manual_pipeline_expanded(False)
            return
        self._show_main_menu()

    def _show_home_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = True
        self.view.navigation.automatic_active = False
        self.view.animations._set_runway_options_expanded(False)
        self.view.animations._set_manual_pipeline_expanded(False)
        self.view._main_menu.show_home()
        self.view.setWindowTitle("DLC Gait Assembler")
        self._refresh_stage_navigation()
        self._show_widget(self.view._main_menu)

    def _show_main_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = False
        self.view.animations._set_runway_options_expanded(True)
        self.view.animations._set_manual_pipeline_expanded(True)
        self.view._main_menu.show_manual()
        self.view.setWindowTitle("DLC Gait Assembler - Manual pipeline")
        self._refresh_stage_navigation()
        self._show_widget(self.view._main_menu)

    def _show_runway_menu(self) -> None:
        if not self._can_leave_active_tool():
            return
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = False
        self.view.animations._set_runway_options_expanded(True)
        self.view.animations._set_manual_pipeline_expanded(False)
        self.view._main_menu.show_runway_home()
        self.view.setWindowTitle("DLC Gait Assembler - Runway")
        self._refresh_stage_navigation()
        self._show_widget(self.view._main_menu)

    def _show_automated_pipeline(self) -> None:
        if not self._can_leave_active_tool():
            return
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = True
        self.view.animations._set_runway_options_expanded(True)
        self.view.navigation.automatic_page = "run"
        self.view.animations._set_manual_pipeline_expanded(False)
        self.view._main_menu.show_automated()
        self.view._main_menu.automated_profiles.profiles._show_automation_menu()
        self.view.setWindowTitle("DLC Gait Assembler - Automated pipeline")
        self._refresh_stage_navigation()
        self._show_widget(self.view._main_menu)

    def _show_automated_profiles(self) -> None:
        if not self._can_leave_active_tool():
            return
        self.view._active_tool = None
        self.view.navigation.tool_id = None
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = True
        self.view.animations._set_runway_options_expanded(True)
        self.view.navigation.automatic_page = "profiles"
        self.view.animations._set_manual_pipeline_expanded(False)
        self.view._main_menu.show_automated()
        self.view._main_menu.automated_profiles.profiles._show_profile_configuration()
        self.view.setWindowTitle("DLC Gait Assembler - Manage automated profiles")
        self._refresh_stage_navigation()
        self._show_widget(self.view._main_menu)

    def _create_profile_from_manual_presets(self) -> None:
        (name, accepted) = QInputDialog.getText(
            self.view, "Create profile from manual settings", "Profile name:", text="Manual settings profile"
        )
        name = name.strip()
        if not accepted or not name:
            return
        snapshots = []
        for spec in self.view._tool_specs:
            page = self.view._tool_widgets.get(spec.id)
            if page is not None and spec.snapshot_provider is not None:
                try:
                    snapshots.append(spec.snapshot_provider(page))
                except ValueError:
                    continue
        snapshot = combine_manual_snapshots(snapshots)
        automatic = self.view._main_menu.automated_profiles
        try:
            (profile, present) = automatic.profile_use_cases.create_from_manual(name, snapshot)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not create profile", str(exc))
            return
        automatic.show_created_profile(profile)
        self._show_automated_profiles()
        labels = {
            "processing_manifest": "Video settings manifest",
            "calibration_map": "Calibration map",
            "analysis_manifest": "Gait analysis manifest",
            "knee_manifest": "Knee correction manifest",
        }
        saved = [label for (key, label) in labels.items() if key in present]
        missing = [label for (key, label) in labels.items() if key not in present]
        missing.append("DeepLabCut models (assign one per video region)")
        summary = [f'Profile "{profile.name}" was created.', "", "Saved:"]
        summary.extend(f"✓  {label}" for label in saved)
        if not saved:
            summary.append("—  No manual manifests were available")
        summary.extend(("", "Not saved:"))
        summary.extend(f"—  {label}" for label in missing)
        QMessageBox.information(self.view, "Profile created", "\n".join(summary))

    def _automated_workspace_changed(self, page: str) -> None:
        self.view.navigation.automatic_page = page
        if not self.view.navigation.automatic_active:
            return
        self.view.setWindowTitle(
            "DLC Gait Assembler - Manage automated profiles"
            if page == "profiles"
            else "DLC Gait Assembler - Automated pipeline"
        )
        self._refresh_stage_navigation()

    def _pipeline_tab_changed(self, index: int) -> None:
        if self.view._stack.currentWidget() is not self.view._main_menu:
            return
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = index == 1
        self.view.animations._set_runway_options_expanded(True)
        self.view.animations._set_manual_pipeline_expanded(not self.view.navigation.automatic_active)
        if not self.view.navigation.automatic_active:
            self.view.navigation.tool_id = None
        self.view.setWindowTitle(
            "DLC Gait Assembler - Automated pipeline"
            if self.view.navigation.automatic_active
            else "DLC Gait Assembler - Manual pipeline"
        )
        self._refresh_stage_navigation()

    def _open_tool(self, tool_id: str) -> None:
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
        self.view.styling._apply_tool_surface_depth(tool)
        is_manual_tool = tool_id in self.view._manual_stage_buttons
        self.view._active_tool = tool
        self.view.navigation.tool_id = tool_id
        self.view.navigation.home_active = False
        self.view.navigation.automatic_active = False
        self.view.animations._set_runway_options_expanded(is_manual_tool)
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
        self.view._home_button.setProperty("activeNavigation", self.view.navigation.home_active)
        runway_active = self.view.navigation.automatic_active or (
            not self.view.navigation.home_active and self.view.navigation.tool_id != self.view._ladder_spec.id
        )
        self.view._runway_button.setProperty("activeNavigation", runway_active)
        self.view._ladder_button.setProperty(
            "activeNavigation", self.view.navigation.tool_id == self.view._ladder_spec.id
        )
        self.view._automation_run_button.setProperty(
            "activeNavigation", self.view.navigation.automatic_active and self.view.navigation.automatic_page == "run"
        )
        self.view._automation_profiles_button.setProperty(
            "activeNavigation",
            self.view.navigation.automatic_active and self.view.navigation.automatic_page == "profiles",
        )
        self.view._runway_manual_button.setProperty(
            "activeNavigation", self.view.animations._active_runway_mode_button() is self.view._runway_manual_button
        )
        manual_active = not self.view.navigation.home_active and (not self.view.navigation.automatic_active)
        self.view._manual_tools_button.setProperty("activeManual", manual_active)
        for stage_id, stage_button in self.view._manual_stage_buttons.items():
            stage_button.setProperty("activeStage", stage_id == self.view.navigation.tool_id)
            stage_button.style().unpolish(stage_button)
            stage_button.style().polish(stage_button)
            stage_button.update()
        for button in (
            self.view._home_button,
            self.view._runway_button,
            self.view._ladder_button,
            self.view._automation_run_button,
            self.view._automation_profiles_button,
            self.view._runway_manual_button,
            self.view._manual_tools_button,
        ):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        if self.view._manual_stage_expanded:
            self.view.animations._animate_manual_stage_highlight()
        if self.view._runway_options_expanded:
            self.view.animations._animate_runway_mode_highlight()
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
