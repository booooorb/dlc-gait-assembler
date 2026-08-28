from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.gui.gait_analysis.settings import MULTI_SIDE_VIEW_MODE_LABEL
from dlc_gait_assembly.gui.gait_analysis.window import (
    ALMA_WORKFLOW_LABEL,
    RUSTLAB1_WORKFLOW_LABEL,
    AlmaKinematicsWidget,
)
from dlc_gait_assembly.gui.gait_analysis.workers import RustLab1AnalysisThread
from dlc_gait_assembly.services.pipeline.alma import AlmaViewCsvSet
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RustLab1RunResult,
    RustLab1StandaloneSettings,
)


class _Signal:
    def connect(self, *_args):
        pass


def _write_minimal_dlc_csv(path: Path) -> None:
    path.write_text(
        "scorer,a,a,a\nbodyparts,toe,toe,toe\ncoords,x,y,likelihood\n",
        encoding="utf-8",
    )


def _write_dlc_labels(path: Path, labels: tuple[str, ...]) -> None:
    scorer = ["scorer", *("model" for _label in labels for _coord in range(3))]
    bodyparts = ["bodyparts", *(label for label in labels for _coord in range(3))]
    coords = ["coords", *(coord for _label in labels for coord in ("x", "y", "likelihood"))]
    path.write_text(
        "\n".join(",".join(row) for row in (scorer, bodyparts, coords)) + "\n",
        encoding="utf-8",
    )


def test_gait_analysis_exposes_separate_three_view_rustlab1_workflow():
    app = QApplication.instance() or QApplication([])
    widget = AlmaKinematicsWidget()

    widget.workflow_combo.setCurrentText(RUSTLAB1_WORKFLOW_LABEL)
    app.processEvents()

    assert widget.input_mode_combo.currentText() == MULTI_SIDE_VIEW_MODE_LABEL
    assert not widget.input_mode_combo.isEnabled()
    assert not widget.analysis_type_combo.isEnabled()
    assert widget.input_mode_combo.isHidden()
    assert widget.input_mode_label.isHidden()
    assert widget.analysis_type_combo.isHidden()
    assert widget.analysis_type_label.isHidden()
    assert widget.setup_box.title() == "RustLab1 recording"
    assert widget.speed_box.title() == "Recording timing"
    assert not widget.settings_tabs.isTabVisible(2)
    assert not widget.settings_tabs.isTabVisible(4)
    assert widget.settings_tabs.tabText(3) == "Stride QC"
    assert not widget.rustlab_detector_box.isHidden()
    assert widget.filter_box.isHidden()
    assert widget.stroke_filter_box.isHidden()
    assert widget.output_options_box.isHidden()
    assert widget.preview_button.text() == "1. Generate RustLab1 stride preview"
    assert widget.run_button.text() == "2. Run RustLab1 analysis"
    assert widget.export_manifest_button.isHidden()
    assert widget.rustlab1_checkbox.isHidden()
    assert not widget.rustlab_standalone_figures_checkbox.isHidden()
    assert widget.bottom_y_pixels_per_cm_spin.isHidden()
    assert not widget.bottom_x_pixels_per_cm_spin.isHidden()
    visible_sources = {
        definition.source
        for definition, item in widget.parameter_selection._items
        if not item.isHidden()
    }
    assert visible_sources == {"RustLab1"}
    settings = widget._collect_rustlab1_settings()
    assert settings.reference_paw == "d-back-left"
    assert settings.stance_speed_threshold_px_frame == 7.0
    assert settings.maximum_tracking_speed_px_frame == 100.0
    assert settings.likelihood_threshold == 0.95
    assert settings.minimum_complete_strides == 1

    widget.rustlab_filter_cutoff_spin.setValue(8.0)
    widget.filter_cutoff_spin.setValue(3.0)
    widget.rustlab_max_tracking_speed_spin.setValue(125.0)
    widget.rustlab_min_stance_spin.setValue(2)
    widget.rustlab_min_swing_spin.setValue(3)
    widget.rustlab_min_strides_spin.setValue(4)
    widget.bottom_x_pixels_per_cm_spin.setValue(31.367)
    widget.rustlab_standalone_figures_checkbox.setChecked(False)
    configured = widget._collect_rustlab1_settings()
    assert configured.filter_cutoff == 8.0
    assert configured.maximum_tracking_speed_px_frame == 125.0
    assert configured.minimum_stance_frames == 2
    assert configured.minimum_swing_frames == 3
    assert configured.minimum_complete_strides == 4
    assert configured.view_calibration == {
        "bottom": {"x_pixels_per_cm": pytest.approx(31.367)}
    }
    assert configured.generate_figures is False

    widget.frame_rate_spin.setValue(20.0)
    assert widget.rustlab_filter_cutoff_spin.maximum() == pytest.approx(9.9)
    assert widget.rustlab_filter_cutoff_spin.value() <= 9.9
    widget.rustlab_stance_speed_spin.setValue(15.0)
    assert widget.rustlab_max_tracking_speed_spin.minimum() == pytest.approx(15.1)

    widget.workflow_combo.setCurrentText(ALMA_WORKFLOW_LABEL)
    app.processEvents()

    assert widget.input_mode_combo.isEnabled()
    assert widget.analysis_type_combo.isEnabled()
    assert not widget.input_mode_combo.isHidden()
    assert not widget.analysis_type_combo.isHidden()
    assert widget.settings_tabs.isTabVisible(2)
    assert widget.settings_tabs.isTabVisible(4)
    assert widget.settings_tabs.tabText(3) == "Filters"
    assert widget.rustlab_detector_box.isHidden()
    assert not widget.filter_box.isHidden()
    assert not widget.output_options_box.isHidden()
    assert widget.run_button.text() == "2. Run gait analysis"
    assert not widget.export_manifest_button.isHidden()
    assert not widget.rustlab1_checkbox.isHidden()
    assert widget.rustlab_standalone_figures_checkbox.isHidden()
    assert not widget.bottom_y_pixels_per_cm_spin.isHidden()
    assert any(
        definition.source == "ALMA" and not item.isHidden()
        for definition, item in widget.parameter_selection._items
    )
    widget.close()
    app.processEvents()


