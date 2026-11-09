"""Style the application shell, navigation, and active workspace surfaces."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QGroupBox, QWidget

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet as _dependency_theme_stylesheet
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex as _dependency_theme_mix_hex


class AppShellStyle:
    """AppShellStyle operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

    def _apply_shell_style(self) -> None:
        stylesheet = _dependency_theme_stylesheet(
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
                QFrame#WorkflowProfileBar {
                    background: transparent;
                    border: 0;
                }
                QFrame#WorkflowProfileBar QPushButton, QFrame#WorkflowProfileBar QComboBox {
                    min-height: 30px;
                }
                QFrame#WorkflowProfileBar QPushButton { padding: 0; }
                QWidget#WorkflowPicker { background: {theme.BACKGROUND}; }
                QLabel#WorkflowPickerTitle { font-size: 30px; font-weight: 600; }
                QLabel#WorkflowPickerDescription { color: {theme.CONNECTOR}; font-size: 13px; }
                QWidget#WorkflowPicker QListWidget {
                    background: {theme.SURFACE}; border: 1px solid {theme.BORDER};
                    border-radius: 10px; padding: 6px;
                }
                QWidget#WorkflowPicker QListWidget::item {
                    padding: 0; border: 0; border-bottom: 1px solid {theme.BORDER}; border-radius: 6px;
                }
                QWidget#WorkflowPicker QListWidget::item:hover { background: {theme.PANEL}; }
                QWidget#WorkflowPicker QListWidget::item:selected { background: {theme.PANEL}; }
                QLabel#WorkflowRowTitle { font-size: 16px; font-weight: 600; background: transparent; }
                QLabel#WorkflowRowDetail { color: {theme.CONNECTOR}; font-size: 12px; background: transparent; }
                QLabel#WorkflowRowArrow { font-size: 22px; background: transparent; }
                QLabel#WorkflowEmptyState {
                    color: {theme.CONNECTOR}; background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER}; border-radius: 10px; padding: 36px 20px;
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
                QFrame#PrimaryNavigationHighlight[navigationRole="ladder"] {
                    background: NAV_PROFILES_FILL;
                    border-bottom-color: {theme.TOOL_2};
                }
                QPushButton#PrimaryNavigationButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-bottom-width: 3px;
                    border-radius: 6px;
                    color: {theme.CONNECTOR};
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 36px;
                    max-height: 36px;
                    padding: 0 8px;
                }
                QPushButton#PrimaryNavigationButton:hover,
                QPushButton#PrimaryNavigationButton:focus {
                    background: {theme.PANEL};
                    color: {theme.TEXT};
                }
                QPushButton#PrimaryNavigationButton[activeNavigation="true"] {
                    background: transparent;
                    color: {theme.TEXT};
                    font-weight: 700;
                }
                QFrame#ManualStageExpansion {
                    background: {theme.PANEL};
                    border: 0;
                    border-top: 1px solid {theme.BORDER};
                    border-bottom: 1px solid {theme.BORDER};
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
                QToolButton#SettingsButton,
                QToolButton#CreditsButton {
                    background: transparent;
                    border: 1px solid {theme.BORDER};
                    border-radius: 6px;
                    color: {theme.TEXT};
                    font-size: 12px;
                    min-height: 32px;
                    padding: 1px 11px;
                }
                QToolButton#SettingsButton:hover,
                QToolButton#SettingsButton:open,
                QToolButton#CreditsButton:hover,
                QToolButton#CreditsButton:open {
                    background: {theme.SURFACE};
                    border-color: {theme.CONNECTOR};
                }
                QFrame#PartnerMarks {
                    background: transparent;
                    border: 0;
                    margin-left: 10px;
                }
                QFrame#PrimaryToolbarRow[compactHeader="true"] QPushButton#PrimaryNavigationButton {
                    padding-left: 5px; padding-right: 5px;
                }
                QLabel#MainMenuLogo {
                    background: transparent;
                }
                """
        )
        stylesheet = (
            stylesheet.replace("NAV_HOME_FILL", _dependency_theme_mix_hex(theme.TOOL_1, theme.SURFACE, 0.9))
            .replace("NAV_RUN_FILL", _dependency_theme_mix_hex(theme.TOOL_1, theme.SURFACE, 0.84))
            .replace("NAV_PROFILES_FILL", _dependency_theme_mix_hex(theme.TOOL_2, theme.SURFACE, 0.86))
            .replace("NAV_MANUAL_FILL", _dependency_theme_mix_hex(theme.TOOL_3, theme.SURFACE, 0.86))
        )
        self.view._shell.setStyleSheet(stylesheet)
        self.view.header._apply_navigation_icons()

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
        surfaces = [child for child in tool.findChildren(QWidget) if child.objectName() in surface_names]
        if tool.property("elevateGroupSurfaces"):
            surfaces.extend(tool.findChildren(QGroupBox))
        seen: set[int] = set()
        for surface in surfaces:
            identity = id(surface)
            if identity in seen:
                continue
            seen.add(identity)
            newly_elevated = not bool(surface.property("elevatedWorkspaceSurface"))
            surface.setProperty("elevatedWorkspaceSurface", True)
            if surface.graphicsEffect() is not None:
                surface.setGraphicsEffect(None)
            if newly_elevated:
                surface.style().unpolish(surface)
                surface.style().polish(surface)


WORKFLOW_ROW_HEIGHT = 44
APP_TOOLBAR_HEIGHT = 64
MINIMUM_WINDOW_SIZE = QSize(1100, 640)
DEFAULT_WINDOW_SIZE = QSize(1440, 900)
WINDOW_SCREEN_MARGIN = 64
