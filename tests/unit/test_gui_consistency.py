from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QTabWidget, QWidget

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.app import (
    THEME_SETTING_KEY,
    WINDOW_GEOMETRY_SETTING_KEY,
    resolved_theme_mode,
    restore_window_geometry,
    save_window_geometry,
)
from dlc_gait_assembly.gui.deeplabcut.window import DeepLabCutWidget
from dlc_gait_assembly.gui.gait_analysis.ladder_window import LadderAnalysisWidget
from dlc_gait_assembly.gui.gait_analysis.previews import OutputPreviewWidget
from dlc_gait_assembly.gui.gait_analysis.workers import AlmaAnalysisThread
from dlc_gait_assembly.gui.gait_analysis.window import AlmaKinematicsWidget, _auto_bodypart_label
from dlc_gait_assembly.gui.knee_correction import KneeCorrectionWidget
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.gui.main_window import (
    BRAND_LOGO_FILENAMES,
    MainMenuWidget,
    MainWindow,
    PartnerLogoLabel,
    TOOL_SPECS,
)
from dlc_gait_assembly.gui.merging.window import MergingWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget
from dlc_gait_assembly.services.pipeline.alma import AlmaRunResult, AlmaSettings


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
        KneeCorrectionWidget(),
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

    video_editor = widgets[1]
    assert not video_editor.remove_videos_button.icon().isNull()
    assert not video_editor.clear_videos_button.icon().isNull()
    assert not video_editor.import_video_manifest_button.icon().isNull()
    assert not video_editor.export_video_manifest_button.icon().isNull()

    deep_lab_cut = widgets[2]
    assert deep_lab_cut.findChild(type(deep_lab_cut.status_label), "StatusDot") is None
    assert deep_lab_cut.findChild(type(deep_lab_cut.status_label), "StatusPill") is None

    knee_correction = widgets[3]
    assert knee_correction.settings_tabs.objectName() == "KneeCorrectionSettingsTabs"
    assert "QTabWidget#KneeCorrectionSettingsTabs QTabBar::tab:selected" in knee_correction.styleSheet()

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
    assert window._home_button.text() == ""
    assert not window._home_button.icon().isNull()
    assert window._brand_logo_filename == "DLC-Gait-Assembler-logo-light-original-clean.png"
    assert window._settings_button.isVisible()
    assert not window._settings_button.icon().isNull()
    assert window._settings_button.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
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
    assert menu.view_stack.currentWidget() is menu.home_page
    assert menu.automated_choice_button.text() == "Open automated pipeline"
    assert menu.manual_choice_button.text() == "Open manual pipeline"
    assert not menu.automated_choice_button.icon().isNull()
    assert not menu.manual_choice_button.icon().isNull()
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
        "1  Video settings",
        "2  DLC models",
        "3  Analysis settings",
    ]
    assert automated_profiles.run_pipeline_button.text() == "Run pipeline"
    assert automated_profiles.run_pipeline_button.isEnabled()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.automation_page
    automated_profiles.open_profile_configuration_button.click()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.configuration_page
    automated_profiles.back_to_automation_button.click()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.automation_page
    menu.close()


def test_automation_menus_keep_guidance_in_control_tooltips():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    widget = window._main_menu.automated_profiles

    assert not widget.findChildren(QLabel, "AutomatedProfileDescription")
    assert not widget.findChildren(QLabel, "ProfileStageDescription")
    assert not widget.findChildren(QLabel, "ProfileStageTitle")
    assert widget.automation_console.toPlainText() == "[Ready]"
    assert widget.pipeline_log_state.text() == "●  Ready"
    assert widget.pipeline_log_state.property("logState") == "ready"
    assert widget.run_readiness_label.text() == "●  Ready"
    assert widget.run_readiness_label.property("readinessState") == "ready"

    interactive_controls = [
        window._automation_run_button,
        window._automation_profiles_button,
        widget.profile_selector,
        widget.duplicate_profile_button,
        widget.open_profile_configuration_button,
        widget.upload_videos_button,
        widget.remove_videos_button,
        widget.clear_videos_button,
        widget.video_list,
        widget.automation_console,
        widget.run_pipeline_button,
        widget.back_to_automation_button,
        widget.new_profile_button,
        widget.configuration_profile_selector,
        widget.profile_name,
        widget.delete_profile_button,
        widget.manifest_upload_button,
        widget.calibration_upload_button,
        widget.analysis_manifest_upload_button,
        widget.knee_manifest_upload_button,
        widget.save_profile_button,
        widget.pipeline_review_video_list,
        widget.pipeline_component_tabs,
        widget.pipeline_change_settings_button,
        widget.pipeline_needs_changes_button,
        widget.pipeline_approve_button,
    ]
    assert all(control.toolTip().strip() for control in interactive_controls)
    assert all(
        widget.configuration_tabs.tabToolTip(index).strip()
        for index in range(widget.configuration_tabs.count())
    )
    window.close()
    app.processEvents()



