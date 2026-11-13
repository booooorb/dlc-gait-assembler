from dlc_gait_assembly.app.app_bootstrap import create_main_menu


from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations








from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_controller import DeepLabCutController


from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
    create_cohort_writer,
    create_gait_preview,
    create_knee_correction_use_cases,
    create_ladder_use_cases,
    create_main_window as _create_main_window,
    create_media_access,
    create_video_processing_use_cases,
)


(TOOL_SPECS, LADDER_TOOL_SPEC) = build_tool_specs()


from dlc_gait_assembly.shared.client.theme.theme_font_loader import interface_font as _dependency_theme_interface_font


from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    fixed_width_font as _dependency_theme_fixed_width_font,
)


from dlc_gait_assembly.shared.client.theme.theme_font_loader import GEIST_FONT_PATH


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
    QLabel,
    QMessageBox,
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


@pytest.fixture(autouse=True)
def discard_navigation_test_edits(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.Discard)


def create_main_window(**options):
    """Navigation tests start inside a saved workflow; profile entry has its own tests."""
    from tempfile import TemporaryDirectory
    temporary = TemporaryDirectory(prefix="gait-navigation-test-")
    window = _create_main_window(profile_store=AutomatedProfileStore(temporary.name), **options)
    window._test_profile_directory = temporary
    window.workflows.new(name="Navigation test")
    if options.get("initial_tool_id") is None:
        window.routes._show_home_menu()
        QTest.qWait(250)
    return window


def test_application_stylesheet_uses_one_plain_component_system():
    stylesheet = _dependency_theme_application_stylesheet()
    assert 'font-family: "Geist"' in stylesheet
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


def test_application_uses_bundled_geist():
    app = QApplication.instance() or QApplication([])
    interface_font = _dependency_theme_interface_font()
    fixed_width_font = _dependency_theme_fixed_width_font()
    assert interface_font.family() == "Geist"
    assert fixed_width_font.family() == "Geist"
    assert GEIST_FONT_PATH.is_file()


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
        assert "QPushButton#RemoveButton {" in stylesheet
        assert "border-radius: 0;" in stylesheet
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
    assert window._brand_logo_filename == "paw-track-light.svg"
    assert window._settings_button.isVisible()
    assert not window._settings_button.icon().isNull()
    expected_style = Qt.ToolButtonIconOnly if window.width() < 1600 else Qt.ToolButtonTextBesideIcon
    assert window._settings_button.toolButtonStyle() == expected_style
    actions = window._settings_menu.actions()
    assert [action.text() for action in actions[:2]] == ["Light mode", "Dark mode"]
    assert window.updates.check_action in actions
    assert window.updates.auto_action in actions
    window._theme_actions["dark"].trigger()
    assert requested_modes == ["dark"]
    window.set_theme_mode("light")
    assert window._theme_actions["light"].isChecked()
    assert requested_modes == ["dark"]
    window.close()


def test_main_menu_exposes_manual_workflow_and_automated_profiles():
    app = QApplication.instance() or QApplication([])
    menu = create_main_menu(TOOL_SPECS)
    assert menu.view_stack.currentWidget() is menu.home_page
    assert menu.view_stack.count() == 2
    illustrations = menu.home_page.findChildren(QLabel, "WorkspaceChoiceIllustration")
    assert len(illustrations) == 2
    assert all(not illustration.pixmap().isNull() for illustration in illustrations)
    assert menu.findChild(QWidget, "RunwayHomePage") is None
    assert menu.findChild(QWidget, "ManualPipelineMenuPage") is None
    automated_profiles = menu.automated_profiles
    assert isinstance(automated_profiles, AutomatedPipelineProfilesWidget)
    assert automated_profiles.findChild(QTabWidget, "ProfileConfigurationTabs") is None
    content = automated_profiles.configuration_scroll.widget()
    assert content.isAncestorOf(automated_profiles.include_gait_analysis_button)
    assert content.isAncestorOf(automated_profiles.models_container)
    assert automated_profiles.run_pipeline_button.text() == "Run pipeline"
    assert automated_profiles.run_pipeline_button.isEnabled()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.automation_page
    automated_profiles.open_profile_configuration_button.click()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.configuration_page
    automated_profiles.back_to_automation_button.click()
    assert automated_profiles.workspace_stack.currentWidget() is automated_profiles.automation_page
    menu.close()


