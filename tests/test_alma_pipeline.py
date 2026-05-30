from __future__ import annotations

import json
from pathlib import Path

from dlc_gait_assembly.services.alma_pipeline import (
    AlmaSettings,
    pixels_per_cm_from_calibration_map,
    run_alma_gait_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALMA_ROOT = PROJECT_ROOT / "DLC-Gait-Analysis-main" / "alma-master"
ALMA_RESOURCES = ALMA_ROOT / "Resources"
REAL_ALMA_PARAMETERS_CSV = PROJECT_ROOT / "tests" / "Demo_Mouse_Treadmill_30cm_s_650000_filtered_parameters.csv"
DLC_COORDINATE_CSV = ALMA_RESOURCES / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv"


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


def test_spontaneous_manual_pixel_ratio_matches_real_alma_parameters_csv(tmp_path):
    import pandas as pd
    from pandas.testing import assert_frame_equal

    assert REAL_ALMA_PARAMETERS_CSV.exists(), f"Missing real ALMA output fixture: {REAL_ALMA_PARAMETERS_CSV}"
    assert DLC_COORDINATE_CSV.exists(), f"Missing DLC coordinate input fixture: {DLC_COORDINATE_CSV}"

    settings = AlmaSettings(
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

    results = run_alma_gait_analysis([DLC_COORDINATE_CSV], tmp_path, settings, ALMA_ROOT)
    actual_output = tmp_path / f"{DLC_COORDINATE_CSV.stem}_parameters.csv"

    assert len(results) == 1
    assert actual_output in results[0].output_files
    assert actual_output.exists()
    _assert_csv_text_equal(actual_output, REAL_ALMA_PARAMETERS_CSV)

    actual = pd.read_csv(actual_output)
    expected = pd.read_csv(REAL_ALMA_PARAMETERS_CSV)
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
