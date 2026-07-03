from __future__ import annotations

import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QTabWidget, QWidget

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.app import THEME_SETTING_KEY, resolved_theme_mode
from dlc_gait_assembly.gui.deeplabcut.window import DeepLabCutWidget
from dlc_gait_assembly.gui.gait_analysis.ladder_window import LadderAnalysisWidget
from dlc_gait_assembly.gui.gait_analysis.window import AlmaKinematicsWidget
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.gui.main_window import MainMenuWidget, MainWindow, PartnerLogoLabel, TOOL_SPECS
from dlc_gait_assembly.gui.merging.window import MergingWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget


def test_application_stylesheet_uses_one_plain_component_system():
    stylesheet = theme.application_stylesheet()

    for selector in (
        "QPushButton, QToolButton",
        "QLineEdit, QTextEdit, QPlainTextEdit, QComboBox",
        "QGroupBox",
        "QTabWidget::pane",
        "QHeaderView::section",
        "QProgressBar",
    ):
        assert selector in stylesheet

    lowered = stylesheet.lower()
    assert "gradient" not in lowered
    assert "box-shadow" not in lowered
    assert "border-radius: 20" not in lowered


def test_every_tool_workspace_uses_the_shared_workspace_contract(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(DeepLabCutWidget, "_check_deeplabcut_available", lambda self: None)
    widgets = [
        ManualCalibrationWidget(),
        VideoEditorWidget(),
        DeepLabCutWidget(),
        AlmaKinematicsWidget(),
        LadderAnalysisWidget(),
        PcaRandomForestWidget(),
        MergingWidget(),
    ]

    for widget in widgets:
        stylesheet = widget.styleSheet()
        assert "QLabel#TitleLabel, QLabel#PreviewTitle" in stylesheet
        assert "QPushButton#RemoveButton, QPushButton#ClearButton" in stylesheet
        assert "border-radius: 2px" in stylesheet

    deep_lab_cut = widgets[2]
    assert deep_lab_cut.findChild(type(deep_lab_cut.status_label), "StatusDot") is None
    assert deep_lab_cut.findChild(type(deep_lab_cut.status_label), "StatusPill") is None

    for widget in widgets:
        release_resources = getattr(widget, "release_resources", None)
        if release_resources is not None:
            release_resources()
        widget.close()


def test_visible_settings_dropdown_emits_theme_choices_without_reemitting_updates():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(initial_theme_mode="light")
    window.show()
    app.processEvents()
    requested_modes: list[str] = []
    window.theme_mode_requested.connect(requested_modes.append)

    assert window.menuWidget() is None
    assert window._settings_button.isVisible()
    assert [action.text() for action in window._settings_menu.actions()] == [
        "Light mode",
        "Dark mode",
    ]

    window._theme_actions["dark"].trigger()
    assert requested_modes == ["dark"]

    window.set_theme_mode("light")
    assert window._theme_actions["light"].isChecked()
    assert requested_modes == ["dark"]
    window.close()


def test_main_menu_exposes_manual_workflow_and_automated_profiles():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuWidget(TOOL_SPECS)
    tabs = menu.findChild(QTabWidget, "PipelineTabs")

    assert tabs is not None
    assert tabs.tabBar().expanding()
    assert tabs.tabBar().isHidden()
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Manual pipeline",
        "Automated pipeline",
    ]
    expected_stages = [spec.label for spec in TOOL_SPECS]
    manual_page = tabs.widget(0)
    automated_page = tabs.widget(1)
    assert [label.text() for label in manual_page.findChildren(QLabel, "StepTitle")] == expected_stages
    assert all(button.isEnabled() for button in manual_page.findChildren(QPushButton, "OpenToolButton"))
    automated_profiles = automated_page.findChild(AutomatedPipelineProfilesWidget)
    assert automated_profiles is not None
    assert automated_page.findChild(QScrollArea, "AutomatedPipelineScroll") is None
    assert not automated_page.findChildren(QPushButton, "OpenToolButton")
    configuration_tabs = automated_profiles.findChild(QTabWidget, "ProfileConfigurationTabs")
    assert [configuration_tabs.tabText(index) for index in range(configuration_tabs.count())] == [
        "1  Manifest + regions",
        "2  Region models",
        "3  Gait analysis",
        "4  Review + save",
    ]
    assert automated_profiles.run_pipeline_button.text() == "RUN pipeline"
    assert automated_profiles.run_pipeline_button.isEnabled()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.automation_page
    automated_profiles.open_profile_configuration_button.click()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.configuration_page
    automated_profiles.back_to_automation_button.click()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.automation_page
    menu.close()


