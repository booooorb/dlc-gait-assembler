"""Style DeepLabCut environment actions, terminal controls, and status presentation."""

from __future__ import annotations

from PySide6.QtCore import QSize

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class DeepLabCutStyle:
    """DeepLabCutStyle operates on its explicitly supplied DeepLabCutWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "DeepLabCutWidget",
                """
            QWidget#StatusGroup {
                background: transparent;
            }
            QLabel#StatusLabel {
                background: transparent;
                border: 0;
                color: {theme.CONNECTOR};
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#StatusLabel[statusState="ready"] {
                color: {theme.STATUS_READY};
            }
            QLabel#StatusLabel[statusState="running"] {
                color: {theme.STATUS_RUNNING};
            }
            QLabel#StatusLabel[statusState="error"] {
                color: {theme.STATUS_ERROR};
            }
            QFrame#TerminalFrame {
                background: {theme.CANVAS};
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
            }
            QFrame#TerminalToolbarDivider {
                background: {theme.BORDER};
                border: 0;
                min-width: 1px;
                max-width: 1px;
                min-height: 22px;
                max-height: 22px;
                margin: 0 4px;
            }
            QFrame#TerminalHeader {
                background: {theme.CANVAS};
                border-radius: 0;
            }
            QLabel#TerminalHeaderLabel {
                color: {theme.CANVAS_TEXT};
                font-size: 12px;
                font-weight: 700;
            }
            QPlainTextEdit#TerminalPane {
                border: 0;
                border-top: 1px solid {theme.BORDER};
                border-radius: 0;
                background: {theme.CANVAS};
                color: {theme.CANVAS_TEXT};
                font-size: 13px;
                padding: 12px;
                selection-background-color: {theme.SOFT};
            }
            QWidget#TerminalViewport {
                background: {theme.CANVAS};
            }
            """,
            )
        )
        icon_specs = (
            (self.view.launch_button, "play", theme.PRIMARY_TEXT),
            (self.view.outputs_button, "folder", theme.TEXT),
            (self.view.install_button, "download", theme.TEXT),
            (self.view.install_docs_button, "external", theme.TEXT),
            (self.view.user_docs_button, "external", theme.TEXT),
            (self.view.github_button, "external", theme.TEXT),
            (self.view.paper_button, "external", theme.TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))
