"""Animate workflow expansion, navigation highlights, and page transitions."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QRect, QTimer

from dlc_gait_assembly.app.client.app_shell_styles import APP_TOOLBAR_HEIGHT, WORKFLOW_ROW_HEIGHT


class AppNavigationAnimations:
    """AppNavigationAnimations operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

    def _settle_runway_highlight(self) -> None:
        if self.view._runway_mode_highlight_animation.state() != QPropertyAnimation.State.Running:
            self._snap_runway_mode_highlight()

    def _toggle_runway_options(self) -> None:
        if self.view._runway_options_expanded:
            self._set_runway_options_expanded(False)
            return
        self.view.routes._show_runway_menu()

    def _set_runway_options_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if self.view._runway_options_expanded == expanded:
            return
        self.view._runway_options_expanded = expanded
        self.view._runway_button.setText("Runway  ‹" if expanded else "Runway  ›")
        runway_workspace_active = self.view.navigation.automatic_active or (
            not self.view.navigation.home_active and self.view.navigation.tool_id != self.view._ladder_spec.id
        )
        self.view._runway_button.setProperty("activeNavigation", expanded or runway_workspace_active)
        animation = self.view._runway_options_animation
        animation.stop()
        if expanded:
            start_width = self.view._runway_options.width() if self.view._runway_options.isVisible() else 0
            self.view._runway_options.show()
            target_width = self.view._runway_options.sizeHint().width()
            self.view._runway_options.setMaximumWidth(start_width)
            animation.setStartValue(start_width)
            animation.setEndValue(target_width)
        else:
            animation.setStartValue(self.view._runway_options.width())
            animation.setEndValue(0)
        animation.start()
        self.view._runway_button.setProperty("expanded", self.view._runway_options_expanded)
        self.view._runway_button.style().unpolish(self.view._runway_button)
        self.view._runway_button.style().polish(self.view._runway_button)
        self.view._runway_button.update()

    def _runway_options_animation_finished(self) -> None:
        if self.view._runway_options_expanded:
            self.view._runway_options.setMaximumWidth(16777215)
            self.view._primary_layout.activate()
            self.view._primary_navigation_layout.activate()
            self.view._runway_options.layout().activate()
            QTimer.singleShot(0, self._snap_runway_mode_highlight)
            self._snap_runway_mode_highlight()
            self._snap_primary_navigation_highlight()
            return
        self.view._runway_options.hide()
        self.view._runway_mode_highlight.hide()
        self._snap_primary_navigation_highlight()

    def _active_runway_mode_button(self):
        if self.view.navigation.automatic_active:
            return (
                self.view._automation_profiles_button
                if self.view.navigation.automatic_page == "profiles"
                else self.view._automation_run_button
            )
        manual_active = self.view.navigation.tool_id in self.view._manual_stage_buttons or (
            self.view._stack.currentWidget() is self.view._main_menu
            and self.view._main_menu.view_stack.currentWidget() is self.view._main_menu.manual_pipeline_page
        )
        return self.view._runway_manual_button if manual_active else None

    def _runway_mode_highlight_target(self) -> QRect | None:
        self.view._primary_layout.activate()
        self.view._primary_navigation_layout.activate()
        self.view._runway_options.layout().activate()
        button = self._active_runway_mode_button()
        if button is None or not button.isVisible():
            return None
        top_left = button.mapTo(self.view._runway_options, button.rect().topLeft())
        return QRect(top_left.x(), top_left.y(), button.width(), button.height())

    def _style_runway_mode_highlight(self) -> None:
        button = self._active_runway_mode_button()
        if button is self.view._automation_run_button:
            mode = "automated"
        elif button is self.view._automation_profiles_button:
            mode = "profiles"
        elif button is self.view._runway_manual_button:
            mode = "manual"
        else:
            mode = ""
        highlight = self.view._runway_mode_highlight
        if highlight.property("runwayMode") == mode:
            return
        highlight.setProperty("runwayMode", mode)
        highlight.style().unpolish(highlight)
        highlight.style().polish(highlight)

    def _snap_runway_mode_highlight(self) -> None:
        target = self._runway_mode_highlight_target()
        if target is None:
            self.view._runway_mode_highlight.hide()
            return
        self._style_runway_mode_highlight()
        self.view._runway_mode_highlight_animation.stop()
        self.view._runway_mode_highlight.setGeometry(target)
        self.view._runway_mode_highlight.show()
        self.view._runway_mode_highlight.lower()

    def _animate_runway_mode_highlight(self) -> None:
        target = self._runway_mode_highlight_target()
        highlight = self.view._runway_mode_highlight
        if target is None:
            highlight.hide()
            return
        self._style_runway_mode_highlight()
        animation = self.view._runway_mode_highlight_animation
        animation.stop()
        if highlight.isHidden() or not self.view.isVisible():
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
        if self.view._manual_stage_expanded == expanded:
            if expanded and self.view._manual_stage_frame.isHidden():
                self.view._manual_stage_frame.show()
                self.view._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
                self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
                self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            elif expanded and self.view._manual_stage_animation.state() != QPropertyAnimation.State.Running:
                self.view._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
                self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
                self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            elif not expanded and self.view._manual_stage_animation.state() != QPropertyAnimation.State.Running:
                self.view._manual_stage_frame.hide()
                self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT)
                self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT)
            return
        self.view._manual_stage_expanded = expanded
        animation = self.view._manual_stage_animation
        toolbar_animation = self.view._toolbar_height_animation
        toolbar_max_animation = self.view._toolbar_max_height_animation
        animation.stop()
        toolbar_animation.stop()
        toolbar_max_animation.stop()
        if expanded:
            self.view._manual_stage_frame.show()
            self.view._manual_stage_frame.setMaximumHeight(0)
            animation.setStartValue(0)
            animation.setEndValue(WORKFLOW_ROW_HEIGHT)
            toolbar_animation.setStartValue(self.view._toolbar.height())
            toolbar_animation.setEndValue(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            toolbar_max_animation.setStartValue(self.view._toolbar.height())
            toolbar_max_animation.setEndValue(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
        else:
            animation.setStartValue(self.view._manual_stage_frame.height())
            animation.setEndValue(0)
            toolbar_animation.setStartValue(self.view._toolbar.height())
            toolbar_animation.setEndValue(APP_TOOLBAR_HEIGHT)
            toolbar_max_animation.setStartValue(self.view._toolbar.height())
            toolbar_max_animation.setEndValue(APP_TOOLBAR_HEIGHT)
        animation.start()
        toolbar_animation.start()
        toolbar_max_animation.start()

    def _manual_stage_target_geometry(self) -> QRect:
        return QRect(0, APP_TOOLBAR_HEIGHT, self.view._shell.width(), WORKFLOW_ROW_HEIGHT)

    def _position_manual_stage_rail(self) -> None:
        if self.view._manual_stage_animation.state() == QPropertyAnimation.State.Running:
            return
        self.view._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)

    def _manual_stage_animation_finished(self) -> None:
        if self.view._manual_stage_expanded:
            self.view._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
            self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            self._snap_manual_stage_highlight()
            if not self.view.navigation.automatic_active and (not self.view.navigation.home_active):
                self._snap_primary_navigation_highlight()
            return
        self.view._manual_stage_frame.hide()
        self.view._manual_stage_highlight.hide()
        self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT)
        self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT)

    def _manual_stage_highlight_target(self) -> QRect | None:
        button = self.view._manual_stage_buttons.get(self.view.navigation.tool_id or "")
        if button is None or not button.isVisible():
            return None
        top_left = button.mapTo(self.view._manual_stage_frame, button.rect().bottomLeft())
        row_height = max(self.view._manual_stage_frame.height(), WORKFLOW_ROW_HEIGHT)
        return QRect(top_left.x() + 4, row_height - 4, max(8, button.width() - 8), 3)

    def _snap_manual_stage_highlight(self) -> None:
        target = self._manual_stage_highlight_target()
        if target is None:
            self.view._manual_stage_highlight.hide()
            return
        self.view._manual_stage_highlight_animation.stop()
        self.view._manual_stage_highlight.setGeometry(target)
        self.view._manual_stage_highlight.show()
        self.view._manual_stage_highlight.raise_()

    def _animate_manual_stage_highlight(self) -> None:
        target = self._manual_stage_highlight_target()
        highlight = self.view._manual_stage_highlight
        if target is None:
            highlight.hide()
            return
        animation = self.view._manual_stage_highlight_animation
        animation.stop()
        if highlight.isHidden() or not self.view.isVisible():
            highlight.setGeometry(target)
            highlight.show()
            highlight.raise_()
            return
        animation.setStartValue(highlight.geometry())
        animation.setEndValue(target)
        highlight.show()
        highlight.raise_()
        animation.start()

    def _animate_primary_navigation_highlight(self) -> None:
        (target_button, role) = self._active_primary_navigation_target()
        highlight = self.view._primary_navigation_highlight
        animation = self.view._primary_navigation_animation
        if target_button is None:
            animation.stop()
            highlight.hide()
            return
        target_geometry = self._primary_navigation_target_geometry(target_button)
        self._style_primary_navigation_highlight(role)
        if highlight.isHidden() or not self.view.isVisible():
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
        (target_button, role) = self._active_primary_navigation_target()
        if target_button is None:
            self.view._primary_navigation_animation.stop()
            self.view._primary_navigation_highlight.hide()
            return
        self.view._primary_navigation_animation.stop()
        self._style_primary_navigation_highlight(role)
        self.view._primary_navigation_highlight.setGeometry(self._primary_navigation_target_geometry(target_button))
        self.view._primary_navigation_highlight.show()
        self.view._primary_navigation_highlight.lower()

    def _primary_navigation_target_geometry(self, target_button):
        self.view._primary_navigation_layout.activate()
        self.view._primary_layout.activate()
        top_left = target_button.mapTo(self.view._primary_row, target_button.rect().topLeft())
        return target_button.rect().translated(top_left)

    def _style_primary_navigation_highlight(self, role: str) -> None:
        highlight = self.view._primary_navigation_highlight
        if highlight.property("navigationRole") == role:
            return
        highlight.setProperty("navigationRole", role)
        highlight.style().unpolish(highlight)
        highlight.style().polish(highlight)

    def _active_primary_navigation_target(self):
        if self.view.navigation.tool_id == self.view._ladder_spec.id:
            return (self.view._ladder_button, "ladder")
        return (None, "")
