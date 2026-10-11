"""Style Ladder inputs, detection controls, event tables, and review surfaces."""

from __future__ import annotations

from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)


class LadderAnalysisStyle:
    """LadderAnalysisStyle operates on its explicitly supplied LadderAnalysisWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "LadderAnalysisWidget",
                """
                QLabel#VideoPreview {
                    background: {theme.CANVAS};
                    color: {theme.CANVAS_TEXT};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                """,
            )
        )
