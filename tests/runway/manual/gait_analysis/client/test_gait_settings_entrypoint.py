"""Existing launchers must reach the controls used by preview and analysis."""

import json

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from dlc_gait_assembly.app import app_bootstrap
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import STRIDE_METHODS


def test_existing_module_entrypoint_delegates_to_current_app(monkeypatch):
    import runpy

    calls = []
    monkeypatch.setattr(app_bootstrap, "main", lambda: calls.append("current") or 7)
    with pytest.raises(SystemExit) as result:
        runpy.run_module("dlc_gait_assembly", run_name="__main__")
    assert result.value.code == 7
    assert calls == ["current"]


@pytest.fixture
def launched_gait_page():
    app = QApplication.instance() or QApplication([])
    specs, _ = app_bootstrap.build_tool_specs()
    spec = next(spec for spec in specs if spec.id == "gait_parameter_analysis")
    page = spec.widget_factory()
    page.resize(1400, 1000)
    page.show()
    app.processEvents()
    yield page.kinematics_widget
    page.close()
    app.processEvents()


def test_main_app_exposes_dedicated_detection_and_calibration_tabs(launched_gait_page):
    view = launched_gait_page
    view.settings_tabs.setCurrentWidget(view.stride_detection_tab)
    assert view.stride_detection_tab.isAncestorOf(view.stride_method_combo)
    assert view.calibration_tab.isAncestorOf(view.view_calibration_box)
    assert view.stride_method_combo.isVisible()
    assert not hasattr(view, "continuous_strides_spin")
    assert view.settings_section_rows[0].tabText(2) == "Stride detection"
    assert tuple(view.stride_method_combo.itemText(i) for i in range(len(STRIDE_METHODS))) == tuple(STRIDE_METHODS)
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    assert view.stride_method_combo.isEnabled()
    view.state.preview_validity.complete()
    view.stride_method_combo.setCurrentText("Bottom paw speed")
    assert not view.state.preview_validity.ready
    assert view.setup._collect_settings().stride_detection_method == "Bottom paw speed"
    view.edit_view_calibration_button.click()
    assert view.settings_tabs.currentWidget() is view.calibration_tab
    view.edit_view_calibration_button.click()
    assert view.settings_tabs.currentWidget() is view.calibration_tab
    view.analysis_type_combo.setCurrentText("Treadmill")
    assert not view.stride_method_combo.isEnabled()
    assert "Choose Spontaneous walking" in view.stride_method_description.text()
    view.workflow_combo.setCurrentText("RustLab1 standalone (three-view)")
    assert not view.stride_method_combo.isVisible()
    assert not view.settings_tabs.isTabVisible(view.settings_tabs.indexOf(view.stride_detection_tab))


def test_short_gap_default_is_visible_and_strict_setting_is_explicit(launched_gait_page):
    view = launched_gait_page
    view.settings_tabs.setCurrentWidget(view.stride_detection_tab)
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    assert view.stride_detection_tab.isAncestorOf(view.detection_gap_spin)
    assert view.detection_gap_spin.isVisible()
    assert view.detection_gap_spin.text() == "Auto (up to 50 ms)"
    assert view.setup._collect_settings().max_interpolation_gap_frames == -1
    view.state.preview_validity.complete()
    view.detection_gap_spin.setValue(0)
    assert not view.state.preview_validity.ready
    assert "entire stride" in view.detection_gap_note.text()
    assert view.setup._collect_settings().max_interpolation_gap_frames == 0


def test_each_visible_map_button_imports_only_its_camera(launched_gait_page, tmp_path, monkeypatch):
    view = launched_gait_page
    view.input_mode_combo.setCurrentIndex(0)
    for camera, scale in (("left", 30.0), ("right", 60.0), ("bottom", 90.0)):
        path = tmp_path / f"{camera}.json"
        path.write_text(json.dumps({"conversion_factor_map": {"overall": {"pixels_per_centimeter": scale}}}))
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_, selected=path: (str(selected), ""))
        view.state.preview_validity.complete()
        view.view_map_buttons[camera].click()
        assert not view.state.preview_validity.ready
    settings = view.setup._collect_settings()
    assert settings.view_calibration["left"]["pixels_per_cm"] == 30.0
    assert settings.view_calibration["right"]["pixels_per_cm"] == 60.0
    assert settings.view_calibration["bottom"]["x_pixels_per_cm"] == 90.0
    assert settings.view_calibration["bottom"]["y_pixels_per_cm"] == 90.0
    for camera in ("left", "right", "bottom"):
        assert settings.view_calibration[camera]["map_path"] == str(tmp_path / f"{camera}.json")


