"""Style video sources, region operations, timeline, and export controls."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QToolButton

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class VideoProcessingStyle:
    """VideoProcessingStyle operates on its explicitly supplied VideoEditorWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        if hasattr(self.view, "crop_tool_button"):
            self.view.crop_tool_button.setStyleSheet(tool_button_style(theme.TOOL_3))
            self.view.enhancements_tool_button.setStyleSheet(tool_button_style(theme.TOOL_2))
            self.view.trim_tool_button.setStyleSheet(tool_button_style(theme.TOOL_1))
            icon_specs = (
                (self.view.add_videos_button, "plus", theme.TEXT),
                (self.view.add_folder_button, "folder", theme.TEXT),
                (self.view.remove_videos_button, "trash", theme.STATUS_ERROR),
                (self.view.clear_videos_button, "clear", theme.STATUS_ERROR),
                (self.view.import_video_manifest_button, "upload", theme.TEXT),
                (self.view.export_video_manifest_button, "download", theme.TEXT),
                (self.view.process_button, "play", theme.PRIMARY_TEXT),
            )
            for button, icon_name, color in icon_specs:
                button.setIcon(interface_icon(icon_name, color))
                button.setIconSize(QSize(16, 16))
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "VideoEditorWidget",
                """
            QScrollArea#OperationSettingsScroll,
            QScrollArea#OperationSettingsScroll > QWidget,
            QWidget#OperationSettingsContent {
                background: {theme.SURFACE};
                border: 0;
            }
            QPushButton#TinyResetButton {
                border-radius: 2px;
                padding: 0 4px;
                font-size: 9px;
            }
            QPushButton#InlineDeleteButton {
                border: 0;
                border-radius: 0;
                padding: 0;
                min-width: 18px;
                max-width: 18px;
                min-height: 18px;
                max-height: 18px;
                background: transparent;
                color: {theme.TEXT};
                font-weight: 800;
            }
            QPushButton#InlineDeleteButton:hover {
                background: {theme.PANEL};
                color: {theme.STATUS_ERROR};
            }
            QPushButton#CreateRegionButton,
            QPushButton#CreateCropRegionButton,
            QPushButton#CreateTrimRangeButton,
            QPushButton#ChooseVideosButton,
            QPushButton#ResetButton {
                font-weight: 650;
            }
            QPushButton#CreateCropRegionButton {
                background: {theme.SURFACE};
                border-color: {theme.BORDER};
                color: {theme.TEXT};
            }
            QPushButton#CreateTrimRangeButton {
                background: {theme.SURFACE};
                border-color: {theme.BORDER};
                color: {theme.TEXT};
            }
            QPushButton#ChooseVideosButton {
                padding: 2px 6px;
                font-size: 10px;
                min-height: 18px;
                background: {theme.SURFACE};
                border-color: {theme.BORDER};
                color: {theme.TEXT};
            }
            QPushButton#ChooseVideosButton:hover {
                background: {theme.SOFT};
                border-color: {theme.TEXT};
                color: {theme.TEXT};
            }
            QPushButton#ResetButton,
            QPushButton#CreateRegionButton {
                background: {theme.SURFACE};
                border-color: {theme.ACCENT};
                color: {theme.TEXT};
            }
            QFrame#RegionSettings {
                border: 0;
                border-top: 1px solid {theme.BORDER};
                border-radius: 0;
                background: transparent;
            }
            QLabel#RegionTitle {
                font-weight: 600;
                font-size: 12px;
            }
            QLabel#DimensionLabel {
                color: {theme.CONNECTOR};
                font-size: 11px;
            }
            QFrame#EnhancementSettings {
                border: 0;
                border-top: 1px solid {theme.BORDER};
                border-radius: 0;
                background: transparent;
            }
            QSlider#EnhancementSlider::groove:horizontal {
                height: 7px;
                border-radius: 3px;
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
            }
            QSlider#EnhancementSlider::handle:horizontal {
                width: 16px;
                margin: -6px 0;
                border-radius: 2px;
                background: {theme.SOFT};
                border: 1px solid {theme.TEXT};
            }
            QSlider#EnhancementSlider::handle:horizontal:hover {
                background: {theme.mix_hex(theme.SOFT, theme.SURFACE, 0.35)};
            }
            QListWidget::item {
                padding: 4px 6px;
            }
            QGraphicsView {
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
                background: {theme.CANVAS};
            }
            """,
            )
        )


def make_tool_button(text: str, color: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setCheckable(True)
    button.setStyleSheet(tool_button_style(color))
    return button


def tool_button_style(color: str) -> str:
    return f"\n        QToolButton {{\n            background: {theme.SURFACE};\n            border: 1px solid {theme.BORDER};\n            border-bottom: 3px solid {color};\n            color: {theme.TEXT};\n            border-radius: 3px;\n            padding: 6px 10px;\n            font-weight: 600;\n        }}\n        QToolButton:hover {{\n            background: {theme.PANEL};\n            border-color: {theme.CONNECTOR};\n            border-bottom-color: {color};\n        }}\n        QToolButton:checked {{\n            background: {theme.PANEL};\n            border: 1px solid {theme.TEXT};\n            border-bottom: 3px solid {color};\n            color: {theme.TEXT};\n        }}\n        QToolButton:disabled {{\n            background: {theme.BACKGROUND};\n            border-color: {theme.ACCENT};\n            color: {theme.CONNECTOR};\n        }}\n    "
