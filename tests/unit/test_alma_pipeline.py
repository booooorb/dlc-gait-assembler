from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from dlc_gait_assembly.services.pipeline.alma import (
    AlmaSettings,
    pixels_per_cm_from_calibration_map,
    run_alma_gait_analysis,
)
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RUSTLAB1_PARAMETER_NAMES,
    extract_rustlab1_parameters,
)


def test_rustlab1_parameters_use_alma_cycle_boundaries_and_manual_scale():
    import numpy as np
    import pandas as pd

    frame_count = 20
    coordinates: dict[tuple[str, str], object] = {}
    marker_values = {
        "d-center-back": (np.zeros(frame_count), np.zeros(frame_count)),
        "d-back-left": (np.ones(frame_count), np.ones(frame_count)),
        "d-back-right": (np.ones(frame_count), np.zeros(frame_count)),
        "l-back-ankle": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "l-back-toe_tip": (np.arange(frame_count, dtype=float) + 10, np.arange(frame_count, dtype=float)),
        "l-hip": (np.r_[np.full(10, 5.0), np.full(10, 15.0)], np.arange(frame_count, dtype=float)),
        "l-iliac-crest": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "r-back-ankle": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "r-back-toe_tip": (np.arange(frame_count, dtype=float) + 10, np.arange(frame_count, dtype=float)),
        "r-hip": (np.r_[np.full(10, 5.0), np.full(10, 15.0)], np.arange(frame_count, dtype=float)),
        "r-iliac-crest": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
    }
    for marker, (x, y) in marker_values.items():
        coordinates[(marker, "x")] = x
        coordinates[(marker, "y")] = y
        coordinates[(marker, "likelihood")] = np.ones(frame_count)

    raw = pd.DataFrame(coordinates)
    alma_parameters = pd.DataFrame(
        {"stride_start (frame)": [0, 10], "stride_end (frame)": [9, 19]}
    )
    settings = AlmaSettings(
        calibration_method="manual",
        pixels_per_cm=10.0,
        generate_stickplot=False,
    )
    identity_kinematics = SimpleNamespace(butterworth_filter=lambda values, _fps, _cutoff: values)

    result = extract_rustlab1_parameters(raw, alma_parameters, settings, identity_kinematics)

    assert result.dataframe is not None
    assert result.available_parameters == RUSTLAB1_PARAMETER_NAMES
    assert result.missing_markers == ()
    assert result.dataframe["LB__avg_Angle"].tolist() == [45.0, 45.0]
    assert result.dataframe["RB__avg_Angle"].tolist() == [0.0, 0.0]
    assert result.dataframe["l-back-ankle__Average_Height"].tolist() == [4.5, 4.5]
    assert result.dataframe["r-back-ankle__Movement"].tolist() == [9.0, 9.0]
    assert np.isnan(result.dataframe.loc[0, "left__back__movement_per_step"])
    assert result.dataframe.loc[1, "left__back__movement_per_step"] == 1.0


def test_pixels_per_cm_from_calibration_map_uses_overall_value(tmp_path):
    map_path = tmp_path / "conversion_factor_map.json"
    map_path.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "overall": {
                        "centimeters_per_pixel": 0.01,
                        "pixels_per_centimeter": 100.0,
                    },
                    "views": {},
                }
            }
        ),
        encoding="utf-8",
    )

    pixels_per_cm, source = pixels_per_cm_from_calibration_map(map_path)

    assert pixels_per_cm == 100.0
    assert source == "overall"