def test_one_bar_gives_each_primary_destination_a_visual_identity():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1180, 700)
    window.show()
    app.processEvents()
    automation_buttons = window.findChildren(QPushButton, "TopAutomationButton")

    assert [button.text() for button in automation_buttons] == ["Automated", "Profiles"]
    assert window._stack.currentWidget() is window._main_menu
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.home_page
    assert window._home_button.property("activeNavigation") is True
    assert window._automation_run_button.property("activeNavigation") is False
    assert window._automation_run_button.property("navigationRole") == "automated"
    assert window._automation_profiles_button.property("navigationRole") == "profiles"
    assert window._manual_tools_button.property("navigationRole") == "manual"
    assert not window._automation_run_button.icon().isNull()
    assert not window._automation_profiles_button.icon().isNull()
    assert not window._manual_tools_button.icon().isNull()
    assert not window._settings_button.icon().isNull()
    assert window._active_tool_id is None
    assert window._manual_tools_button.parentWidget() is not window._primary_navigation
    assert window._manual_stage_frame.isHidden()
    window._manual_tools_button.click()
    app.processEvents()
    assert window._manual_tools_button.text() == "Manual"
    assert not window._manual_stage_frame.isHidden()
    assert window._toolbar.height() == 116
    assert [button.text() for button in window._manual_stage_buttons.values()] == [
        "Calibration",
        "Video processing",
        "DeepLabCut",
        "Knee correction",
        "Gait analysis",
        "PCA + random forest",
    ]
    assert all(button.width() >= 130 for button in window._manual_stage_buttons.values())
    assert window._main_menu.pipeline_tabs.currentIndex() == 0
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.workspace_page
    assert window._manual_tools_button.property("activeManual") is True

    window._automation_profiles_button.click()
    assert window._main_menu.automated_profiles.workspace_stack.currentWidget() is (
        window._main_menu.automated_profiles.configuration_page
    )
    assert window._automation_profiles_button.property("activeNavigation") is True
    assert window._manual_stage_frame.isHidden()
    assert window._toolbar.height() == 64

    window._manual_tools_button.click()
    assert window._main_menu.pipeline_tabs.currentIndex() == 0
    assert window._manual_tools_button.property("activeManual") is True
    assert window._active_tool_id is None
    window._home_button.click()
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.home_page
    assert window._home_button.property("activeNavigation") is True
    assert window._manual_stage_frame.isHidden()
    window.close()


