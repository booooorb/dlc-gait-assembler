from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    bottom_detection,
    detect_strides,
    trusted_samples,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import calculate_recording_table
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter


def variable_speed_walk():
    lengths = (30, 36, 44, 32, 50, 40, 36, 30)
    x, y = [], []
    for k, n in enumerate(lengths):
        stance = n // 2
        x.extend([k * 20.0] * stance + list(k * 20.0 + np.linspace(0, 20, n - stance)))
        y.extend([100.0] * stance + list(100.0 - 20 * np.sin(np.linspace(0, np.pi, n - stance))))
    return np.array(x), np.array(y), np.cumsum((0, *lengths))


@pytest.mark.parametrize("method", ["Adaptive paw speed", "Bottom paw speed"])
def test_variable_speed_walk_keeps_complete_cycles_and_source_frames(method):
    x, y, bounds = variable_speed_walk()
    _, starts, ends, _ = detect_strides(x, y, np.ones(len(x)), 120, method=method)
    assert starts == list(bounds[:-2])
    assert ends == list(bounds[1:-1] - 1)
    # A long tracking loss must not become an invented stride.
    confidence = np.ones(len(x))
    confidence[80:105] = 0.1
    _, starts, ends, _ = detect_strides(x, y, confidence, 120, method=method, maximum_gap=3)
    assert all(not (start <= 105 and end >= 80) for start, end in zip(starts, ends, strict=True))


def test_short_internal_gaps_only_and_configured_cutoff():
    valid, trusted = trusted_samples([0.1, 0.4, 0.4, 0.1, 0.4, 0.4, 0.1], 0.3, 1)
    assert valid.tolist() == [False, True, True, False, True, True, False]
    assert trusted.tolist() == [False, True, True, True, True, True, False]


def test_bottom_paw_aliases_accept_actual_download_labels():
    x, y, bounds = variable_speed_walk()
    raw = pd.DataFrame({("LH_paw", "x"): x, ("LH_paw", "y"): y, ("LH_paw", "likelihood"): np.ones(len(x))})
    _, starts, ends, _ = bottom_detection(raw, "left", AlmaSettings())
    assert len(starts) == 7


def multiview_fixture(tmp_path, alma_fixtures_dir):
    side = alma_fixtures_dir / "alma_edge_cases_filtered.csv"
    frames = len(pd.read_csv(side, header=[1, 2]))
    bottom = pd.DataFrame(
        {
            ("DLC", marker, coord): np.ones(frames) if coord == "likelihood" else np.arange(frames) * 0.1
            for marker in ("lhpaw", "rhpaw", "lfpaw", "rfpaw")
            for coord in ("x", "y", "likelihood")
        }
    )
    path = tmp_path / "bottom.csv"
    bottom.to_csv(path, index=False)
    return AlmaViewCsvSet("test", side, side, path)


def test_each_view_scale_applies_to_alma_rustlab_and_custom(tmp_path, alma_fixtures_dir):
    item = multiview_fixture(tmp_path, alma_fixtures_dir)
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        calibration_method="manual",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        no_outlier_filter=True,
    )
    base, _ = calculate_recording_table(item, settings, GaitResultWriter(), pd)
    calibrated, _ = calculate_recording_table(
        item,
        replace(
            settings,
            view_calibration={
                "left": {"pixels_per_cm": 25.0},
                "right": {"pixels_per_cm": 100.0},
                "bottom": {"pixels_per_cm": 50.0},
            },
        ),
        GaitResultWriter(),
        pd,
    )
    for side, factor in (("left", 2.0), ("right", 0.5)):
        prefix = "l" if side == "left" else "r"
        for name in (
            f"{side}__stride length (cm)",
            f"{prefix}-back-ankle__Movement",
            f"{side}_knee_vertical_excursion",
        ):
            np.testing.assert_allclose(calibrated[name], base[name] * factor, equal_nan=True)
        np.testing.assert_allclose(
            calibrated[f"{side}__knee joint amplitude (deg)"],
            base[f"{side}__knee joint amplitude (deg)"],
            equal_nan=True,
        )


def test_unmatched_right_cycles_are_retained(tmp_path, alma_fixtures_dir):
    item = multiview_fixture(tmp_path, alma_fixtures_dir)
    left = pd.DataFrame({"stride_start (frame)": [0], "stride_end (frame)": [9], "step height (cm)": [1.0]})
    right = pd.DataFrame(
        {"stride_start (frame)": [0, 20], "stride_end (frame)": [9, 29], "step height (cm)": [2.0, 3.0]}
    )
    recordings = iter((left, right))

    def calculate(*_):
        return next(recordings), None, None, None, None, None, ()

    table, messages = calculate_recording_table(
        item, AlmaSettings(pixels_per_cm=50.0), GaitResultWriter(), pd, calculate=calculate
    )
    assert table["right__step height (cm)"].tolist() == [2.0, 3.0]
    assert pd.isna(table.loc[1, "left__step height (cm)"])
    assert table["reference_view"].tolist() == ["left", "right"]