def test_comparison_choice_keeps_rustlab_settings_without_a_display_limit(launched_gait_page, monkeypatch):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_use_cases import StrideComparisonResults
    from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_stride_comparison_dialog import (
        StrideComparisonDialog,
    )

    view = launched_gait_page
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    view.state.preview_validity.begin()
    monkeypatch.setattr(StrideComparisonDialog, "exec", lambda self: 1)
    monkeypatch.setattr(StrideComparisonDialog, "selected_method", lambda self: "RustLab1 (bottom paw)")
    results = StrideComparisonResults((("RustLab1 (bottom paw)", (), "Test"),))
    view.settings_tabs.setCurrentWidget(view.stride_detection_tab)
    view.controller._show_stride_comparison(results)
    assert not hasattr(view, "continuous_strides_spin")
    assert view.comparison_rustlab_box.isVisible()
    view.comparison_rustlab_spins["stance_speed_threshold_px_frame"].setValue(3.5)
    assert view.setup._collect_settings().stance_speed_threshold_px_frame == 3.5
    view.state.preview_validity.complete()
    view.comparison_rustlab_spins["minimum_stance_frames"].setValue(3)
    assert not view.state.preview_validity.ready


def test_context_model_control_and_manifest_round_trip(launched_gait_page, tmp_path):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import (
        CONTEXT_MIXTURE_METHOD,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        alma_settings_from_manifest,
        write_analysis_manifest,
    )

    view = launched_gait_page
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    view.settings_tabs.setCurrentWidget(view.stride_detection_tab)
    view.stride_method_combo.setCurrentText(CONTEXT_MIXTURE_METHOD)
    assert view.mixture_context_box.isVisible()
    assert view.mixture_context_spin.value() == 60
    view.state.preview_validity.complete()
    view.mixture_context_spin.setValue(90)
    assert not view.state.preview_validity.ready
    settings = view.setup._collect_settings()
    assert settings.mixture_context_ms == 90
    destination = tmp_path / "settings.json"
    write_analysis_manifest(destination, settings)
    restored = alma_settings_from_manifest(destination)
    assert restored.stride_detection_method == CONTEXT_MIXTURE_METHOD
    assert restored.mixture_context_ms == 90
    payload = json.loads(destination.read_text())
    del payload["analysis_settings"]["mixture_context_ms"]
    destination.write_text(json.dumps(payload))
    assert alma_settings_from_manifest(destination).mixture_context_ms == 60
    view.stride_method_combo.setCurrentText("Speed mixture (GMM)")
    assert not view.mixture_context_box.isVisible()


def test_comparison_notes_do_not_resize_the_stickplot(launched_gait_page):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import (
        CONTEXT_MIXTURE_METHOD,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_stride_comparison_dialog import (
        StrideComparisonDialog,
    )

    plot = (
        (
            "Left · stick plot",
            b'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="600"><path d="M 0 0 L 1400 600"/></svg>',
        ),
    )
    results = (
        ("Speed mixture (GMM)", plot, "Short result"),
        (CONTEXT_MIXTURE_METHOD, plot, "\n".join(["Long detailed result"] * 20)),
    )
    dialog = StrideComparisonDialog(results, "Speed mixture (GMM)", launched_gait_page)
    dialog.show()
    QApplication.processEvents()
    size = dialog.preview.size()
    dialog.methods.setCurrentText(CONTEXT_MIXTURE_METHOD)
    QApplication.processEvents()
    assert dialog.preview.size() == size
    dialog.close()


def test_output_destination_picker_and_bundle_defaults(launched_gait_page, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult

    view = launched_gait_page
    view.settings_tabs.setCurrentIndex(6)
    QApplication.processEvents()
    assert view.export_folder_edit.isVisible()
    assert all(
        control.isChecked() and control.isVisible()
        for control in (view.stickplot_checkbox, view.alma_representations_checkbox, view.rustlab1_checkbox)
    )
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    view.export_folder_button.click()
    assert view.output_folder_edit.text() == view.export_folder_edit.text() == str(tmp_path)
    path = tmp_path / "gait_parameters.csv"
    path.write_text("recording,gait_cycle\ntest,1\n")
    view.controller._output_results_ready((AlmaRunResult(path, (path,), ()),))
    assert view.open_results_button.isEnabled()
    assert view._saved_results_folder == tmp_path
    assert "Saved 1 files" in view.export_summary_label.text()


def test_camera_timing_is_visible_invalidates_preview_and_round_trips(launched_gait_page, tmp_path):
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        alma_settings_from_manifest,
        write_analysis_manifest,
    )

    view = launched_gait_page
    view.settings_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert view.view_timing_box.isVisible()
    for side, fps, offset in (("left", 120.0, 0.0), ("right", 240.0, 0.25), ("bottom", 100.0, -0.1)):
        view.state.preview_validity.complete()
        view.view_fps_spins[side].setValue(fps)
        assert not view.state.preview_validity.ready
        view.state.preview_validity.complete()
        view.view_offset_spins[side].setValue(offset or 0.001)
        assert not view.state.preview_validity.ready
        view.view_offset_spins[side].setValue(offset)
    settings = view.setup._collect_settings()
    assert settings.view_timing["bottom"] == {"frame_rate": 100.0, "offset_s": -0.1}
    path = tmp_path / "timing.json"
    write_analysis_manifest(path, settings)
    assert alma_settings_from_manifest(path).view_timing == settings.view_timing
    view.workflow_combo.setCurrentText("RustLab1 standalone (three-view)")
    assert not view.view_timing_box.isVisible()


def test_results_preview_keeps_recordings_and_sides_separate(launched_gait_page, tmp_path, monkeypatch):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
    from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_preview_worker import ParameterFiguresThread
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures import gait_parameter_figures

    paths = []
    for recording in ("one", "two"):
        for filename in (
            "left_stride_parameters.csv",
            "right_stride_parameters.csv",
            "general_parameters/general_parameters.csv",
        ):
            path = tmp_path / recording / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"recording,value\n{recording},1\n")
            paths.append(path)
    report = tmp_path / "export_report.txt"
    report.write_text("Export complete")
    view = launched_gait_page
    view.controller._output_results_ready((AlmaRunResult(paths[0], (*paths, report), ()),))
    assert view._saved_results_folder == tmp_path
    assert view._parameter_csv_paths == tuple(paths)
    seen, ready, failed = [], [], []

    def pages(table, **_):
        seen.append(table)
        return [("test", b"<svg/>")]

    monkeypatch.setattr(gait_parameter_figures, "parameter_figure_pages", pages)
    worker = ParameterFiguresThread(view._parameter_csv_paths, reader=view.analysis.results)
    worker.figures_ready.connect(ready.append)
    worker.figures_failed.connect(failed.append)
    worker.run()
    assert not failed and len(seen) == 6
    assert all(len(t) == 1 and t["recording"].nunique() == 1 for t in seen)
    assert len({label for label, _ in ready[0]}) == 6