def test_pixels_per_cm_from_calibration_map_can_use_view_axis_average(tmp_path):
    map_path = tmp_path / "conversion_factor_map.json"
    map_path.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "views": {
                        "1": {
                            "recommended_x_centimeters_per_pixel": 0.01,
                            "recommended_y_centimeters_per_pixel": 0.02,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    pixels_per_cm, source = pixels_per_cm_from_calibration_map(map_path, view_index=1)

    assert pixels_per_cm == 1 / 0.015
    assert source == "view 1"


def test_spontaneous_manual_pixel_ratio_matches_real_alma_parameters_csv(tmp_path, alma_root, alma_fixtures_dir):
    _assert_generated_parameters_match_real_alma(
        tmp_path,
        alma_root=alma_root,
        input_csv=alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv",
        expected_parameters_csv=alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered_parameters.csv",
        settings=_spontaneous_manual_50_px_per_cm_settings(),
    )


def test_edge_case_spontaneous_manual_pixel_ratio_matches_real_alma_parameters_csv(tmp_path, alma_root, alma_fixtures_dir):
    _assert_generated_parameters_match_real_alma(
        tmp_path,
        alma_root=alma_root,
        input_csv=alma_fixtures_dir / "alma_edge_cases_filtered.csv",
        expected_parameters_csv=alma_fixtures_dir / "alma_edge_cases_filtered_parameters.csv",
        settings=_spontaneous_manual_50_px_per_cm_settings(),
    )


def test_treadmill_demo_settings_match_real_alma_parameters_csv(tmp_path, alma_root, alma_fixtures_dir):
    _assert_generated_parameters_match_real_alma(
        tmp_path,
        alma_root=alma_root,
        input_csv=alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv",
        expected_parameters_csv=alma_fixtures_dir / "Treadmill(REAL)_30cm_s_650000_filtered_parameters.csv",
        settings=_treadmill_real_alma_demo_settings(),
    )


def _spontaneous_manual_50_px_per_cm_settings() -> AlmaSettings:
    return AlmaSettings(
        analysis_type="Spontaneous walking",
        frame_rate=120.0,
        filter_cutoff=6.0,
        calibration_method="manual",
        pixels_per_cm=50.0,
        right_to_left=False,
        no_outlier_filter=False,
        dragging_filter=False,
        drag_clearance_cm=0.10,
        drag_min_consecutive_frames=4,
        step_height_min_cm=0.0,
        step_height_max_cm=2.0,
        stride_length_min_cm=0.0,
        stride_length_max_cm=8.0,
        generate_stickplot=False,
    )


def _treadmill_real_alma_demo_settings() -> AlmaSettings:
    return AlmaSettings(
        analysis_type="Treadmill",
        treadmill_speed_cm_s=30.0,
        frame_rate=120.0,
        calibration_method="reference",
        reference_segment="ankle_toe",
        reference_length_cm=1.50,
        right_to_left="auto",
        drag_clearance_cm=0.12,
        drag_min_consecutive_frames=5,
        filter_cutoff=5.0,
        step_height_min_cm=0.0,
        step_height_max_cm=5.0,
        stride_length_min_cm=0.0,
        stride_length_max_cm=20.0,
        generate_stickplot=False,
    )


def _assert_generated_parameters_match_real_alma(
    tmp_path: Path,
    *,
    alma_root: Path,
    input_csv: Path,
    expected_parameters_csv: Path,
    settings: AlmaSettings,
) -> None:
    import pandas as pd
    from pandas.testing import assert_frame_equal

    assert expected_parameters_csv.exists(), f"Missing real ALMA output fixture: {expected_parameters_csv}"
    assert input_csv.exists(), f"Missing DLC coordinate input fixture: {input_csv}"

    results = run_alma_gait_analysis([input_csv], tmp_path, settings, alma_root)
    actual_output = tmp_path / f"{input_csv.stem}_parameters.csv"

    assert len(results) == 1
    assert actual_output in results[0].output_files
    assert actual_output.exists()
    _assert_csv_text_equal(actual_output, expected_parameters_csv)

    actual = pd.read_csv(actual_output)
    expected = pd.read_csv(expected_parameters_csv)
    assert list(actual.columns) == list(expected.columns)
    assert_frame_equal(
        actual,
        expected,
        check_dtype=True,
        check_exact=True,
    )


def _assert_csv_text_equal(actual_path: Path, expected_path: Path) -> None:
    actual_lines = _normalized_csv_text(actual_path).splitlines()
    expected_lines = _normalized_csv_text(expected_path).splitlines()
    assert len(actual_lines) == len(expected_lines), (
        f"CSV line count differs: actual={len(actual_lines)} expected={len(expected_lines)}"
    )

    for line_number, (actual, expected) in enumerate(zip(actual_lines, expected_lines), start=1):
        assert actual == expected, (
            f"CSV differs at line {line_number}\n"
            f"actual:   {actual}\n"
            f"expected: {expected}"
        )


def _normalized_csv_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")
