from dlc_gait_assembly.app.app_bootstrap import create_main_menu


from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations


from dlc_gait_assembly.app.app_bootstrap import create_profile_use_cases


from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import (
    CalibrationSettingsSnapshot,
)


from dlc_gait_assembly.runway.manual.calibration.business.calibration_use_cases import calculate_calibration_report


from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_controller import DeepLabCutController


from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
    create_cohort_writer,
    create_gait_preview,
    create_knee_correction_use_cases,
    create_ladder_use_cases,
    create_main_window,
    create_media_access,
    create_video_processing_use_cases,
)


(TOOL_SPECS, LADDER_TOOL_SPEC) = build_tool_specs()


from dlc_gait_assembly.shared.client.theme.theme_font_loader import interface_font as _dependency_theme_interface_font


from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    fixed_width_font as _dependency_theme_fixed_width_font,
)


from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    NOTO_SANS_FONT_DIR as _dependency_theme_NOTO_SANS_FONT_DIR,
)


from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    NOTO_SANS_FONT_FILES as _dependency_theme_NOTO_SANS_FONT_FILES,
)


from dlc_gait_assembly.shared.client.theme.theme_qt_palette import (
    application_palette as _dependency_theme_application_palette,
)


from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    application_stylesheet as _dependency_theme_application_stylesheet,
)


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from PySide6.QtCore import QAbstractAnimation, QSettings, QSize, Qt


from PySide6.QtGui import QDesktopServices, QPixmap


from PySide6.QtTest import QTest


from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QWidget,
)


import dlc_gait_assembly.shared.client.theme.theme_application_state as theme


from dlc_gait_assembly.app.app_bootstrap import resolved_theme_mode


from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_view import DeepLabCutWidget


from dlc_gait_assembly.ladder.client.ladder_analysis_view import LadderAnalysisWidget


from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget


from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_view import KneeCorrectionWidget


from dlc_gait_assembly.runway.manual.calibration.client.calibration_view import ManualCalibrationWidget


from dlc_gait_assembly.runway.automatic.client.automatic_workspace_view import AutomatedPipelineProfilesWidget


from dlc_gait_assembly.app.client.app_shell_styles import APP_TOOLBAR_HEIGHT


from dlc_gait_assembly.app.client.app_branding_widgets import BRAND_LOGO_FILENAMES


from dlc_gait_assembly.app.client.app_branding_widgets import PartnerLogoLabel


from dlc_gait_assembly.app.client.app_shell_styles import WORKFLOW_ROW_HEIGHT


from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_view import PcaRandomForestWidget


from dlc_gait_assembly.runway.manual.video_processing.client.video_processing_view import VideoEditorWidget


from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_repository import (
    AutomatedProfileStore,
)


from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings


from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationPoint


from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick


def _wait_for_animation(animation, timeout_ms: int = 1500) -> None:
    elapsed = 0
    while animation.state() == QAbstractAnimation.State.Running and elapsed < timeout_ms:
        QTest.qWait(20)
        elapsed += 20
    assert animation.state() == QAbstractAnimation.State.Stopped


from dlc_gait_assembly.app.app_bootstrap import create_deeplabcut_environment


from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


from dlc_gait_assembly.app.app_bootstrap import create_calibration_use_cases


from dlc_gait_assembly.app.infrastructure.app_preferences_store import (
    AppPreferencesStore,
    THEME_SETTING_KEY,
    WINDOW_GEOMETRY_SETTING_KEY,
)


def test_application_stylesheet_uses_one_plain_component_system():
    stylesheet = _dependency_theme_application_stylesheet()
    assert 'font-family: "Noto Sans"' in stylesheet
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


def test_application_uses_bundled_noto_sans_universally():
    app = QApplication.instance() or QApplication([])
    interface_font = _dependency_theme_interface_font()
    fixed_width_font = _dependency_theme_fixed_width_font()
    assert interface_font.family() == "Noto Sans"
    assert fixed_width_font.family() == "Noto Sans"
    assert all(
        (_dependency_theme_NOTO_SANS_FONT_DIR / filename).is_file()
        for filename in _dependency_theme_NOTO_SANS_FONT_FILES
    )