def test_import_manifest_restores_settings_without_replacing_inputs(launched_gait_page, tmp_path, monkeypatch):
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        write_analysis_manifest,
    )

    view = launched_gait_page
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    view.stride_method_combo.setCurrentText("Speed mixture (GMM)")
    view.frame_rate_spin.setValue(239.8)
    view.view_scale_spins["left"].setValue(42.0)
    view.view_scale_spins["right"].setValue(84.0)
    view.bottom_x_pixels_per_cm_spin.setValue(50.0)
    view.bottom_y_pixels_per_cm_spin.setValue(51.0)
    view.view_offset_spins["bottom"].setValue(0.125)
    view.view_fps_spins["right"].setValue(240.0)
    view.state.view_label_mappings = {"recording": {"left": {"back_toe": "toe"}}}
    expected = view.setup._collect_settings()
    manifest = tmp_path / "analysis_manifest.json"
    write_analysis_manifest(manifest, expected)
    view.frame_rate_spin.setValue(100.0)
    view.view_scale_spins["left"].setValue(10.0)
    view.view_offset_spins["bottom"].setValue(0.0)
    view.state.view_label_mappings = {}
    view.state.preview_validity.complete()
    output = view.output_folder_edit.text()
    selected = list(view.state.selected_files)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(manifest), ""))
    view.import_manifest_button.click()
    restored = view.setup._collect_settings()
    assert restored == expected
    assert view.output_folder_edit.text() == output
    assert view.state.selected_files == selected
    assert not view.state.preview_validity.ready
    assert "Imported analysis_manifest.json" in view.status_label.text()


@pytest.mark.parametrize("payload", ["not json", '{"manifest_type": "other"}'])
def test_bad_manifest_does_not_change_settings(launched_gait_page, tmp_path, monkeypatch, payload):
    from PySide6.QtWidgets import QMessageBox

    view = launched_gait_page
    original = view.setup._collect_settings()
    path = tmp_path / "invalid.json"
    path.write_text(payload)
    warnings = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    view.import_manifest_button.click()
    assert warnings and view.setup._collect_settings() == original


def test_import_restores_context_controls_and_custom_labels(launched_gait_page, tmp_path, monkeypatch):
    from dataclasses import replace
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import (
        CONTEXT_MIXTURE_METHOD,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        write_analysis_manifest,
    )

    view = launched_gait_page
    settings = replace(
        view.setup._collect_settings(),
        analysis_type="Spontaneous walking",
        stride_detection_method=CONTEXT_MIXTURE_METHOD,
        mixture_context_ms=90.0,
        custom_bodypart_mapping={"back_toe": "toe", "my_knee": "knee"},
    )
    path = tmp_path / "context.json"
    write_analysis_manifest(path, settings)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(path), ""))
    view.import_manifest_button.click()
    view.settings_tabs.setCurrentWidget(view.stride_detection_tab)
    QApplication.processEvents()
    assert view.mixture_context_box.isVisible()
    assert view.mixture_context_spin.value() == 90.0
    assert view.setup._collect_settings().custom_bodypart_mapping == settings.custom_bodypart_mapping


def test_out_of_range_manifest_is_rejected_before_any_changes(launched_gait_page, tmp_path, monkeypatch):
    from dataclasses import replace
    from PySide6.QtWidgets import QMessageBox
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        write_analysis_manifest,
    )

    view = launched_gait_page
    before = view.setup._collect_settings()
    path = tmp_path / "bad-values.json"
    write_analysis_manifest(path, replace(before, frame_rate=-10.0, analysis_type="Spontaneous walking"))
    warnings = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    view.import_manifest_button.click()
    assert warnings and view.setup._collect_settings() == before