def test_standalone_gui_routes_preview_and_run_only_to_rustlab1(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    captured: dict[str, object] = {}

    class _PreviewThread:
        progress_updated = _Signal()
        log_message = _Signal()
        preview_ready = _Signal()
        preview_failed = _Signal()
        finished = _Signal()

        def __init__(self, view_set, settings, _alma_root):
            captured["preview_view_set"] = view_set
            captured["preview_settings"] = settings

        def start(self):
            captured["preview_started"] = True

        def isRunning(self):
            return False

    class _AnalysisThread:
        progress_updated = _Signal()
        log_message = _Signal()
        results_ready = _Signal()
        analysis_completed = _Signal()
        finished = _Signal()

        def __init__(self, view_sets, output_folder, settings, _alma_root):
            captured["run_view_sets"] = view_sets
            captured["output_folder"] = output_folder
            captured["run_settings"] = settings

        def start(self):
            captured["run_started"] = True

        def isRunning(self):
            return False

    monkeypatch.setattr(
        "dlc_gait_assembly.gui.gait_analysis.window.RustLab1PreviewThread",
        _PreviewThread,
    )
    monkeypatch.setattr(
        "dlc_gait_assembly.gui.gait_analysis.window.RustLab1AnalysisThread",
        _AnalysisThread,
    )
    widget = AlmaKinematicsWidget()
    widget.workflow_combo.setCurrentText(RUSTLAB1_WORKFLOW_LABEL)
    paths = [
        tmp_path / "mouse_left.csv",
        tmp_path / "mouse_right.csv",
        tmp_path / "mouse_bottom.csv",
    ]
    for path in paths:
        _write_minimal_dlc_csv(path)
    widget._add_csv_paths(paths)
    widget._missing_rustlab1_bodyparts = lambda *_args: []
    widget.rustlab_reference_paw_combo.setCurrentText("Right hind paw")

    widget._generate_stickplot_preview()

    assert captured["preview_started"] is True
    assert captured["preview_view_set"].name == "mouse"
    assert captured["preview_settings"].reference_paw == "d-back-right"

    widget._stickplot_preview_ready = True
    widget.output_folder_edit.setText(str(tmp_path / "rustlab-results"))
    widget._run_analysis()

    assert captured["run_started"] is True
    assert [view_set.name for view_set in captured["run_view_sets"]] == ["mouse"]
    assert captured["output_folder"] == (tmp_path / "rustlab-results").resolve()
    assert captured["run_settings"].reference_paw == "d-back-right"
    widget.close()
    app.processEvents()


def test_rustlab1_reference_calibration_requires_segment_on_either_side(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    widget = AlmaKinematicsWidget()
    left = tmp_path / "mouse_left.csv"
    right = tmp_path / "mouse_right.csv"
    bottom = tmp_path / "mouse_bottom.csv"
    side_labels = ("ankle", "toe", "hip", "iliac crest")
    _write_dlc_labels(left, side_labels)
    _write_dlc_labels(right, side_labels)
    _write_dlc_labels(bottom, ("center back", "back left", "back right"))
    view_set = AlmaViewCsvSet("mouse", left, right, bottom)
    settings = RustLab1StandaloneSettings(
        limb_scope="Hindlimb",
        calibration_method="reference",
        reference_segment="hip_knee",
    )

    missing = widget._missing_rustlab1_bodyparts(view_set, settings)
    assert "left or right reference segment hip_knee" in missing

    _write_dlc_labels(right, (*side_labels, "knee"))
    missing = widget._missing_rustlab1_bodyparts(view_set, settings)
    assert "left or right reference segment hip_knee" not in missing
    widget.close()
    app.processEvents()


def test_rustlab1_worker_emits_standalone_results(tmp_path, monkeypatch):
    view_set = AlmaViewCsvSet(
        "mouse",
        tmp_path / "mouse_left.csv",
        tmp_path / "mouse_right.csv",
        tmp_path / "mouse_bottom.csv",
    )
    result = RustLab1RunResult(
        input_file=view_set.bottom_csv,
        output_files=(tmp_path / "mouse_rustlab1_strides.csv",),
    )
    captured = {}

    def fake_run(view_sets, output_folder, settings, alma_root, progress_callback=None):
        captured["view_sets"] = view_sets
        captured["output_folder"] = output_folder
        captured["settings"] = settings
        captured["alma_root"] = alma_root
        progress_callback(1, 1, "RustLab1: processing mouse")
        return [result]

    monkeypatch.setattr(
        "dlc_gait_assembly.gui.gait_analysis.workers.run_rustlab1_analysis",
        fake_run,
    )
    settings = RustLab1StandaloneSettings(reference_paw="d-back-right")
    worker = RustLab1AnalysisThread(
        [view_set],
        tmp_path / "output",
        settings,
        tmp_path / "ALMA",
    )
    emitted_results = []
    completions = []
    progress = []
    worker.results_ready.connect(emitted_results.append)
    worker.analysis_completed.connect(
        lambda success, message: completions.append((success, message))
    )
    worker.progress_updated.connect(lambda value, text: progress.append((value, text)))

    worker.run()

    assert captured["view_sets"] == [view_set]
    assert captured["settings"] is settings
    assert emitted_results == [(result,)]
    assert progress[-1] == (100, "RustLab1 analysis complete.")
    assert completions == [
        (True, f"RustLab1 analysis complete. Results saved to:\n{tmp_path / 'output'}"),
    ]