def test_every_tool_workspace_uses_the_shared_workspace_contract(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(DeepLabCutController, "_check_deeplabcut_available", lambda self: None)
    widgets = [
        ManualCalibrationWidget(
            media_access=create_media_access(), workspace=resolve_workspace(), use_cases=create_calibration_use_cases()
        ),
        VideoEditorWidget(
            use_cases=create_video_processing_use_cases(),
            media_access=create_media_access(),
            workspace=resolve_workspace(),
        ),
        DeepLabCutWidget(environment=create_deeplabcut_environment()),
        KneeCorrectionWidget(
            use_cases=create_knee_correction_use_cases(),
            media_access=create_media_access(),
            workspace=resolve_workspace(),
        ),
        AlmaKinematicsWidget(
            preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
        ),
        LadderAnalysisWidget(
            use_cases=create_ladder_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
        ),
        PcaRandomForestWidget(outputs=create_cohort_writer(), workspace=resolve_workspace()),
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
    window = create_main_window(initial_theme_mode="light")
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
    expected_style = Qt.ToolButtonIconOnly if window.width() < 1240 else Qt.ToolButtonTextBesideIcon
    assert window._settings_button.toolButtonStyle() == expected_style
    assert [action.text() for action in window._settings_menu.actions()] == ["Light mode", "Dark mode"]
    window._theme_actions["dark"].trigger()
    assert requested_modes == ["dark"]
    window.set_theme_mode("light")
    assert window._theme_actions["light"].isChecked()
    assert requested_modes == ["dark"]
    window.close()


def test_main_menu_exposes_manual_workflow_and_automated_profiles():
    app = QApplication.instance() or QApplication([])
    menu = create_main_menu(TOOL_SPECS)
    tabs = menu.findChild(QTabWidget, "PipelineTabs")
    assert tabs is not None
    assert tabs.tabBar().expanding()
    assert tabs.tabBar().isHidden()
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Manual pipeline", "Automated pipeline"]
    assert menu.view_stack.currentWidget() is menu.home_page
    assert menu.automated_choice_button.text() == "Run automated pipeline"
    assert menu.configure_profiles_button.text() == "Configure profiles"
    assert menu.configure_profiles_button.sizeHint().height() < menu.automated_choice_button.sizeHint().height()
    assert menu.manual_choice_button.text() == "Open Runway"
    assert menu.ladder_choice_button.text() == "Open ladder analysis"
    assert not menu.runway_choice_illustration.pixmap().isNull()
    assert not menu.ladder_choice_illustration.pixmap().isNull()
    assert menu.runway_choice_illustration.accessibleName() == "Laboratory mouse walking through a runway enclosure"
    assert menu.ladder_choice_illustration.accessibleName() == "Laboratory mouse walking across a horizontal ladder"
    assert not menu.automated_choice_button.icon().isNull()
    assert not menu.configure_profiles_button.icon().isNull()
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


def test_ladder_analysis_opens_from_secondary_home_workflow_and_returns_home():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window._main_menu.ladder_choice_button.click()
    app.processEvents()
    assert window.navigation.tool_id == LADDER_TOOL_SPEC.id
    assert isinstance(window._active_tool, LadderAnalysisWidget)
    assert not window._manual_stage_expanded
    assert window.windowTitle() == "DLC Gait Assembler - Ladder Analysis"
    window._active_tool.back_requested.emit()
    app.processEvents()
    assert window._stack.currentWidget() is window._main_menu
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.home_page
    window.close()


def test_entire_runway_and_ladder_cards_are_clickable():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    QTest.qWait(600)
    runway_card = window._main_menu._runway_choice_card_widget
    runway_point = window._main_menu.runway_choice_illustration.mapToGlobal(
        window._main_menu.runway_choice_illustration.rect().center()
    )
    runway_target = QApplication.widgetAt(runway_point)
    assert runway_target is runway_card
    QTest.mouseClick(runway_target, Qt.LeftButton, pos=runway_target.mapFromGlobal(runway_point))
    app.processEvents()
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.runway_home_page
    window.close()
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    QTest.qWait(600)
    ladder_card = window._main_menu._ladder_choice_card_widget
    assert window._main_menu.ladder_choice_illustration.testAttribute(Qt.WA_TransparentForMouseEvents)
    QTest.mouseClick(ladder_card, Qt.LeftButton, pos=ladder_card.rect().center())
    app.processEvents()
    assert window.navigation.tool_id == LADDER_TOOL_SPEC.id
    window.close()


def test_manual_pipeline_card_zooms_into_an_actionable_manual_only_menu():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    window.routes._show_runway_menu()
    QTest.qWait(100)
    source_width = window._main_menu._manual_choice_card_widget.width()
    window._main_menu.runway_manual_choice_button.click()
    app.processEvents()
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.manual_pipeline_page
    assert window._main_menu._manual_zoom_animation.state() == QAbstractAnimation.State.Running
    overlay_effect = window._main_menu._manual_zoom_overlay.graphicsEffect()
    assert overlay_effect is None
    QTest.qWait(380)
    assert window._main_menu._manual_zoom_overlay is None
    assert window._main_menu._expanded_manual_card_widget.width() > source_width
    assert not window._main_menu._automated_choice_card_widget.isVisible()
    stages = window._main_menu.manual_pipeline_page.findChildren(QFrame, "ManualMiniStage")
    assert len(stages) == 6
    assert all(stage.cursor().shape() == Qt.PointingHandCursor for stage in stages)
    stages[0].clicked.emit("manual_calibration")
    app.processEvents()
    assert window.navigation.tool_id == "manual_calibration"
    window.close()


def test_manual_navigation_exports_current_settings_and_summarizes_saved_profile(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    editor = window._main_menu.automated_profiles
    editor.profile_use_cases = create_profile_use_cases(AutomatedProfileStore(tmp_path / "profiles"))
    editor.profiles._refresh_profiles()
    assert window._manual_preset_profile_button.text() == "Create\nprofile"
    assert not window._manual_preset_profile_button.icon().isNull()
    for stage in ("video_processing", "manual_calibration", "gait_parameter_analysis", "knee_correction"):
        window.routes._open_tool(stage)
    calibration = window._tool_widgets["manual_calibration"]
    calibration.media_panel._add_media_paths([])
    sticks = (CalibrationStick("x", 1, CalibrationPoint(0, 0), CalibrationPoint(42, 0)),)
    calibration.settings_snapshot = lambda: CalibrationSettingsSnapshot(
        sticks, calculate_calibration_report(list(sticks))
    )
    gait = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    gait.frame_rate_spin.setValue(240.0)
    knee = window._tool_widgets["knee_correction"]
    knee.settings_snapshot = lambda: KneeCorrectionSettings(
        hip_knee_length_cm=1.5, knee_ankle_length_cm=1.7, pixels_per_cm=42.0
    )
    messages = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("Treadmill preset", True))
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, body: messages.append((title, body)))
    window.routes._create_profile_from_manual_presets()
    app.processEvents()
    profile = editor.profile_use_cases.list_profiles()[0]
    assert profile.name == "Treadmill preset"
    assert editor.workspace_stack.currentWidget() is editor.configuration_page
    assert profile.processing_manifest is not None
    assert profile.calibration_map is not None
    assert profile.analysis_manifest is not None
    assert profile.knee_manifest is not None
    assert editor.include_gait_analysis_button.isChecked()
    assert editor.include_knee_correction_button.isChecked()
    assert messages[0][0] == "Profile created"
    assert "✓  Video settings manifest" in messages[0][1]
    assert "✓  Calibration map" in messages[0][1]
    assert "✓  Gait analysis manifest" in messages[0][1]
    assert "✓  Knee correction manifest" in messages[0][1]
    assert "—  DeepLabCut models" in messages[0][1]
    window.close()


def test_one_bar_gives_each_primary_destination_a_visual_identity():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    app.processEvents()
    automation_buttons = window.findChildren(QPushButton, "RunwayOptionButton")
    assert [button.text() for button in automation_buttons] == ["Automated", "Profiles"]
    assert window._stack.currentWidget() is window._main_menu
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.home_page
    assert window._home_button.property("activeNavigation") is True
    assert window._automation_run_button.property("activeNavigation") is False
    assert window._automation_run_button.property("runwayOption") == "automated"
    assert window._automation_profiles_button.property("runwayOption") == "profiles"
    assert not window._automation_run_button.icon().isNull()
    assert not window._automation_profiles_button.icon().isNull()
    assert not window._runway_manual_button.icon().isNull()
    assert not window._settings_button.icon().isNull()
    assert window.navigation.tool_id is None
    assert window._runway_options.isHidden()
    assert window._manual_stage_frame.isHidden()
    assert window._primary_navigation_highlight.isHidden()
    window._runway_button.click()
    QTest.qWait(280)
    assert not window._runway_options.isHidden()
    assert window._runway_button.text() == "Runway  ‹"
    assert window._runway_button.property("activeNavigation") is True
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.runway_home_page
    window._automation_run_button.click()
    QTest.qWait(280)
    assert window._runway_mode_highlight.isVisible()
    assert window._runway_mode_highlight.geometry() == window.animations._runway_mode_highlight_target()
    assert window._runway_mode_highlight.property("runwayMode") == "automated"
    window._automation_profiles_button.click()
    QTest.qWait(280)
    assert window._runway_mode_highlight.geometry() == window.animations._runway_mode_highlight_target()
    assert window._runway_mode_highlight.property("runwayMode") == "profiles"
    assert (
        window._main_menu.automated_profiles.workspace_stack.currentWidget()
        is window._main_menu.automated_profiles.configuration_page
    )
    window._runway_manual_button.click()
    assert window._manual_stage_animation.state() == QAbstractAnimation.State.Running
    _wait_for_animation(window._manual_stage_animation)
    QTest.qWait(40)
    assert window._runway_mode_highlight.property("runwayMode") == "manual"
    assert not window._manual_stage_frame.isHidden()
    assert window._partner_marks.isVisible()
    assert window._toolbar.height() == APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT
    assert window._manual_stage_frame.parentWidget() is window._toolbar
    assert [button.text() for button in window._manual_stage_buttons.values()] == [
        "Calibration",
        "Video\nprocessing",
        "DeepLabCut",
        "Knee\ncorrection",
        "Gait\nanalysis",
        "PCA + random\nforest",
    ]
    assert all(button.iconSize() == QSize(20, 20) for button in window._manual_stage_buttons.values())
    assert all(not button.icon().isNull() for button in window._manual_stage_buttons.values())
    assert [label.text() for label in window._manual_stage_frame.findChildren(QLabel, "ManualStageSeparator")] == [
        ">",
        ">",
        ">",
        ">",
        ">",
        ">",
    ]
    stage_buttons = list(window._manual_stage_buttons.values())
    assert len({button.y() for button in stage_buttons}) == 1
    assert all(button.width() >= 28 for button in stage_buttons)
    assert [button.x() for button in stage_buttons] == sorted(button.x() for button in stage_buttons)
    assert window._manual_stage_animation.duration() == 210
    assert window._main_menu.pipeline_tabs.currentIndex() == 0
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.manual_pipeline_page
    assert window._manual_tools_button.property("activeManual") is True
    expanded_stages = window._main_menu.manual_pipeline_page.findChildren(QFrame, "ManualMiniStage")
    assert len(expanded_stages) == 6
    assert len({stage.y() for stage in expanded_stages}) == 3
    assert len({stage.x() for stage in expanded_stages}) == 2
    window._manual_stage_buttons["manual_calibration"].click()
    QTest.qWait(300)
    assert not window._manual_stage_frame.isHidden()
    assert window.navigation.tool_id == "manual_calibration"
    assert window._toolbar.height() == APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT
    window._automation_profiles_button.click()
    _wait_for_animation(window._manual_stage_animation)
    assert (
        window._main_menu.automated_profiles.workspace_stack.currentWidget()
        is window._main_menu.automated_profiles.configuration_page
    )
    assert window._automation_profiles_button.property("activeNavigation") is True
    assert window._manual_stage_frame.isHidden()
    assert window._partner_marks.isVisible()
    assert window._toolbar.height() == 64
    window._runway_manual_button.click()
    QTest.qWait(240)
    assert window._main_menu.pipeline_tabs.currentIndex() == 0
    assert window._manual_tools_button.property("activeManual") is True
    assert window.navigation.tool_id is None
    window._home_button.click()
    QTest.qWait(300)
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.home_page
    assert window._home_button.property("activeNavigation") is True
    assert window._manual_stage_frame.isHidden()
    window.close()


def test_navigation_does_not_override_the_user_window_size():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.show()
    window.resize(1180, 700)
    app.processEvents()
    chosen_size = window.size()
    window.routes._show_main_menu()
    _wait_for_animation(window._manual_stage_animation)
    assert window._toolbar.height() == APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT
    assert window._manual_stage_frame.isVisible()
    window.routes._show_home_menu()
    _wait_for_animation(window._manual_stage_animation)
    assert window._toolbar.height() == APP_TOOLBAR_HEIGHT
    window.routes._show_automated_pipeline()
    window._main_menu.automated_profiles.set_pipeline_running(True)
    app.processEvents()
    assert window.size() == chosen_size
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
        window = create_main_window(initial_theme_mode="light")
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
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())