def test_automated_workspace_has_clear_input_activity_and_run_hierarchy(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    widget = window._main_menu.automated_profiles

    assert window.findChild(QLabel, "AppMark") is None
    assert window.findChild(QLabel, "AutomationPageSubtitle") is None
    assert not window.findChildren(QLabel, "AutomationPanelSubtitle")
    assert widget.run_status_bar.objectName() == "RunStatusBar"
    assert widget.upload_videos_button.text() == "Add videos"
    assert not widget.upload_videos_button.icon().isNull()
    assert not widget.remove_videos_button.icon().isNull()
    assert not widget.clear_videos_button.icon().isNull()
    assert not widget.open_profile_configuration_button.icon().isNull()
    assert not widget.pipeline_change_settings_button.icon().isNull()
    assert widget.run_readiness_label.objectName() == "RunReadinessBadge"
    assert widget.run_readiness_label.text() == "●  Ready"
    assert widget.run_readiness_label.property("readinessState") == "ready"
    assert "QPushButton#RemoveButton, QPushButton#ClearButton" in widget.styleSheet()
    assert "QLabel#PipelineLogState {\n    background: transparent;\n    border: 0;" in widget.styleSheet()
    assert "QLabel#ProfileStatusLabel, QLabel#RunReadinessBadge {\n    background: transparent;\n    border: 0;" in widget.styleSheet()
    assert theme.STATUS_ERROR in widget.styleSheet()
    assert not widget.remove_videos_button.isEnabled()
    assert not widget.clear_videos_button.isEnabled()
    assert "Drop source videos" in widget.video_list.accessibleDescription()

    video = tmp_path / "mouse_walk.mp4"
    video.write_bytes(b"fixture")
    widget._add_video_paths([video])
    assert widget.video_count_label.text() == "1 video"
    assert widget.remove_videos_button.isEnabled()
    assert widget.clear_videos_button.isEnabled()
    assert widget.video_list.item(0).toolTip() == str(video.resolve())

    widget._clear_videos()
    assert not widget.remove_videos_button.isEnabled()
    assert not widget.clear_videos_button.isEnabled()

    window.close()


def test_navigation_does_not_override_the_user_window_size():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    window.resize(1180, 700)
    app.processEvents()
    chosen_size = window.size()
    window._show_main_menu()
    app.processEvents()
    assert window._toolbar.height() == 116
    assert window.minimumSizeHint().width() <= window.minimumWidth()
    window._show_home_menu()
    app.processEvents()
    assert window._toolbar.height() == 64
    window._show_automated_pipeline()
    window._main_menu.automated_profiles.set_pipeline_running(True)
    app.processEvents()

    assert window.size() == chosen_size
    window.close()


def test_pipeline_geometry_stays_constant_through_stickplot_review():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    window.resize(1180, 700)
    app.processEvents()
    widget = window._main_menu.automated_profiles
    window._show_automated_pipeline()
    app.processEvents()

    initial_geometry = {
        "window": window.geometry(),
        "workspace": window._main_menu._content.geometry(),
        "pipeline": widget.geometry(),
        "input": widget.automation_input_stack.geometry(),
        "console": widget.automation_console_panel.geometry(),
    }
    preview_hint = widget.pipeline_stickplot_preview.sizeHint()

    widget.set_pipeline_running(True)
    assert widget.run_readiness_label.text() == "●  Running"
    assert widget.run_readiness_label.property("readinessState") == "running"
    widget.set_pipeline_stage(4, progress=100)
    widget._pause_for_pipeline_review(4)
    app.processEvents()

    assert widget.run_readiness_label.text() == "●  Review required"
    assert widget.run_readiness_label.property("readinessState") == "review"

    assert window.geometry() == initial_geometry["window"]
    assert window._main_menu._content.geometry() == initial_geometry["workspace"]
    assert widget.geometry() == initial_geometry["pipeline"]
    assert widget.automation_input_stack.geometry() == initial_geometry["input"]
    assert widget.automation_console_panel.geometry() == initial_geometry["console"]
    assert widget.pipeline_stickplot_preview.sizeHint() == preview_hint
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


def test_brand_logo_switches_assets_without_resizing_the_toolbar_button():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    window = None
    try:
        theme.set_dark_mode(False)
        window = MainWindow(initial_theme_mode="light")
        button_size = window._home_button.size()
        light_icon_size = window._home_button.iconSize()
        assert window._brand_logo_filename == BRAND_LOGO_FILENAMES["light"]

        theme.set_dark_mode(True)
        window.apply_theme()

        assert window._brand_logo_filename == BRAND_LOGO_FILENAMES["dark"]
        assert window._home_button.size() == button_size
        assert window._home_button.iconSize() == light_icon_size
    finally:
        if window is not None:
            window.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())


@pytest.mark.parametrize(
    ("filename", "expected_url"),
    (
        ("choforcelab.png", "https://www.choforcelab.ca"),
        ("NERVES_Logo.png", "https://nerves.bme.utah.edu"),
    ),
)
def test_partner_logos_open_their_websites(monkeypatch, filename, expected_url):
    app = QApplication.instance() or QApplication([])
    opened_urls = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    logo = PartnerLogoLabel(filename)
    logo.show()
    app.processEvents()

    QTest.mouseClick(logo, Qt.LeftButton)

    assert opened_urls == [expected_url]
    logo.close()


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
        window.resize(1100, 640)
        window.show()
        gait = window._tool_widgets["gait_parameter_analysis"]

        app.processEvents()
        runway_geometry = window.geometry()
        header = gait.kinematics_widget.findChild(QWidget, "WorkspaceHeader")
        assert window.height() == 640
        assert header is not None and header.height() < 64
        assert not hasattr(gait, "ladder_widget")
        assert window._stack.currentWidget() is gait
        assert gait.kinematics_widget.controls_scroll.verticalScrollBar().maximum() > 0

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


