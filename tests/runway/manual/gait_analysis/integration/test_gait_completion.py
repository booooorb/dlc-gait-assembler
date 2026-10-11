"""End-to-end regressions for calibration and detector/figure integration."""

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.app.app_bootstrap import create_gait_preview
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import bottom_detection
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import calculate_recording_table
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
    camera_map_scales,
    resolve_calibration_settings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter


def write_map(path, scale):
    path.write_text(json.dumps({"conversion_factor_map": {"overall": {"pixels_per_centimeter": scale}}}))
    return path


def test_map_only_settings_apply_to_export_and_preview(tmp_path, alma_fixtures_dir):
    source = alma_fixtures_dir / "alma_edge_cases_filtered.csv"
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        input_mode="Single side view",
        calibration_method="manual",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        no_outlier_filter=True,
    )
    baseline, _ = calculate_recording_table(source, settings, GaitResultWriter(), pd)
    map_settings = replace(settings, pixels_per_cm=None, calibration_map_path=write_map(tmp_path / "map.json", 25.0))
    calibrated, _ = calculate_recording_table(source, map_settings, GaitResultWriter(), pd)
    np.testing.assert_allclose(calibrated["stride length (cm)"], baseline["stride length (cm)"] * 2)
    plots, _, messages = create_gait_preview().prepare((("Left", source),), map_settings)
    assert len(plots) == 1
    assert any("Calibration: 25.0 px/cm" in message for message in messages)


def test_selected_profile_map_replaces_shared_snapshot_only(tmp_path):
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        alma_settings_from_manifest,
        write_analysis_manifest,
    )

    manifest = write_analysis_manifest(
        tmp_path / "settings.json", AlmaSettings(pixels_per_cm=50.0, view_calibration={"left": {"pixels_per_cm": 80.0}})
    )
    loaded = alma_settings_from_manifest(manifest, write_map(tmp_path / "map.json", 25.0))
    resolved = resolve_calibration_settings(loaded)
    assert resolved.pixels_per_cm == 25.0
    assert resolved.view_calibration["left"]["pixels_per_cm"] == 80.0


def test_analysis_worker_accepts_map_only_scale(tmp_path):
    from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_worker import AlmaAnalysisThread

    called, outcomes = [], []

    def analyze(*args, **kwargs):
        called.append(args[2])
        return []

    settings = AlmaSettings(calibration_method="manual", pixels_per_cm=None, calibration_map_path=tmp_path / "map.json")
    worker = AlmaAnalysisThread([], tmp_path, settings, analyze=analyze)
    worker.analysis_completed.connect(lambda success, message: outcomes.append(success))
    worker.run()
    assert called == [settings]
    assert outcomes == [True]


def test_saved_camera_maps_and_bottom_axes_are_independent(tmp_path):
    path = tmp_path / "cameras.json"
    path.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "views": {
                        "1": {"pixels_per_centimeter": 30.0},
                        "2": {"recommended_x_centimeters_per_pixel": 0.01, "recommended_y_centimeters_per_pixel": 0.02},
                    }
                }
            }
        )
    )
    resolved = resolve_calibration_settings(
        AlmaSettings(
            view_calibration={
                "left": {"map_path": str(path), "source": "view 1"},
                "bottom": {"map_path": str(path), "view_index": 2},
                "right": {"map_path": "/unavailable/snapshot.json", "pixels_per_cm": 80.0},
            }
        )
    )
    assert resolved.view_calibration["left"]["pixels_per_cm"] == 30.0
    assert resolved.view_calibration["right"]["pixels_per_cm"] == 80.0
    assert resolved.view_calibration["bottom"]["x_pixels_per_cm"] == 100.0
    assert resolved.view_calibration["bottom"]["y_pixels_per_cm"] == 50.0
    with pytest.raises(ValueError, match="no view 3"):
        camera_map_scales(path, 3)
    with pytest.raises(ValueError, match="Choose the camera"):
        resolve_calibration_settings(AlmaSettings(view_calibration={"left": {"map_path": str(path)}}))
    # Switching back to reference calibration must not reactivate an old imported map.
    reference = AlmaSettings(calibration_method="reference", calibration_map_path=tmp_path / "removed.json")
    assert resolve_calibration_settings(reference).pixels_per_cm is None


