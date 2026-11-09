"""Style calibration media, measurement settings, canvas, and assessment controls."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QToolButton

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


def stick_color(axis: str) -> str:
    if axis == "x":
        return "#C9866D" if theme.IS_DARK else "#985D46"
    return "#C2A16C" if theme.IS_DARK else "#8C7044"


class CalibrationStyle:
    """CalibrationStyle operates on its explicitly supplied ManualCalibrationWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        if hasattr(self.view, "x_tool_button"):
            self.view.x_tool_button.setStyleSheet(tool_button_style(stick_color("x")))
            self.view.y_tool_button.setStyleSheet(tool_button_style(stick_color("y")))
            self.view.cm_tool_button.setStyleSheet(tool_button_style(theme.TOOL_1))
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "ManualCalibrationWidget",
                """
            QLabel#ResultsLabel {
                background: {theme.SURFACE};
            }
            QScrollArea#ResultsScroll,
            QScrollArea#ResultsScroll > QWidget,
            QScrollArea#ResultsScroll > QWidget > QWidget {
                background: {theme.SURFACE};
                border: 0;
            }
            QPushButton#ResetButton {
                padding: 2px 5px;
                font-size: 10px;
            }
            QPushButton#PreviewResetZoomButton {
                background: {theme.BACKGROUND};
                border: 1px solid {theme.TEXT};
                border-radius: 0;
                color: {theme.TEXT};
                font-size: 10px;
                font-weight: 700;
                padding: 2px 5px;
            }
            QPushButton#PreviewResetZoomButton:hover {
                background: {theme.PANEL};
                color: {theme.TEXT};
            }
            QGraphicsView {
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
                background: {theme.CANVAS};
            }
                """,
            )
        )
        icon_specs = (
            (self.view.open_media_button, "plus", theme.TEXT),
            (self.view.remove_media_button, "trash", theme.STATUS_ERROR),
            (self.view.clear_calibration_button, "clear", "#FFFFFF"),
            (self.view.save_to_gait_button, "check", theme.PRIMARY_TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))
        if hasattr(self.view, "results_label"):
            self.view.controller._update_calibration_results()


def make_tool_button(text: str, color: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setCheckable(True)
    button.setStyleSheet(tool_button_style(color))
    return button


def tool_button_style(color: str) -> str:
    return f"\n        QToolButton {{\n            background: {theme.SURFACE};\n            border: 1px solid {theme.BORDER};\n            border-bottom: 3px solid {color};\n            color: {theme.TEXT};\n            border-radius: 0;\n            padding: 6px 10px;\n            font-weight: 600;\n        }}\n        QToolButton:hover {{\n            background: {theme.PANEL};\n            border-color: {theme.CONNECTOR};\n            border-bottom-color: {color};\n        }}\n        QToolButton:checked {{\n            background: {theme.PANEL};\n            border: 1px solid {theme.TEXT};\n            border-bottom: 3px solid {color};\n            color: {theme.TEXT};\n        }}\n        QToolButton:disabled {{\n            background: {theme.BACKGROUND};\n            border-color: {theme.ACCENT};\n            color: {theme.CONNECTOR};\n        }}\n    "
