"""Style cohort input selection, analysis options, progress, and results."""

from __future__ import annotations

from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)


class CohortAnalysisStyle:
    """CohortAnalysisStyle operates on its explicitly supplied PcaRandomForestWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "PcaRandomForestWidget",
                """
                QScrollArea#CohortControlsScroll,
                QScrollArea#CohortControlsScroll > QWidget,
                QScrollArea#CohortControlsScroll > QWidget > QWidget {
                    border: 0;
                    background: {theme.PANEL};
                }
                """,
            )
        )