def test_reference_segment_is_estimated_per_side_and_shared_with_post_features(tmp_path, alma_fixtures_dir):
    left = alma_fixtures_dir / "alma_edge_cases_filtered.csv"
    data = pd.read_csv(left, header=[0, 1, 2])
    for column in data:
        if column[-1] in ("x", "y"):
            data[column] *= 2
    right = tmp_path / "right.csv"
    data.to_csv(right, index=False)
    bottom = tmp_path / "bottom.csv"
    pd.DataFrame(
        {
            ("DLC", paw, coord): np.ones(len(data))
            for paw in ("lhpaw", "rhpaw", "lfpaw", "rfpaw")
            for coord in ("x", "y", "likelihood")
        }
    ).to_csv(bottom, index=False)
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        pixels_per_cm=None,
        calibration_method="reference",
        likelihood_threshold=0.0,
        no_outlier_filter=True,
    )
    left_result = calculate_alma_recording(pd.read_csv(left, header=[1, 2]), settings)
    right_result = calculate_alma_recording(pd.read_csv(right, header=[1, 2]), settings)
    assert right_result[1].attrs["pixels_per_cm"] == pytest.approx(left_result[1].attrs["pixels_per_cm"] * 2)
    item = AlmaViewCsvSet("same mouse, two scales", left, right, bottom)
    table, _ = calculate_recording_table(item, settings, GaitResultWriter(), pd)
    np.testing.assert_allclose(table["left__stride length (cm)"], table["right__stride length (cm)"], equal_nan=True)
    np.testing.assert_allclose(table["l-back-ankle__Movement"], table["r-back-ankle__Movement"], equal_nan=True)
    np.testing.assert_allclose(
        table["left_knee_vertical_excursion"], table["right_knee_vertical_excursion"], equal_nan=True
    )


def bottom_walk(count):
    phase = np.arange(count) % 40
    x = (np.arange(count) // 40) * 20.0 + np.where(phase < 20, 0.0, phase - 20.0)
    return pd.DataFrame(
        {("LH_paw", "x"): x, ("LH_paw", "y"): np.full(count, 100.0), ("LH_paw", "likelihood"): np.ones(count)}
    )


def test_bottom_diagnostic_uses_bottom_signal_and_missing_coordinates_are_excluded(alma_fixtures_dir):
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_detection_figure import (
        render_detection_figure,
    )

    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    bottom = bottom_walk(len(raw))
    bottom.loc[80:105, ("LH_paw", "x")] = np.nan
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        stride_detection_method="Bottom paw speed",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        max_interpolation_gap_frames=3,
        no_outlier_filter=True,
    )
    trace = {}
    detection = bottom_detection(bottom, "left", settings, diagnostics=trace)
    assert all(not (start <= 105 and end >= 80) for start, end in zip(detection[1], detection[2], strict=True))
    result = calculate_alma_recording(raw, settings, cycle_detection=detection, detection_diagnostics=trace)
    svg = render_detection_figure(result[0], result[1], raw, settings, "Left").decode()
    assert "Bottom left hind paw speed" in svg
    assert "Stance-entry threshold" in svg and "Excluded tracking gap" in svg
    assert "Side toe: raw" not in svg


def test_bottom_image_height_cannot_change_side_drag_measurements(alma_fixtures_dir):
    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    bottom = bottom_walk(len(raw))
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        stride_detection_method="Bottom paw speed",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        no_outlier_filter=True,
    )
    first = calculate_alma_recording(raw, settings, cycle_detection=bottom_detection(bottom, "left", settings))[0]
    bottom[("LH_paw", "y")] += 10000
    second = calculate_alma_recording(raw, settings, cycle_detection=bottom_detection(bottom, "left", settings))[0]
    assert len(first) > 0
    pd.testing.assert_frame_equal(first, second)


def test_parameter_figure_worker_keeps_ui_responsive(tmp_path, monkeypatch):
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_preview_worker import ParameterFiguresThread

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "gait_parameters.csv"
    pd.DataFrame({"left__stride length (cm)": [1.0, np.nan, 3.0]}).to_csv(source, index=False)
    from dlc_gait_assembly.app.app_bootstrap import create_gait_result_reader

    worker = ParameterFiguresThread(source, reader=create_gait_result_reader())
    loop = QEventLoop()
    pages, errors, ticks = [], [], []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    worker.figures_ready.connect(pages.append)
    worker.figures_failed.connect(errors.append)
    worker.finished.connect(loop.quit)
    timer.start(5)
    worker.start()
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    worker.wait(1000)
    timer.stop()
    assert not worker.isRunning()
    assert not errors
    assert ticks and len(pages[0]) == 1
    assert b"n=2/3 valid" in pages[0][0][1]
    app.processEvents()