def test_preview_does_not_depend_on_csv_export(monkeypatch, alma_fixtures_dir):
    from dlc_gait_assembly.runway.manual.gait_analysis.client import gait_preview_worker as workers
    from dlc_gait_assembly.app.app_bootstrap import create_gait_preview
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure import gait_scientific_runtime_executor

    def unexpected(*_, **__):
        raise AssertionError("Preview must never call the CSV exporter")

    monkeypatch.setattr(gait_scientific_runtime_executor, "run_alma_gait_analysis", unexpected)
    worker = workers.StickPlotPreviewThread(
        (("Left", alma_fixtures_dir / "alma_edge_cases_filtered.csv"),),
        AlmaSettings(analysis_type="Spontaneous walking", pixels_per_cm=50.0, likelihood_threshold=0.0),
        preview=create_gait_preview(),
    )
    completed, errors = [], []
    worker.preview_ready.connect(lambda plots, source: completed.append(plots))
    worker.preview_failed.connect(errors.append)
    worker.run()
    assert not errors
    assert len(completed[0]) == 1
    assert completed[0][0][0] == "Left · stick plot"
    assert all(b"<svg" in svg for _, svg in completed[0])


def test_parameter_figures_keep_sparse_and_empty_measurements():
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_parameter_figures import (
        parameter_figure_pages,
    )

    table = pd.DataFrame(
        {
            "recording": ["mouse1", "mouse2"],
            "left__stride length (cm)": [1.0, np.nan],
            "right__step height (cm)": [np.nan, np.nan],
        }
    )
    pages = parameter_figure_pages(table)
    assert len(pages) == 1
    svg = pages[0][1].decode()
    assert "n=1/2 valid" in svg and "n=0/2 valid" in svg
    assert "No valid measurements" in svg


def test_rejected_cycles_still_show_stickplot_without_inventing_accepted_measurements(alma_fixtures_dir):
    from dlc_gait_assembly.app.app_bootstrap import create_gait_preview

    settings = AlmaSettings(
        analysis_type="Spontaneous walking", pixels_per_cm=50.0, likelihood_threshold=0.0, stride_length_min_cm=1000.0
    )
    plots, _, messages = create_gait_preview().prepare(
        (("Left", alma_fixtures_dir / "alma_edge_cases_filtered.csv"),), settings
    )
    assert [name for name, _ in plots] == ["Left · stick plot"]
    assert "0 accepted" in plots[0][1].decode()
    assert "stick-frame-" in plots[0][1].decode()
    assert "4 detected strides; 0 accepted" in plots[0][1].decode()
    assert any("0 passed filters" in message for message in messages)


def test_new_options_round_trip_manifest(tmp_path):
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        write_analysis_manifest,
        alma_settings_from_manifest,
    )

    settings = AlmaSettings(
        stride_detection_method="Bottom paw speed",
        max_interpolation_gap_frames=3,
        view_calibration={
            "left": {"pixels_per_cm": 25.0, "map_path": "/maps/left.json"},
            "right": {"pixels_per_cm": 100.0},
            "bottom": {"x_pixels_per_cm": 80.0, "y_pixels_per_cm": 90.0},
        },
    )
    path = tmp_path / "settings.json"
    write_analysis_manifest(path, settings)
    loaded = alma_settings_from_manifest(path)
    assert loaded.stride_detection_method == settings.stride_detection_method
    assert loaded.view_calibration == settings.view_calibration
    assert loaded.max_interpolation_gap_frames == 3


def test_camera_map_import_is_independent_and_controls_save_choice(tmp_path, monkeypatch):
    import json
    from PySide6.QtWidgets import QApplication, QFileDialog
    from dlc_gait_assembly.app.app_bootstrap import create_gait_preview, create_gait_analysis_operations
    from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace
    from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget

    app = QApplication.instance() or QApplication([])
    view = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    path = tmp_path / "left.json"
    path.write_text(json.dumps({"conversion_factor_map": {"overall": {"pixels_per_centimeter": 30.0}}}))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(path), ""))
    view.view_scale_spins["right"].setValue(75.0)
    view.bottom_x_pixels_per_cm_spin.setValue(80.0)
    view.calibration._import_view_calibration("left")
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    view.stride_method_combo.setCurrentText("Paw excursion peaks")
    settings = view.setup._collect_settings()
    assert settings.stride_detection_method == "Paw excursion peaks"
    assert settings.view_calibration["left"]["pixels_per_cm"] == 30.0
    assert settings.view_calibration["right"]["pixels_per_cm"] == 75.0
    assert settings.view_calibration["bottom"]["x_pixels_per_cm"] == 80.0
    view.close()