def test_one_bar_prioritizes_automation_and_expands_manual_stages_to_the_right():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    automation_buttons = window.findChildren(QPushButton, "TopAutomationButton")

    assert [button.text() for button in automation_buttons] == ["Run", "Profiles"]
    assert window._stack.currentWidget() is window._main_menu
    assert window._main_menu.pipeline_tabs.currentIndex() == 1
    assert window._automation_run_button.property("activeNavigation") is True
    assert window._active_tool_id is None
    assert window._manual_stage_frame.isHidden()
    window._manual_tools_button.click()
    assert not window._manual_stage_frame.isHidden()
    assert [button.text() for button in window._manual_stage_buttons.values()] == [
        "Overview",
        "Calibration",
        "Video",
        "DeepLabCut",
        "Gait",
        "PCA/RF",
    ]

    window._automation_profiles_button.click()
    assert window._main_menu.automated_profiles.workspace_stack.currentWidget() is (
        window._main_menu.automated_profiles.configuration_page
    )
    assert window._automation_profiles_button.property("activeNavigation") is True

    window._manual_stage_buttons["manual_overview"].click()
    assert window._main_menu.pipeline_tabs.currentIndex() == 0
    assert window._manual_tools_button.property("activeManual") is True
    assert window._manual_tools_button.isChecked()
    assert window._manual_stage_buttons["manual_overview"].property("activeStage") is True
    window.close()


def test_partner_logos_use_pixel_outlines_only_in_dark_mode():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    try:
        theme.set_dark_mode(False)
        logo = PartnerLogoLabel("choforcelab.png")
        light_size = logo.pixmap().size()

        theme.set_dark_mode(True)
        logo.apply_theme()
        dark_size = logo.pixmap().size()

        assert dark_size.width() > light_size.width()
        assert dark_size.height() > light_size.height()
        assert logo.styleSheet() == ""
        logo.close()
    finally:
        theme.set_dark_mode(previous_mode)


def test_gait_workspaces_fit_the_window_and_keep_their_bottom_accessible():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    window = None
    ladder = None
    try:
        theme.set_dark_mode(True)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())
        window = MainWindow(
            initial_tool_id="gait_parameter_analysis",
            initial_theme_mode="dark",
        )
        window.resize(1280, 820)
        window.show()
        gait = window._tool_widgets["gait_parameter_analysis"]

        app.processEvents()
        runway_geometry = window.geometry()
        header = gait.kinematics_widget.findChild(QWidget, "WorkspaceHeader")
        assert window.height() == 820
        assert header is not None and header.height() < 64
        assert not hasattr(gait, "ladder_widget")

        ladder = LadderAnalysisWidget()
        ladder.resize(1280, 750)
        ladder.show()
        app.processEvents()
        controls_scroll = ladder.findChild(QScrollArea, "LadderControlsScroll")
        preview = ladder.video_preview
        preview_geometry = preview.geometry()
        preview.setPixmap(QPixmap(1920, 1080))
        app.processEvents()
        preview.setPixmap(QPixmap(320, 240))
        app.processEvents()
        assert window.geometry() == runway_geometry
        assert preview.geometry() == preview_geometry
        assert controls_scroll is not None
        assert controls_scroll.verticalScrollBar().maximum() > 0
    finally:
        if ladder is not None:
            ladder.close()
        if window is not None:
            window.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())


def test_runway_light_mode_has_a_distinct_settings_tab_strip():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    runway = None
    try:
        theme.set_dark_mode(False)
        runway = AlmaKinematicsWidget()
        stylesheet = runway.styleSheet()

        assert runway.settings_tabs.objectName() == "RunwaySettingsTabs"
        assert runway.settings_tabs.tabBar().expanding()
        assert "QTabWidget#RunwaySettingsTabs QTabBar::tab" in stylesheet
        assert f"background: {theme.PANEL};" in stylesheet
        assert f"background: {theme.SURFACE};" in stylesheet
    finally:
        if runway is not None:
            runway.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())


def test_main_navigation_uses_one_primary_bar_instead_of_a_duplicate_tab_strip():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    menu = None
    try:
        theme.set_dark_mode(False)
        window = MainWindow(initial_theme_mode="light")
        menu = window._main_menu

        assert menu.pipeline_tabs.tabBar().isHidden()
        assert window._toolbar.height() == 60
        assert "QPushButton#TopAutomationButton" in window._shell.styleSheet()
        window.close()
    finally:
        if menu is not None:
            menu.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())


def test_saved_theme_mode_overrides_system_theme(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    assert resolved_theme_mode(settings, Qt.ColorScheme.Dark) == "dark"

    settings.setValue(THEME_SETTING_KEY, "light")
    assert resolved_theme_mode(settings, Qt.ColorScheme.Dark) == "light"

    settings.setValue(THEME_SETTING_KEY, "unsupported")
    assert resolved_theme_mode(settings, Qt.ColorScheme.Light) == "light"