def test_gait_and_pca_stay_embedded_with_clear_workspace_navigation():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1180, 700)
    window.show()

    window._open_tool("gait_parameter_analysis")
    gait = window._tool_widgets["gait_parameter_analysis"]
    assert window._stack.currentWidget() is gait
    assert not gait.isWindow()
    assert [
        gait.kinematics_widget.workspace_tabs.tabText(index)
        for index in range(gait.kinematics_widget.workspace_tabs.count())
    ] == ["1. Inputs", "2. Preview / results", "3. Run log"]

    window._open_tool("pca_random_forest")
    pca = window._tool_widgets["pca_random_forest"]
    app.processEvents()

    assert window._stack.currentWidget() is pca
    assert not pca.isWindow()
    assert all(size >= 300 for size in pca.analysis_splitter.sizes())
    assert pca.log.width() >= 300

    window._open_tool("gait_parameter_analysis")
    app.processEvents()
    assert window._stack.currentWidget() is gait
    assert window._tool_widgets["pca_random_forest"] is pca

    window.close()


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
        mapping_index = runway.settings_tabs.indexOf(runway.mapping_tab)
        assert mapping_index >= 0
        assert runway.settings_tabs.tabText(mapping_index) == "Mapping"
        assert _auto_bodypart_label(["iliac-crest"], "iliac crest") == "iliac-crest"
        assert "QTabWidget#RunwaySettingsTabs QTabBar::tab" in stylesheet
        assert f"background: {theme.PANEL};" in stylesheet
        assert f"background: {theme.SURFACE};" in stylesheet
    finally:
        if runway is not None:
            runway.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())