def test_ladder_card_is_disabled_and_marked_wip():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.show()
    app.processEvents()
    menu = window._main_menu
    ladder_card = next(card for card in menu.home_page.findChildren(QFrame, "SetupChoiceCard")
                       if card.property("setupAsset") == "ladder-mouse")
    assert ladder_card.isVisible() and not ladder_card.isEnabled()
    assert ladder_card.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert ladder_card.cursor().shape() == Qt.ArrowCursor
    assert ladder_card.findChild(QLabel, "SetupStatus").text() == "(WIP)"
    assert window._ladder_button.isHidden() and not window._ladder_button.isEnabled()
    QTest.mouseClick(ladder_card, Qt.LeftButton)
    QTest.keyClick(ladder_card, Qt.Key_Return)
    window.routes._open_tool("ladder_analysis")
    assert "ladder_analysis" not in window._tool_widgets
    assert window._stack.currentWidget() is menu
    window.close()


def test_runway_card_opens_the_profile_picker_directly():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    app.processEvents()
    menu = window._main_menu
    picker = window.workflows
    assert menu.view_stack.currentWidget() is menu.home_page
    assert not picker.open_button.isVisible()
    runway_card = next(card for card in menu.home_page.findChildren(QFrame, "SetupChoiceCard")
                       if card.property("setupAsset") == "runway-mouse")
    QTest.mouseClick(runway_card, Qt.LeftButton)
    app.processEvents()
    assert window._stack.currentWidget() is picker.picker
    assert picker.new_profile_button.isVisible()
    assert picker.open_button.isVisible()
    picker.profile_list.setCurrentRow(0)
    picker.open_button.click()
    assert window.navigation.tool_id == "manual_calibration"
    _wait_for_animation(window._manual_stage_animation)
    assert window._manual_stage_frame.isVisible()
    window.close()


def test_manual_navigation_saves_settings_in_the_active_profile():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    for stage in ("video_processing", "manual_calibration", "gait_parameter_analysis", "knee_correction"):
        window.routes._open_tool(stage)
    gait = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    gait.frame_rate_spin.setValue(240.0)
    window.workflows.save_button.click()
    profile = window.workflows.use_cases.load(window.workflows.active.id)
    assert profile.name == "Navigation test"
    assert profile.processing_manifest is not None
    assert profile.analysis_manifest is not None
    assert set(profile.workspace_state["pages"]) == {
        "video_processing", "manual_calibration", "gait_parameter_analysis", "knee_correction"
    }
    assert profile.workspace_state["pages"]["gait_parameter_analysis"]["controls"]["frame_rate_spin"] == 240
    assert window.workflows.status.text() == "Saved"
    window.close()


