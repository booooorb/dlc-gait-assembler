"""Animate workflow stage navigation expansion and selection highlights."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QRect

from dlc_gait_assembly.app.client.app_shell_styles import APP_TOOLBAR_HEIGHT, WORKFLOW_ROW_HEIGHT


class AppNavigationAnimations:
    """AppNavigationAnimations operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

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

    def _manual_stage_animation_finished(self) -> None:
        if self.view._manual_stage_expanded:
            self.view._manual_stage_frame.setMaximumHeight(WORKFLOW_ROW_HEIGHT)
            self.view._toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            self.view._toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT)
            self._snap_manual_stage_highlight()
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
        for button in self.view._primary_navigation_buttons:
            if button.property("activeNavigation"):
                return button, button.property("navigationRole")
        return None, ""