@pytest.mark.parametrize(
    ("filename", "expected_url"),
    (("choforcelab.png", "https://www.choforcelab.ca"), ("NERVES_Logo.png", "https://nerves.bme.utah.edu")),
)
def test_partner_logos_open_their_websites(monkeypatch, filename, expected_url):
    app = QApplication.instance() or QApplication([])
    opened_urls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened_urls.append(url.toString()) or True)
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
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())
        window = create_main_window(initial_tool_id="gait_parameter_analysis", initial_theme_mode="dark")
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
        ladder = LadderAnalysisWidget(
            use_cases=create_ladder_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
        )
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
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())


def test_gait_and_pca_stay_embedded_with_clear_workspace_navigation():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    window.routes._open_tool("gait_parameter_analysis")
    gait = window._tool_widgets["gait_parameter_analysis"]
    assert window._stack.currentWidget() is gait
    assert not gait.isWindow()
    assert [
        gait.kinematics_widget.workspace_tabs.tabText(index)
        for index in range(gait.kinematics_widget.workspace_tabs.count())
    ] == ["1. Inputs", "2. Preview / results", "3. Run log"]
    window.routes._open_tool("pca_random_forest")
    pca = window._tool_widgets["pca_random_forest"]
    app.processEvents()
    assert window._stack.currentWidget() is pca
    assert not pca.isWindow()
    assert all(size >= 300 for size in pca.analysis_splitter.sizes())
    assert pca.log.width() >= 300
    window.routes._open_tool("gait_parameter_analysis")
    app.processEvents()
    assert window._stack.currentWidget() is gait
    assert window._tool_widgets["pca_random_forest"] is pca
    window.close()