def test_runway_preview_uses_selected_multiview_set_and_visible_stride_count(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    captured: dict[str, object] = {}

    class _Signal:
        def connect(self, *_args):
            pass

    class _PreviewThread:
        progress_updated = _Signal()
        log_message = _Signal()
        preview_ready = _Signal()
        preview_failed = _Signal()
        finished = _Signal()

        def __init__(self, csv_files, settings, _alma_root):
            captured["csvs"] = [Path(path).name for _label, path in csv_files]
            captured["strides"] = settings.n_continuous_strides

        def start(self):
            captured["started"] = True

        def isRunning(self):
            return False

    monkeypatch.setattr(
        "dlc_gait_assembly.gui.gait_analysis.window.StickPlotPreviewThread",
        _PreviewThread,
    )
    widget = AlmaKinematicsWidget()
    widget._missing_required_bodyparts = lambda _settings: []
    paths = [
        tmp_path / "first_left.csv",
        tmp_path / "first_right.csv",
        tmp_path / "first_bottom.csv",
        tmp_path / "second_left.csv",
        tmp_path / "second_right.csv",
        tmp_path / "second_bottom.csv",
    ]
    for path in paths:
        path.write_text(
            "scorer,a,a,a\nbodyparts,toe,toe,toe\ncoords,x,y,likelihood\n",
            encoding="utf-8",
        )

    widget._add_csv_paths(paths)
    widget.file_list.setCurrentRow(4)
    widget.continuous_strides_spin.setValue(7)
    widget._generate_stickplot_preview()

    assert len(widget._view_sets) == 2
    assert widget.view_set_table.topLevelItemCount() == 2
    assert widget.view_set_table.currentItem().text(0) == "second"
    assert captured == {"csvs": ["second_left.csv", "second_right.csv"], "strides": 7, "started": True}
    assert widget.preview_stack.minimumHeight() >= 280
    assert widget.workspace_tabs.currentWidget() is widget.preview_page
    widget.close()
    app.processEvents()


def test_runway_requires_complete_left_right_bottom_csv_sets(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AlmaKinematicsWidget()
    left = tmp_path / "mouse_left.csv"
    right = tmp_path / "mouse_right.csv"
    for path in (left, right):
        path.write_text(
            "scorer,a,a,a\nbodyparts,toe,toe,toe\ncoords,x,y,likelihood\n",
            encoding="utf-8",
        )

    widget._add_csv_paths([left, right])

    assert widget._view_sets == []
    assert not widget.preview_button.isEnabled()
    assert "missing bottom" in widget.view_set_status_label.text().lower()
    assert widget.view_set_table.topLevelItemCount() == 1
    assert "Missing bottom" in widget.view_set_table.topLevelItem(0).text(4)
    widget.close()
    app.processEvents()


def test_runway_previews_generated_svg_figures_and_csv_tables(tmp_path):
    app = QApplication.instance() or QApplication([])
    csv_path = tmp_path / "mouse_parameter_summary.csv"
    csv_path.write_text(
        "parameter,mean,standard_deviation\nstride_length,4.2,0.3\nstep_height,1.1,0.1\n",
        encoding="utf-8",
    )
    figure_folder = tmp_path / "mouse_alma_figures"
    figure_folder.mkdir()
    svg_path = figure_folder / "1_ALMA_cycle_timing.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="200" height="100" fill="white"/>'
        '<path d="M10 80 L80 20 L190 70" stroke="black" fill="none"/>'
        "</svg>",
        encoding="utf-8",
    )
    ignored_path = tmp_path / "analysis_metadata.json"
    ignored_path.write_text("{}", encoding="utf-8")

    preview = OutputPreviewWidget(max_csv_rows=1, max_csv_columns=2)
    preview.load_paths((csv_path, ignored_path, svg_path, tmp_path / "missing.csv"))

    assert preview.paths == (csv_path.resolve(), svg_path.resolve())
    assert preview.selected_path == svg_path.resolve()
    assert preview.svg_preview.renderer().isValid()

    preview.file_combo.setCurrentIndex(0)
    assert preview.selected_path == csv_path.resolve()
    assert preview.csv_preview.rowCount() == 1
    assert preview.csv_preview.columnCount() == 2
    assert preview.csv_preview.horizontalHeaderItem(0).text() == "parameter"
    assert preview.csv_preview.item(0, 0).text() == "stride_length"

    runway = AlmaKinematicsWidget()
    runway._output_results_ready(
        (
            AlmaRunResult(
                input_file=tmp_path / "mouse_left.csv",
                output_files=(csv_path, ignored_path, svg_path),
            ),
        )
    )
    assert runway.preview_stack.currentWidget() is runway.output_preview_view
    assert runway.workspace_tabs.currentWidget() is runway.preview_page
    assert runway.output_preview_view.selected_path == svg_path.resolve()
    assert "Loaded 2 generated output previews" in runway.log.toPlainText()

    preview.close()
    runway.close()
    app.processEvents()


def test_runway_worker_hands_generated_outputs_to_preview_signal(tmp_path, monkeypatch):
    result = AlmaRunResult(
        input_file=tmp_path / "mouse_left.csv",
        output_files=(tmp_path / "mouse_parameters.csv",),
    )
    monkeypatch.setattr(
        "dlc_gait_assembly.gui.gait_analysis.workers.run_alma_gait_analysis",
        lambda *_args, **_kwargs: [result],
    )
    worker = AlmaAnalysisThread(
        [result.input_file],
        tmp_path,
        AlmaSettings(),
        tmp_path / "ALMA",
    )
    emitted_results = []
    completions = []
    worker.results_ready.connect(emitted_results.append)
    worker.analysis_completed.connect(
        lambda success, message: completions.append((success, message))
    )

    worker.run()

    assert emitted_results == [(result,)]
    assert completions == [
        (True, f"Analysis complete. Results saved to:\n{tmp_path}"),
    ]


def test_main_navigation_uses_one_primary_bar_instead_of_a_duplicate_tab_strip():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    menu = None
    try:
        theme.set_dark_mode(False)
        window = MainWindow(initial_theme_mode="light")
        menu = window._main_menu

        assert menu.pipeline_tabs.tabBar().isHidden()
        assert window._toolbar.height() == 64
        assert window._home_button.size().width() == 168
        assert window._home_button.size().height() == 44
        assert not window._home_button.icon().isNull()
        assert window._brand_logo_filename == "DLC-Gait-Assembler-logo-light-original-clean.png"
        assert window._primary_navigation.objectName() == "PrimaryNavigation"
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


def test_window_geometry_is_saved_and_restored(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    original = MainWindow()
    restored = MainWindow()
    # The offscreen Qt test display is narrower than the app's minimum width,
    # so vary the height while keeping the saved geometry display-valid.
    original.resize(1100, 730)
    app.processEvents()

    save_window_geometry(original, settings)

    assert settings.contains(WINDOW_GEOMETRY_SETTING_KEY)
    assert restore_window_geometry(restored, settings)
    assert restored.size() == original.size()
    original.close()
    restored.close()
