"""A workflow survives closing and reopening across manual tools and automation."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QInputDialog, QMessageBox

from dlc_gait_assembly.app.app_bootstrap import build_tool_specs, create_main_menu
from dlc_gait_assembly.app.client.app_shell_window import MainWindow
from dlc_gait_assembly.app.client.workflow_page_state import decode_value, encode_value
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_repository import AutomatedProfileStore
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationPoint, CalibrationStick
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet, StrokeStudyMetadata
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    alma_settings_from_manifest,
)
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import CropRegion, NormalizedRect

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/gait/rustlab1_r_reference"


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    specs, ladder = build_tool_specs()
    def menu_factory(tools):
        menu = create_main_menu(tools)
        menu.automated_profiles.profile_use_cases.repository = AutomatedProfileStore(tmp_path / "profiles")
        menu.automated_profiles.profiles._refresh_profiles()
        return menu
    def error(*args):
        raise AssertionError(f"Unexpected dialog: {args[1:]}")
    monkeypatch.setattr(QMessageBox, "warning", error)
    monkeypatch.setattr(QMessageBox, "critical", error)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Discard)
    result = MainWindow(tool_specs=specs, ladder_spec=ladder, menu_factory=menu_factory)
    yield result
    result.workflows.saved_snapshot = result.workflows._snapshot()
    result.close()
    app.processEvents()


def test_runway_menu_creates_and_loads_the_profile_used_by_automation(window, monkeypatch):
    menu = window._main_menu
    picker = window.workflows
    assert window._stack.currentWidget() is menu
    assert menu.view_stack.currentWidget() is menu.home_page
    assert picker.active is None
    menu.runway_requested.emit()
    assert window._stack.currentWidget() is picker.picker

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Walking study", True))
    picker.new_profile_button.click()
    profile = picker.active
    assert profile.name == "Walking study"
    assert menu.automated_profiles.profile_state.current_profile_id == profile.id
    assert window.navigation.tool_id == "manual_calibration"

    window._manual_stage_buttons["gait_parameter_analysis"].click()
    window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.setValue(240)
    assert picker.save()
    assert picker.new(name="Another study")
    window._home_button.click()
    menu.runway_requested.emit()
    assert window._stack.currentWidget() is picker.picker
    saved = picker.profile_list.findItems(profile.name, Qt.MatchExactly)[0]
    picker.profile_list.setCurrentItem(saved)
    picker.open_button.click()
    assert picker.active.id == profile.id
    assert window.navigation.tool_id == "gait_parameter_analysis"
    assert window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.value() == 240

    window._automation_run_button.click()
    assert menu.automated_profiles.profile_state.current_profile_id == profile.id


def test_workflows_require_a_profile_before_manual_and_automation(window):
    cards = window._main_menu.home_page.findChildren(QFrame, "SetupChoiceCard")
    ladder_card = next(card for card in cards if card.property("setupAsset") == "ladder-mouse")
    ladder_card.clicked.emit()
    assert window._stack.currentWidget() is window._main_menu
    window._manual_tools_button.click()
    assert window.workflows.new(name="Manual study")
    assert window.navigation.tool_id == "manual_calibration"
    assert window._stack.currentWidget() is window._tool_widgets["manual_calibration"]
    assert window.workflows.close_profile()

    window.routes._open_tool("gait_parameter_analysis")
    assert window._stack.currentWidget() is window.workflows.picker
    assert window._tool_widgets == {}
    assert window.workflows.new(name="Study A")
    assert window.navigation.tool_id == "gait_parameter_analysis"
    assert window.workflows.selector.currentText() == "Study A"
    assert window.workflows.close_profile()
    window.routes._show_automated_pipeline()
    assert window._stack.currentWidget() is window.workflows.picker
    assert window.workflows.new(name="Study B")
    assert window.navigation.automatic_active


def test_profile_restores_settings_pairings_metadata_and_optional_csvs(window):
    assert window.workflows.new(name="Walking session")
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    paths = [FIXTURES / f"{side}.csv" for side in ("left", "right", "bottom")]
    assert all(path.is_file() for path in paths)
    view.inputs._add_csv_paths(paths)
    view.state.manual_view_sets = [AlmaViewCsvSet("M3_session", *paths, StrokeStudyMetadata(animal_id="M3", session_id="day7"))]
    view.inputs._refresh_view_sets()
    view.frame_rate_spin.setValue(239.76)
    view.calibration_method_combo.setCurrentIndex(view.calibration_method_combo.findData("manual"))
    view.pixels_per_cm_spin.setValue(31.3667)
    view.workflow_combo.setCurrentText("ALMA side + rust bottom")
    view.view_offset_spins["right"].setValue(0.12)
    assert window.workflows.save()
    profile_id = window.workflows.active.id
    assert view.import_manifest_button.isHidden()
    window.workflows.close_profile()
    assert window.workflows.open_profile(profile_id, restore_files=False)
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    assert view.frame_rate_spin.value() == 239.76
    assert view.pixels_per_cm_spin.value() == pytest.approx(31.3667, abs=0.001)
    assert view.view_offset_spins["right"].value() == 0.12
    assert view.workflow_combo.currentText() == "ALMA side + rust bottom"
    assert view.state.selected_files == []
    window.workflows.close_profile()
    assert window.workflows.open_profile(profile_id, restore_files=True)
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    assert view.state.selected_files == paths
    assert view.state.view_sets[0].name == "M3_session"
    assert view.state.view_sets[0].metadata.animal_id == "M3"
    assert view.state.view_sets[0].metadata.session_id == "day7"


def test_video_regions_and_incomplete_knee_settings_survive_reopening(window):
    window.workflows.new(name="Camera setup")
    window.routes._open_tool("video_processing")
    video = window._tool_widgets["video_processing"]
    video.preview.set_crop_regions((CropRegion("Left", NormalizedRect(0, 0, 0.4, 1)),))
    video.crf_spin.setValue(23)
    window.routes._open_tool("knee_correction")
    knee = window._tool_widgets["knee_correction"]
    knee.hip_knee_length.setValue(2.25)
    knee.hip_label_combo.addItem("custom_hip", "custom_hip")
    knee.hip_label_combo.setCurrentText("custom_hip")
    assert window.workflows.save()
    profile_id = window.workflows.active.id
    assert window.workflows.active.processing_manifest is not None
    window.workflows.close_profile()
    window.workflows.open_profile(profile_id, restore_files=False)
    window.routes._open_tool("video_processing")
    video = window._tool_widgets["video_processing"]
    assert video.crf_spin.value() == 23
    assert video.controller._current_processing_options().crop_regions[0].name == "Left"
    window.routes._open_tool("knee_correction")
    assert window._tool_widgets["knee_correction"].hip_knee_length.value() == 2.25
    assert window._tool_widgets["knee_correction"].hip_label_combo.currentData() == "custom_hip"


def test_switching_to_a_new_profile_clears_other_workflow_state(window):
    window.workflows.new(name="A")
    window.routes._open_tool("gait_parameter_analysis")
    window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.setValue(42)
    window.workflows.save()
    profile_a = window.workflows.active.id
    window.workflows.new(name="B")
    window.routes._open_tool("gait_parameter_analysis")
    assert window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.value() != 42
    assert window.workflows.active.id != profile_a


def test_newly_opened_tool_does_not_clear_unsaved_edits(window):
    window.workflows.new(name="A")
    window.routes._open_tool("gait_parameter_analysis")
    window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.setValue(42)
    window.routes._open_tool("knee_correction")
    window.workflows.refresh_dirty_state()
    assert window.workflows.status.text() == "Unsaved changes"


def test_switch_cancel_keeps_the_active_profile_and_edits(window, monkeypatch):
    window.workflows.new(name="A")
    profile_a = window.workflows.active.id
    other = window.workflows.use_cases.save("B", None, None, {}, allow_incomplete=True)
    window.routes._open_tool("gait_parameter_analysis")
    window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.setValue(42)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Cancel)
    assert not window.workflows.open_profile(other.id, restore_files=False)
    assert window.workflows.active.id == profile_a
    assert window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.value() == 42


def test_profile_save_as_keeps_the_original_workspace(window):
    window.workflows.new(name="Original")
    original_id = window.workflows.active.id
    window.routes._open_tool("gait_parameter_analysis")
    window._tool_widgets["gait_parameter_analysis"].kinematics_widget.frame_rate_spin.setValue(42)
    assert window.workflows.save(name="Copy")
    assert window.workflows.active.id != original_id
    assert window.workflows.use_cases.load(original_id).workspace_state["pages"] == {}


def test_state_codec_preserves_calibration_geometry_and_rejects_arbitrary_types():
    stick = CalibrationStick("x", 1, CalibrationPoint(0.1, 0.2), CalibrationPoint(0.9, 0.2), (0.5,))
    saved = json.loads(json.dumps(encode_value({"image": (stick,)})))
    assert decode_value(saved) == {"image": (stick,)}
    region = CropRegion("Per-video flip", NormalizedRect(0, 0, 1, 1), True, False, frozenset({"/tmp/first.mp4"}))
    assert decode_value(json.loads(json.dumps(encode_value(region)))) == region
    with pytest.raises(ValueError, match="Unsupported"):
        decode_value({"$type": "arbitrary.import", "fields": {}})


def test_profile_bar_and_csv_actions_fit_a_small_window(window):
    from PySide6.QtTest import QTest
    window.workflows.new(name="Small laptop")
    window.routes._open_tool("gait_parameter_analysis")
    window.resize(1100, 640)
    window.show()
    QTest.qWait(300)
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    assert window.height() == 640
    assert view.view_set_table.geometry().bottom() < view.view_set_status_label.geometry().top()
    assert view.edit_pairing_button.geometry().bottom() < view.file_box.height()
    assert window.workflows.save_button.isVisible()


def test_automation_queue_restore_is_optional_and_missing_files_are_skipped(window, tmp_path):
    window.workflows.new(name="Automation queue")
    videos = [tmp_path / name for name in ("first.mp4", "second.mp4")]
    for path in videos:
        path.touch()
    window.workflows.automatic.queue._add_video_paths(videos)
    assert window.workflows.save()
    profile_id = window.workflows.active.id
    window.workflows.close_profile()
    window.workflows.open_profile(profile_id, restore_files=False)
    assert window.workflows.automatic._video_paths == []
    window.workflows.close_profile()
    videos[1].unlink()
    window.workflows.open_profile(profile_id, restore_files=True)
    assert window.workflows.automatic._video_paths == [videos[0]]


def test_reopening_offers_restore_files_and_settings_only(window, tmp_path, monkeypatch):
    window.workflows.new(name="Reopen choices")
    video = tmp_path / "first.mp4"
    video.touch()
    window.workflows.automatic.queue._add_video_paths([video])
    window.workflows.save()
    profile_id = window.workflows.active.id
    window.workflows.close_profile()
    seen = []
    def choose_settings(dialog):
        seen.extend(button.text() for button in dialog.buttons())
        next(button for button in dialog.buttons() if button.text() == "Settings only").click()
    monkeypatch.setattr(QMessageBox, "exec", choose_settings)
    assert window.workflows.open_profile(profile_id)
    assert "Restore files" in seen and "Settings only" in seen
    assert window.workflows.automatic._video_paths == []


def test_workflow_manifests_stay_hidden_when_switching_analysis_modes(window):
    window.workflows.new(name="One save location")
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    for index in (1, 2, 0):
        view.workflow_combo.setCurrentIndex(index)
        assert view.saved_settings_box.isHidden()
        assert view.export_manifest_button.isHidden()


def test_incomplete_gait_settings_are_saved_without_reusing_a_previous_run_configuration(window):
    window.workflows.new(name="Work in progress")
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    assert window.workflows.save()
    assert window.workflows.active.analysis_manifest is not None
    view.calibration_method_combo.setCurrentIndex(view.calibration_method_combo.findData("map"))
    view.state.calibration_map_path = None
    view.state.calibration_map_pixels_per_cm = None
    assert window.workflows.save()
    assert window.workflows.active.analysis_manifest is None
    assert "Gait settings" in window.workflows.use_cases.missing_requirements(window.workflows.active)
    profile_id = window.workflows.active.id
    window.workflows.close_profile()
    window.workflows.open_profile(profile_id, restore_files=False)
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    assert view.calibration_method_combo.currentData() == "map"


def test_invalid_workspace_replacement_cannot_destroy_a_saved_profile(window):
    window.workflows.new(name="Keep this workflow")
    profile = window.workflows.active
    repository = window.workflows.use_cases.repository
    metadata = repository.root / profile.id / "profile.json"
    original = metadata.read_bytes()
    with pytest.raises(ValueError, match="Unsupported workflow"):
        repository.save(profile.name, None, None, {}, profile_id=profile.id,
                        allow_incomplete=True, workspace_state={"version": 100, "pages": {}})
    assert metadata.read_bytes() == original
    assert repository.load(profile.id).name == profile.name


def test_existing_automation_updates_and_duplication_keep_workspace_settings(window):
    window.workflows.new(name="Original")
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    view.frame_rate_spin.setValue(42)
    window.workflows.save()
    profile = window.workflows.active
    repository = window.workflows.use_cases.repository
    edited = repository.save(profile.name, profile.processing_manifest, profile.calibration_map,
        profile.deeplabcut_models, profile_id=profile.id, analysis_manifest=profile.analysis_manifest, allow_incomplete=True)
    assert edited.workspace_state == profile.workspace_state
    copied = window.workflows.use_cases.duplicate(profile.id, "Copy")
    assert copied.workspace_state == profile.workspace_state
    assert copied.id != profile.id


def test_standalone_rustlab_settings_do_not_silently_run_alma_in_automation(window):
    window.workflows.new(name="Standalone analysis")
    window.routes._open_tool("gait_parameter_analysis")
    view = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    view.workflow_combo.setCurrentIndex(2)
    assert window.workflows.save()
    missing = window.workflows.use_cases.missing_requirements(window.workflows.active)
    assert any("RustLab1 standalone runs in Gait analysis" in item for item in missing)


def test_manual_video_and_ladder_review_reopen_the_saved_video(window, tmp_path):
    window._ladder_spec = replace(window._ladder_spec, enabled=True)
    import cv2
    import numpy as np
    from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange
    video_path = tmp_path / "review.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    for level in (20, 80, 160):
        writer.write(np.full((48, 64, 3), level, np.uint8))
    writer.release()
    window.workflows.new(name="Video review")
    window.routes._open_tool("video_processing")
    video = window._tool_widgets["video_processing"]
    video.sources._add_video_paths([video_path])
    video.state.trim_ranges_by_video[str(video_path)] = [TrimRange(0, 200)]
    video.preview.set_crop_regions((CropRegion("Left", NormalizedRect(0, 0, 0.5, 1), True, False,
                                               frozenset({str(video_path)})),))
    window.routes._open_tool("ladder_analysis")
    ladder = window._tool_widgets["ladder_analysis"]
    ladder.state.video_path = video_path
    ladder.video_edit.setText(str(video_path))
    ladder.mode_combo.setCurrentText("Paired left + right cameras")
    assert window.workflows.save()
    profile_id = window.workflows.active.id
    window.workflows.close_profile()
    window.workflows.open_profile(profile_id, restore_files=True)
    ladder = window._tool_widgets["ladder_analysis"]
    assert ladder._video_capture is not None
    assert ladder.frame_slider.maximum() == 2
    assert ladder.settings_tabs.isTabVisible(1)
    window.routes._open_tool("video_processing")
    video = window._tool_widgets["video_processing"]
    assert video.state.current_video == video_path
    assert video.state.trim_ranges_by_video[str(video_path)] == [TrimRange(0, 200)]
    assert video.controller._current_processing_options().crop_regions[0].flip_horizontal_video_paths == frozenset({str(video_path)})


def test_calibration_measurements_and_settings_survive_without_loading_media(window):
    window.workflows.new(name="Calibration workspace")
    window.routes._open_tool("manual_calibration")
    calibration = window._tool_widgets["manual_calibration"]
    stick = CalibrationStick("x", 1, CalibrationPoint(0, 0), CalibrationPoint(42, 0))
    calibration.state.calibration_sticks_by_media["example.png"] = (stick,)
    calibration.tau_spin.setValue(3.5)
    assert window.workflows.save()
    profile_id = window.workflows.active.id
    assert window.workflows.active.calibration_map is not None
    window.workflows.close_profile()
    window.workflows.open_profile(profile_id, restore_files=False)
    calibration = window._tool_widgets["manual_calibration"]
    assert calibration.state.calibration_sticks_by_media["example.png"] == (stick,)
    assert calibration.tau_spin.value() == 3.5
    assert calibration.media_list.count() == 0
    assert calibration.save_to_gait_button.isEnabled()


def test_save_to_gait_analysis_applies_the_workflow_calibration(window):
    assert window.workflows.new(name="Calibration handoff")
    window.routes._open_tool("gait_parameter_analysis")
    gait = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    gait.frame_rate_spin.setValue(240)
    window.routes._open_tool("manual_calibration")
    calibration = window._tool_widgets["manual_calibration"]
    calibration.state.calibration_sticks_by_media["example.png"] = (
        CalibrationStick("x", 1, CalibrationPoint(0, 0), CalibrationPoint(42, 0)),
    )
    calibration.controller._update_calibration_results()
    assert calibration.save_to_gait_button.isEnabled()
    calibration.save_to_gait_button.click()
    profile = window.workflows.active
    assert window.navigation.tool_id == "gait_parameter_analysis"
    assert gait.settings_tabs.currentWidget() is gait.calibration_tab
    assert gait.calibration_method_combo.currentData() == "map"
    assert gait.state.calibration_map_path == profile.calibration_map
    assert gait.state.calibration_map_pixels_per_cm == pytest.approx(42)
    saved_gait = alma_settings_from_manifest(profile.analysis_manifest, profile.calibration_map)
    assert saved_gait.calibration_method == "map"
    assert saved_gait.calibration_map_path == profile.calibration_map
    assert window.workflows.close_profile()
    assert window.workflows.open_profile(profile.id, restore_files=False)
    gait = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    assert gait.calibration_method_combo.currentData() == "map"
    assert gait.state.calibration_map_path == profile.calibration_map
    assert gait.frame_rate_spin.value() == 240


def test_automation_runs_saved_settings_and_only_prompts_for_edits(window, tmp_path, monkeypatch):
    assert window.workflows.new(name="Run settings")
    window.routes._open_tool("gait_parameter_analysis")
    gait = window._tool_widgets["gait_parameter_analysis"].kinematics_widget
    gait.frame_rate_spin.setValue(120)
    window.routes._show_automated_pipeline()
    automation = window.workflows.automatic
    video = tmp_path / "recording.mp4"
    video.touch()
    automation.queue._add_video_paths([video])
    assert window.workflows.save()
    first_profile = window.workflows.active
    prompts, started = [], []
    response = QMessageBox.Cancel

    def question(_parent, title, *_args):
        prompts.append(title)
        return response

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(automation.profile_use_cases, "missing_requirements", lambda _profile: [])
    monkeypatch.setattr(automation.runs, "_start_pipeline", started.append)
    automation.run_pipeline_button.click()
    assert prompts == []
    assert started == [first_profile]
    assert window.workflows.active is first_profile

    gait.frame_rate_spin.setValue(240)
    automation.run_pipeline_button.click()
    assert prompts == ["Save before running?"]
    assert started == [first_profile]
    assert alma_settings_from_manifest(first_profile.analysis_manifest).frame_rate == 120

    response = QMessageBox.Save
    automation.run_pipeline_button.click()
    assert len(prompts) == 2
    assert len(started) == 2
    assert started[-1] is window.workflows.active
    assert alma_settings_from_manifest(started[-1].analysis_manifest).frame_rate == 240
    assert started[-1].workspace_state["automation_videos"] == [str(video)]
    assert not window.workflows.has_unsaved_changes()


def test_automation_stage_switches_save_without_a_separate_button(window):
    assert window.workflows.new(name="Automatic settings")
    profile_id = window.workflows.active.id
    window.routes._show_automated_profiles()
    widget = window.workflows.automatic
    assert widget.save_profile_button.isHidden()
    widget.include_gait_analysis_button.click()
    widget.include_knee_correction_button.click()
    profile = window.workflows.use_cases.load(profile_id)
    assert not profile.gait_analysis_enabled
    assert profile.knee_correction_enabled


def test_running_automation_keeps_its_profile_assets_until_it_stops(window):
    window.workflows.new(name="Running workflow")
    metadata = window.workflows.use_cases.repository.root / window.workflows.active.id / "profile.json"
    saved = metadata.read_bytes()
    class Worker:
        running = True
        def isRunning(self):
            return self.running
    worker = Worker()
    window.workflows.automatic._pipeline_worker = worker
    try:
        window.workflows.refresh_dirty_state()
        assert not window.workflows.save_button.isEnabled()
        assert not window.workflows.selector.isEnabled()
        assert not window.workflows.save()
        assert metadata.read_bytes() == saved
        worker.running = False
        window.workflows.refresh_dirty_state()
        assert window.workflows.save_button.isEnabled()
    finally:
        window.workflows.automatic._pipeline_worker = None


def test_closing_the_application_stops_profile_polling(window):
    assert window.workflows.timer.isActive()
    window.close()
    assert not window.workflows.timer.isActive()


def test_ladder_marker_choices_apply_when_csv_is_added_after_settings_only_restore(window, tmp_path, monkeypatch):
    window._ladder_spec = replace(window._ladder_spec, enabled=True)
    import pandas as pd
    from PySide6.QtWidgets import QFileDialog, QListWidgetItem
    path = tmp_path / "ladder.csv"
    columns = pd.MultiIndex.from_product([["DLC"], ["pawA", "pawB"], ["x", "y", "likelihood"]])
    pd.DataFrame(1.0, index=range(3), columns=columns).to_csv(path)
    window.workflows.new(name="Ladder markers")
    window.routes._open_tool("ladder_analysis")
    ladder = window._tool_widgets["ladder_analysis"]
    item = QListWidgetItem("pawB")
    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Checked)
    ladder.bodyparts_list.addItem(item)
    assert window.workflows.save()
    profile_id = window.workflows.active.id
    window.workflows.close_profile()
    window.workflows.open_profile(profile_id, restore_files=False)
    ladder = window._tool_widgets["ladder_analysis"]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args, **_kwargs: (str(path), ""))
    ladder.inputs._choose_csv()
    assert ladder.controller._selected_bodyparts() == ["pawB"]


def test_saved_workflows_can_be_renamed_and_deleted_from_the_picker(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    window.workflows.new(name="First name")
    profile_id = window.workflows.active.id
    window.workflows.close_profile()
    window.workflows.profile_list.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("New name", True))
    window.workflows.rename_button.click()
    assert window.workflows.use_cases.load(profile_id).name == "New name"
    window.workflows.profile_list.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.Cancel)
    window.workflows.delete_button.click()
    assert window.workflows.use_cases.load(profile_id).name == "New name"
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.Yes)
    window.workflows.delete_button.click()
    assert window.workflows.use_cases.list_profiles() == []


def test_workflow_search_keeps_hidden_selections_from_opening_and_supports_keyboard(window):
    from PySide6.QtTest import QTest

    window.workflows.new(name="Runway study")
    window.workflows.close_profile()
    window.workflows.new(name="Ladder study")
    window.workflows.close_profile()
    window.show()
    picker = window.workflows
    picker.profile_list.setCurrentRow(0)
    picker.profile_search.setText("RUNWAY")
    assert not picker.open_button.isEnabled()
    assert not picker.delete_button.isEnabled()
    picker.profile_list.setCurrentRow(1)
    assert picker.open_button.isEnabled()
    picker.profile_search.setText("no matching workflow")
    assert picker.empty_label.isVisible()
    assert not picker.open_button.isEnabled()
    picker.profile_search.clear()
    picker.profile_list.setCurrentRow(1)
    picker.profile_list.setFocus()
    QTest.keyClick(picker.profile_list, Qt.Key_Return)
    assert picker.active.name == "Runway study"
