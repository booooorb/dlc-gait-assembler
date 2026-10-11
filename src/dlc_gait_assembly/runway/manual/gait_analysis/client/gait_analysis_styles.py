"""Style gait inputs, settings tabs, preview/results pages, and run logs."""

from __future__ import annotations

from PySide6.QtCore import QSize

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class GaitAnalysisStyle:
    """GaitAnalysisStyle operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _apply_style(self) -> None:
        runway_tab_style = """
            QTabWidget#RunwaySettingsTabs {
                background: {theme.PANEL};
            }
            QTabBar#RunwaySettingsSectionRow {
                background: {theme.PANEL};
                border: 0;
            }
            QWidget#RunwayStickySettingsNavigation {
                background: {theme.PANEL};
                border: 0;
                border-bottom: 1px solid {theme.BORDER};
            }
            QTabBar#RunwaySettingsSectionRow::tab {
                background: {theme.PANEL};
                border: 0;
                color: {theme.CONNECTOR};
                font-size: 12px;
                min-height: 30px;
                padding: 0 8px;
            }
            QTabBar#RunwaySettingsSectionRow::tab:hover {
                background: {theme.SOFT};
                color: {theme.TEXT};
            }
            QTabBar#RunwaySettingsSectionRow::tab:selected {
                background: {theme.SURFACE};
                color: {theme.TEXT};
                font-weight: 700;
            }
            QTabBar#RunwaySettingsSectionRow[activeRow="false"]::tab:selected {
                background: {theme.PANEL};
                color: {theme.CONNECTOR};
                font-weight: 400;
            }
            QTabWidget#RunwaySettingsTabs::pane {
                background: {theme.BACKGROUND};
                border: 0;
                border-top: 1px solid {theme.BORDER};
            }
            QTabWidget#RunwaySettingsTabs QTabBar::tab {
                background: {theme.PANEL};
            }
            QTabWidget#RunwaySettingsTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
            }
            QTabWidget#RunwayWorkspaceTabs::pane {
                border: 1px solid {theme.BORDER};
                background: {theme.SURFACE};
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar {
                background: {theme.PANEL};
                border-bottom: 1px solid {theme.BORDER};
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar::tab {
                background: {theme.PANEL};
                color: {theme.CONNECTOR};
                border: 0;
                border-bottom: 3px solid transparent;
                min-width: 120px;
                padding: 8px 12px;
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar::tab:hover {
                background: {theme.SOFT};
                color: {theme.TEXT};
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
                color: {theme.TEXT};
                border-bottom-color: transparent;
                font-weight: 700;
            }
        """
        self.view.setStyleSheet(
            _dependency_theme_workspace_stylesheet(
                "GaitAnalysisWidget",
                runway_tab_style
                + """
            QStackedWidget#StickPlotPreview {
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
                background: white;
            }
            QSvgWidget#StickPlotSvg {
                background: white;
            }
            QScrollArea#RunwayControlsScroll,
            QScrollArea#RunwayControlsScroll > QWidget,
            QScrollArea#RunwayControlsScroll > QWidget > QWidget {
                border: 0;
                background: {theme.PANEL};
            }
            QWidget#RunwayActionFooter {
                border-top: 1px solid {theme.BORDER};
                background: {theme.PANEL};
            }
            QWidget#GaitParameterReference {
                background: {theme.BACKGROUND};
                background-image: url({theme.BACKGROUND_TEXTURE});
            }
            QLabel#ParameterReferenceTitle {
                color: {theme.TEXT};
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#ParameterReferenceSubtitle {
                color: {theme.CONNECTOR};
                font-size: 13px;
                padding-bottom: 6px;
            }
            QFrame#FigureCreatorIndex,
            QFrame#FigureCreatorDetails {
                background: {theme.SURFACE};
                border: 1px solid {theme.BORDER};
                border-radius: 6px;
            }
            QLabel#FigureCreatorTitle {
                color: {theme.TEXT};
                font-size: 20px;
                font-weight: 700;
                border: 0;
            }
            QLabel#FigureCreatorIntro {
                color: {theme.CONNECTOR};
                font-size: 12px;
                border: 0;
            }
            QLabel#FigureCountLabel {
                color: {theme.CONNECTOR};
                font-size: 11px;
                border: 0;
            }
            QLabel#FigureIndexHeading {
                color: {theme.TEXT};
                font-size: 13px;
                font-weight: 700;
                border: 0;
            }
            QListWidget#FigureCreatorList {
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
                padding: 3px;
            }
            QListWidget#FigureCreatorList::item {
                color: {theme.TEXT};
                padding: 6px 7px;
                border-radius: 3px;
            }
            QListWidget#FigureCreatorList::item:selected {
                background: {theme.PRIMARY};
                color: white;
            }
            QSvgWidget#FigureCreatorPreview {
                background: white;
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
            }
            QLabel#FigureSourceBadge {
                color: {theme.PRIMARY};
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 9px;
                font-size: 10px;
                font-weight: 700;
                padding: 2px 8px;
            }
            QLabel#FigurePreviewNote {
                color: {theme.CONNECTOR};
                font-size: 11px;
                border: 0;
            }
            QScrollArea#FigureExplanationScroll,
            QScrollArea#FigureExplanationScroll > QWidget,
            QScrollArea#FigureExplanationScroll > QWidget > QWidget {
                background: transparent;
                border: 0;
            }
            QLabel#FigureExplanationTitle {
                color: {theme.TEXT};
                font-size: 16px;
                font-weight: 700;
                border: 0;
            }
            QLabel#FigureDetailHeading {
                color: {theme.TEXT};
                font-size: 11px;
                font-weight: 700;
                border: 0;
            }
            QLabel#FigureDetailValue {
                color: {theme.CONNECTOR};
                font-size: 11px;
                border: 0;
            }
            QTreeWidget#GaitParameterTree {
                background: {theme.SURFACE};
                alternate-background-color: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
            }
            QFrame#ParameterDetails {
                background: {theme.SURFACE};
                border: 1px solid {theme.BORDER};
                border-radius: 5px;
            }
            QLabel#ParameterName {
                color: {theme.TEXT};
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#ParameterDetailHeading {
                color: {theme.TEXT};
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#ParameterDetailValue {
                color: {theme.CONNECTOR};
                font-size: 13px;
            }
            QLabel#ParameterCalculationFocus {
                color: {theme.TEXT};
                font-size: 15px;
                font-weight: 600;
                padding: 6px 0 10px 0;
            }
            QTreeWidget#GaitParameterSelectionTree {
                background: {theme.SURFACE};
                alternate-background-color: {theme.PANEL};
                border: 1px solid {theme.BORDER};
            }
            """,
            )
        )
        icon_specs = (
            (self.view.add_file_button, "plus", theme.TEXT),
            (self.view.add_folder_button, "folder", theme.TEXT),
            (self.view.clear_files_button, "clear", theme.STATUS_ERROR),
            (self.view.output_folder_button, "folder", theme.TEXT),
            (self.view.load_fps_button, "upload", theme.TEXT),
            (self.view.import_calibration_map_button, "upload", theme.TEXT),
            (self.view.export_manifest_button, "download", theme.TEXT),
            (self.view.preview_button, "eye", theme.TEXT),
            (self.view.run_button, "play", theme.PRIMARY_TEXT),
            (self.view.figure_reference_button, "chart", theme.TEXT),
            (self.view.parameter_reference_button, "document", theme.TEXT),
            (self.view.documentation_back_button, "arrow-left", theme.TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))