def test_main_navigation_uses_one_primary_bar_instead_of_a_duplicate_tab_strip():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    menu = None
    try:
        theme.set_dark_mode(False)
        window = create_main_window(initial_theme_mode="light")
        menu = window._main_menu
        assert menu.pipeline_tabs.tabBar().isHidden()
        assert window._toolbar.height() == 64
        assert window._home_button.size().width() == 168
        assert window._home_button.size().height() == 44
        assert not window._home_button.icon().isNull()
        assert window._brand_logo_filename == "DLC-Gait-Assembler-logo-light-original-clean.png"
        assert window._primary_navigation.objectName() == "PrimaryNavigation"
        assert "QToolButton#RunwayNavigationButton" in window._shell.styleSheet()
        assert "QPushButton#RunwayOptionButton" in window._shell.styleSheet()
        window.close()
    finally:
        if menu is not None:
            menu.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())


def test_saved_theme_mode_overrides_system_theme(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    assert resolved_theme_mode(AppPreferencesStore(settings), Qt.ColorScheme.Dark) == "dark"
    settings.setValue(THEME_SETTING_KEY, "light")
    assert resolved_theme_mode(AppPreferencesStore(settings), Qt.ColorScheme.Dark) == "light"
    settings.setValue(THEME_SETTING_KEY, "unsupported")
    assert resolved_theme_mode(AppPreferencesStore(settings), Qt.ColorScheme.Light) == "light"


def test_window_geometry_is_saved_and_restored(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    original = create_main_window()
    restored = create_main_window()
    original.resize(1100, 730)
    app.processEvents()
    AppPreferencesStore(settings).save_geometry(original.saveGeometry())
    assert settings.contains(WINDOW_GEOMETRY_SETTING_KEY)
    assert restored.restoreGeometry(AppPreferencesStore(settings).geometry())
    assert restored.size() == original.size()
    original.close()
    restored.close()


@pytest.mark.parametrize("dark", [False, True])
def test_redesigned_menu_keeps_carbon_and_launch_controls_clear_at_minimum_size(dark):
    app = QApplication.instance() or QApplication([])
    previous_dark = theme.IS_DARK
    theme.set_dark_mode(dark)
    window = create_main_window()
    try:
        window.resize(1100, 640)
        window.show()
        window.routes._show_runway_menu()
        QTest.qWait(650)
        menu = window._main_menu
        assert window.size() == QSize(1100, 640)
        assert ("carbon-dark.png" if dark else "carbon-light.png") in menu.styleSheet()
        assert theme.SURFACE in menu.styleSheet()
        bridge = menu._pipeline_handoff_widget
        for card, button in (
            (menu._manual_choice_card_widget, menu.runway_manual_choice_button),
            (menu._automated_choice_card_widget, menu.automated_choice_button),
        ):
            assert card.geometry().bottom() < bridge.geometry().top()
            assert card.rect().contains(button.geometry())
            assert button.isVisible()
        assert menu.runway_home_page.rect().contains(bridge.geometry())
        assert all(
            button.width() >= button.sizeHint().width()
            for button in (
                window._automation_run_button,
                window._automation_profiles_button,
                window._runway_manual_button,
            )
        )
        requested = []
        menu.profiles_requested.connect(lambda: requested.append("profiles"))
        menu.configure_profiles_button.click()
        assert requested == ["profiles"]
    finally:
        window.close()
        theme.set_dark_mode(previous_dark)


def test_manual_directory_keyboard_actions_target_each_stage():
    app = QApplication.instance() or QApplication([])
    menu = create_main_menu(TOOL_SPECS)
    requested = []
    menu.tool_requested.connect(requested.append)
    menu.show_manual()
    menu.resize(1100, 600)
    menu.show()
    app.processEvents()
    try:
        for stage in menu.manual_pipeline_page.findChildren(QFrame, "ManualMiniStage"):
            stage.setFocus()
            QTest.keyClick(stage, Qt.Key_Return)
        assert requested == [spec.id for spec in TOOL_SPECS]
    finally:
        menu.close()


@pytest.mark.parametrize("dark", [False, True])
def test_sliding_mode_highlights_paint_the_original_role_colors(dark):
    app = QApplication.instance() or QApplication([])
    previous_dark = theme.IS_DARK
    theme.set_dark_mode(dark)
    window = create_main_window()
    try:
        window.resize(1100, 640)
        window.show()
        QTest.qWait(600)
        for action, color in (
            (window.routes._show_automated_pipeline, theme.TOOL_1),
            (window.routes._show_automated_profiles, theme.TOOL_2),
            (window.routes._show_main_menu, theme.TOOL_3),
        ):
            action()
            QTest.qWait(350)
            highlight = window._runway_mode_highlight
            assert highlight.geometry() == window.animations._runway_mode_highlight_target()
            rendered = highlight.grab().toImage()
            assert rendered.pixelColor(rendered.width() // 2, rendered.height() - 2).name() == color.lower()
            window.resize(1280, 720)
            QTest.qWait(30)
            assert highlight.geometry() == window.animations._runway_mode_highlight_target()
            window.resize(1100, 640)
            QTest.qWait(30)
            assert highlight.geometry() == window.animations._runway_mode_highlight_target()
    finally:
        window.close()
        theme.set_dark_mode(previous_dark)
