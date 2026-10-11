"""Style knee dataset selection, reconstruction settings, coordinate previews, and results."""

from __future__ import annotations

from PySide6.QtCore import QSize

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class KneeCorrectionStyle:
    """KneeCorrectionStyle operates on its explicitly supplied KneeCorrectionWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        settings_tab_style = """
            QTabWidget#KneeCorrectionSettingsTabs {
                background: {theme.PANEL};
            }
            QTabWidget#KneeCorrectionSettingsTabs::pane {
                background: {theme.BACKGROUND};
                border: 0;
                border-top: 1px solid {theme.BORDER};
            }
            QTabWidget#KneeCorrectionSettingsTabs QTabBar::tab {
                background: {theme.PANEL};
            }
            QTabWidget#KneeCorrectionSettingsTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
            }
        """
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "KneeCorrectionWidget",
                settings_tab_style
                + """
                QTreeWidget#KneePairTable {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                }
                QWidget#KneeStickplotPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                }
                QGroupBox[elevatedWorkspaceSurface="true"] {
                    background: {theme.SURFACE};
                    border: 0;
                    border-radius: 7px;
                    margin-top: 12px;
                    padding-top: 8px;
                }
                QGroupBox[elevatedWorkspaceSurface="true"]::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 4px;
                }
                """,
            )
        )
        icon_specs = (
            (self.view.add_files_button, "plus", theme.TEXT),
            (self.view.add_folder_button, "folder", theme.TEXT),
            (self.view.remove_button, "trash", theme.STATUS_ERROR),
            (self.view.clear_button, "clear", theme.STATUS_ERROR),
            (self.view.calibration_map_button, "upload", theme.TEXT),
            (self.view.output_folder_button, "folder", theme.TEXT),
            (self.view.export_manifest_button, "download", theme.TEXT),
            (self.view.run_button, "play", theme.PRIMARY_TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))