def test_one_bar_gives_each_primary_destination_a_visual_identity():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1180, 700)
    window.show()
    app.processEvents()
    assert [button.text() for button in window._primary_navigation_buttons] == [
        "Manual", "Batch run", "Profiles",
    ]
    assert window._stack.currentWidget() is window._main_menu
    assert window._main_menu.view_stack.currentWidget() is window._main_menu.home_page
    assert window._home_button.property("activeNavigation") is True
    assert window._manual_stage_frame.isHidden()
    window._automation_run_button.click()
    automated = window._main_menu.automated_profiles
    assert automated.workspace_stack.currentWidget() is automated.automation_page
    window._automation_profiles_button.click()
    assert automated.workspace_stack.currentWidget() is automated.configuration_page
    window._manual_tools_button.click()
    assert window._stack.currentWidget() is window._tool_widgets["manual_calibration"]
    QTest.qWait(300)
    assert not window._manual_stage_frame.isHidden()
    assert window._partner_marks.isVisible()
    assert window._toolbar.height() == APP_TOOLBAR_HEIGHT + WORKFLOW_ROW_HEIGHT
    assert window._manual_stage_frame.parentWidget() is window._toolbar
    assert [button.text() for button in window._manual_stage_buttons.values()] == [
        "Calibration",
        "Video prep",
        "Pose tracking",
        "Knee correction",
        "Gait analysis",
        "PCA + classification",
    ]
    assert all(button.iconSize() == QSize(20, 20) for button in window._manual_stage_buttons.values())
    assert all(not button.icon().isNull() for button in window._manual_stage_buttons.values())
    assert [label.text() for label in window._manual_stage_frame.findChildren(QLabel, "ManualStageSeparator")] == [
        ">", ">", ">", ">", ">",
    ]
    stage_buttons = list(window._manual_stage_buttons.values())
    assert len({button.y() for button in stage_buttons}) == 1
    assert all(button.width() >= 28 for button in stage_buttons)
    assert [button.x() for button in stage_buttons] == sorted(button.x() for button in stage_buttons)
    assert window._manual_stage_animation.duration() == 210
    assert window._manual_tools_button.property("activeNavigation") is True
    assert window.navigation.tool_id == "manual_calibration"
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
    window.routes._open_tool("manual_calibration")
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
    ] == ["Files", "Preview", "Results", "Log"]
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
        assert menu.findChild(QTabWidget, "PipelineTabs") is None
        assert window._toolbar.height() == 64
        assert window._home_button.size().width() == 168
        assert window._home_button.size().height() == 44
        assert not window._home_button.icon().isNull()
        assert window._brand_logo_filename == "paw-track-light.svg"
        assert window.findChild(QFrame, "PrimaryNavigation") is not None
        assert "QPushButton#PrimaryNavigationButton" in window._shell.styleSheet()
        assert window.findChild(QWidget, "RunwayOptions") is None
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
def test_redesigned_menu_has_flat_background_and_launch_controls_clear_at_minimum_size(dark):
    app = QApplication.instance() or QApplication([])
    previous_dark = theme.IS_DARK
    theme.set_dark_mode(dark)
    window = create_main_window()
    try:
        window.resize(1100, 640)
        window.show()
        app.processEvents()
        menu = window._main_menu
        assert window.size() == QSize(1100, 640)
        assert theme.BACKGROUND in menu.styleSheet()
        assert "background-image" not in menu.styleSheet()
        assert theme.SURFACE in menu.styleSheet()
        for card in menu.home_page.findChildren(QFrame, "SetupChoiceCard"):
            assert card.isVisible()
            assert window.rect().contains(card.rect().translated(card.mapTo(window, card.rect().topLeft())))
        menu.runway_requested.emit()
        app.processEvents()
        picker = window.workflows
        for button in (picker.new_profile_button, picker.open_button, *window._primary_navigation_buttons):
            assert button.isVisible()
            assert button.width() >= button.sizeHint().width()
            assert window.rect().contains(button.rect().translated(button.mapTo(window, button.rect().topLeft())))
    finally:
        window.close()
        theme.set_dark_mode(previous_dark)


def test_manual_toolbar_keyboard_actions_target_each_stage():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.resize(1100, 640)
    window.show()
    window._manual_tools_button.click()
    _wait_for_animation(window._manual_stage_animation)
    try:
        for stage_id, button in window._manual_stage_buttons.items():
            button.setFocus()
            QTest.keyClick(button, Qt.Key_Space)
            assert window.navigation.tool_id == stage_id
    finally:
        window.close()


@pytest.mark.parametrize("dark", [False, True])
def test_primary_navigation_highlights_paint_each_role_color(dark):
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
            (window.routes._open_manual_workspace, theme.TOOL_3),
        ):
            action()
            QTest.qWait(350)
            highlight = window._primary_navigation_highlight
            button, _ = window.animations._active_primary_navigation_target()
            assert highlight.geometry() == window.animations._primary_navigation_target_geometry(button)
            rendered = highlight.grab().toImage()
            assert rendered.pixelColor(rendered.width() // 2, rendered.height() - 2).name() == color.lower()
            window.resize(1280, 720)
            QTest.qWait(30)
            assert highlight.geometry() == window.animations._primary_navigation_target_geometry(button)
            window.resize(1100, 640)
            QTest.qWait(30)
            assert highlight.geometry() == window.animations._primary_navigation_target_geometry(button)
    finally:
        window.close()
        theme.set_dark_mode(previous_dark)
