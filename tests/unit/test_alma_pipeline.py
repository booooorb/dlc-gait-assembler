from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from dlc_gait_assembly.services.pipeline.alma import (
    ALMA_FIGURE_FILENAMES,
    AlmaSettings,
    AlmaViewCsvSet,
    filter_low_confidence_coordinates,
    generate_alma_representations,
    hide_low_confidence_stickplot_frames,
    merge_multiview_rustlab1_dataframe,
    pixels_per_cm_from_calibration_map,
    run_alma_gait_analysis,
    settings_from_alma_config,
)
from dlc_gait_assembly.services.pipeline.alma.runner import (
    _selected_alma_output,
    _selected_combined_output,
    load_kinematics_functions,
)
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    CUSTOM_SOP_PARAMETER_NAMES,
    RUSTLAB1_FIGURE_FILENAMES,
    RUSTLAB1_PARAMETER_NAMES,
    extract_custom_sop_parameters,
    extract_rustlab1_parameters,
    generate_rustlab1_figures,
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
        "l-back-mtp": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "l-back-knee": (np.zeros(frame_count), np.arange(frame_count, dtype=float) * 2.0),
        "l-back-toe_tip": (np.arange(frame_count, dtype=float) + 10, np.arange(frame_count, dtype=float)),
        "l-hip": (np.r_[np.full(10, 5.0), np.full(10, 15.0)], np.arange(frame_count, dtype=float)),
        "l-iliac-crest": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "r-back-ankle": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "r-back-mtp": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
        "r-back-knee": (np.zeros(frame_count), np.arange(frame_count, dtype=float) * 2.0),
        "r-back-toe_tip": (np.arange(frame_count, dtype=float) + 10, np.arange(frame_count, dtype=float)),
        "r-hip": (np.r_[np.full(10, 5.0), np.full(10, 15.0)], np.arange(frame_count, dtype=float)),
        "r-iliac-crest": (np.zeros(frame_count), np.arange(frame_count, dtype=float)),
    }
    for marker, (x, y) in marker_values.items():
        coordinates[(marker, "x")] = x
        coordinates[(marker, "y")] = y
        coordinates[(marker, "likelihood")] = np.ones(frame_count)

    raw = pd.DataFrame(coordinates)
    alma_parameters = pd.DataFrame({"stride_start (frame)": [0, 10], "stride_end (frame)": [9, 19]})
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

    custom = extract_custom_sop_parameters(raw, alma_parameters, settings, identity_kinematics)

    assert custom.available_parameters == CUSTOM_SOP_PARAMETER_NAMES
    assert custom.missing_markers == ()
    assert custom.dataframe["left_mtp_average_height"].tolist() == [0.45, 0.45]
    assert custom.dataframe["right_knee_vertical_excursion"].tolist() == [1.8, 1.8]


def test_parameter_selection_limits_alma_rustlab_and_combined_outputs():
    import pandas as pd

    settings = AlmaSettings(
        enabled_parameter_names=("stride length (cm)", "LB__avg_Angle"),
    )
    alma = pd.DataFrame(
        {
            "stride_start (frame)": [0],
            "stride length (cm)": [1.2],
            "cycle duration (s)": [0.1],
        }
    )
    combined = pd.DataFrame(
        {
            "animal_id": ["mouse-1"],
            "left__stride length (cm)": [1.2],
            "right__cycle duration (s)": [0.1],
            "LB__avg_Angle": [45.0],
            "RB__avg_Angle": [40.0],
            "cycle_valid": [True],
        }
    )

    assert list(_selected_alma_output(alma, settings)) == [
        "stride_start (frame)",
        "stride length (cm)",
    ]
    assert list(_selected_combined_output(combined, settings)) == [
        "animal_id",
        "left__stride length (cm)",
        "LB__avg_Angle",
        "cycle_valid",
    ]


def test_rustlab_and_custom_extraction_skip_disabled_parameters():
    import numpy as np
    import pandas as pd

    frame_count = 10
    coordinates = {}
    for marker in (
        "d-center-back",
        "d-back-left",
        "d-back-right",
        "l-back-ankle",
        "l-back-mtp",
        "l-back-knee",
        "l-back-toe",
        "l-hip",
        "l-iliac-crest",
        "r-back-ankle",
        "r-back-mtp",
        "r-back-knee",
        "r-back-toe",
        "r-hip",
        "r-iliac-crest",
    ):
        coordinates[(marker, "x")] = np.arange(frame_count, dtype=float)
        coordinates[(marker, "y")] = np.arange(frame_count, dtype=float)
        coordinates[(marker, "likelihood")] = np.ones(frame_count)
    raw = pd.DataFrame(coordinates)
    alma_parameters = pd.DataFrame({"stride_start (frame)": [0], "stride_end (frame)": [9]})
    settings = AlmaSettings(
        calibration_method="manual",
        pixels_per_cm=10.0,
        enabled_parameter_names=("LB__avg_Angle", "left_mtp_average_height"),
    )
    identity_kinematics = SimpleNamespace(butterworth_filter=lambda values, _fps, _cutoff: values)

    rustlab = extract_rustlab1_parameters(raw, alma_parameters, settings, identity_kinematics)
    custom = extract_custom_sop_parameters(raw, alma_parameters, settings, identity_kinematics)

    assert rustlab.available_parameters == ("LB__avg_Angle",)
    assert "RB__avg_Angle" not in rustlab.dataframe
    assert custom.available_parameters == ("left_mtp_average_height",)
    assert "right_mtp_average_height" not in custom.dataframe


def test_rustlab1_generates_complete_runway_figure_bundle(tmp_path):
    import matplotlib
    import numpy as np
    import pandas as pd

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    frame_count = 20
    coordinates: dict[tuple[str, str], object] = {}
    marker_values = {
        "d-center-back": (np.linspace(0, 2, frame_count), np.zeros(frame_count)),
        "d-back-left": (np.linspace(1, 5, frame_count), np.linspace(1, 2, frame_count)),
        "d-back-right": (np.linspace(1, 4, frame_count), np.linspace(-1, -2, frame_count)),
        "l-back-ankle": (np.linspace(0, 2, frame_count), np.sin(np.linspace(0, 4, frame_count)) + 5),
        "l-back-toe": (np.linspace(2, 8, frame_count), np.sin(np.linspace(0, 4, frame_count)) + 6),
        "l-hip": (np.linspace(0, 4, frame_count), np.cos(np.linspace(0, 4, frame_count)) + 4),
        "l-iliac-crest": (np.linspace(-1, 3, frame_count), np.cos(np.linspace(0, 4, frame_count)) + 3),
        "r-back-ankle": (np.linspace(0, 2, frame_count), np.sin(np.linspace(0, 4, frame_count)) + 5),
        "r-back-toe": (np.linspace(2, 8, frame_count), np.sin(np.linspace(0, 4, frame_count)) + 6),
        "r-hip": (np.linspace(0, 4, frame_count), np.cos(np.linspace(0, 4, frame_count)) + 4),
        "r-iliac-crest": (np.linspace(-1, 3, frame_count), np.cos(np.linspace(0, 4, frame_count)) + 3),
    }
    for marker, (x, y) in marker_values.items():
        coordinates[(marker, "x")] = x
        coordinates[(marker, "y")] = y
        coordinates[(marker, "likelihood")] = np.linspace(0.90, 1.0, frame_count)

    raw = pd.DataFrame(coordinates)
    alma_parameters = pd.DataFrame(
        {
            "limb (hind left / right)": ["left", "right"],
            "stride_start (frame)": [0, 10],
            "stride_end (frame)": [9, 19],
            "cycle duration (s)": [0.1, 0.1],
            "stride length (cm)": [1.2, 1.4],
            "stance duration (s)": [0.06, 0.05],
            "swing duration (s)": [0.04, 0.05],
        }
    )
    settings = AlmaSettings(
        calibration_method="manual",
        pixels_per_cm=10.0,
        frame_rate=120.0,
        generate_stickplot=False,
    )
    identity_kinematics = SimpleNamespace(butterworth_filter=lambda values, _fps, _cutoff: values)
    extraction = extract_rustlab1_parameters(raw, alma_parameters, settings, identity_kinematics)

    output_paths = generate_rustlab1_figures(
        raw,
        alma_parameters,
        extraction,
        tmp_path / "mouse_rustlab1_figures",
        settings,
        identity_kinematics,
        plt,
    )

    assert tuple(path.name for path in output_paths) == RUSTLAB1_FIGURE_FILENAMES
    assert all(path.exists() for path in output_paths)
    assert all("<svg" in path.read_text(encoding="utf-8") for path in output_paths)
    assert plt.get_fignums() == []


def test_alma_generates_tidy_summary_and_diagnostic_figure_bundle(tmp_path):
    import matplotlib
    import pandas as pd

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    parameters = pd.DataFrame(
        {
            "limb (hind left / right)": ["left", "right", "left", "right"],
            "stride_start (frame)": [0, 5, 10, 15],
            "stride_end (frame)": [4, 9, 14, 19],
            "cycle duration (s)": [0.10, 0.11, 0.12, 0.13],
            "stance duration (s)": [0.06, 0.07, 0.07, 0.08],
            "swing duration (s)": [0.04, 0.04, 0.05, 0.05],
            "stance percentage (%)": [60.0, 63.6, 58.3, 61.5],
            "stride length (cm)": [1.2, 1.3, 1.4, 1.5],
            "step height (cm)": [0.4, 0.5, 0.6, 0.7],
            "max velocity during swing (cm/s)": [20.0, 22.0, 24.0, 26.0],
            "mean toe-to-crest distance (cm)": [2.0, 2.1, 2.2, 2.3],
            "mtp joint extension (deg)": [100.0, 102.0, 104.0, 106.0],
            "mtp joint flexion (deg)": [60.0, 62.0, 64.0, 66.0],
            "mtp joint amplitude (deg)": [40.0, 40.0, 40.0, 40.0],
            "ankle joint amplitude (deg)": [30.0, 31.0, 32.0, 33.0],
            "knee joint amplitude (deg)": [25.0, 26.0, 27.0, 28.0],
            "hip joint amplitude (deg)": [20.0, 21.0, 22.0, 23.0],
            "Variability x plane 5 strides mean": [0.1, 0.2, 0.3, 0.4],
            "drag duration (s)": [0.0, 0.01, 0.02, 0.03],
            "drag percentage (%)": [0.0, 5.0, 10.0, 15.0],
        }
    )

    output_paths = generate_alma_representations(
        parameters,
        tmp_path,
        "mouse",
        plt,
        pd,
    )

    assert output_paths[0].name == "mouse_parameters_long.csv"
    assert output_paths[1].name == "mouse_parameter_summary.csv"
    assert tuple(path.name for path in output_paths[2:]) == ALMA_FIGURE_FILENAMES
    assert all(path.exists() for path in output_paths)
    assert set(pd.read_csv(output_paths[0])["parameter"]) >= {
        "cycle duration (s)",
        "knee joint amplitude (deg)",
    }
    summary = pd.read_csv(output_paths[1])
    assert set(summary["limb"]) == {"left", "right"}
    assert all("<svg" in path.read_text(encoding="utf-8") for path in output_paths[2:])
    assert plt.get_fignums() == []


def test_multiview_csv_set_merges_separate_views_for_rustlab1(tmp_path):
    import pandas as pd

    left_csv = tmp_path / "mouse_left.csv"
    right_csv = tmp_path / "mouse_right.csv"
    bottom_csv = tmp_path / "mouse_bottom.csv"
    _write_dlc_csv(left_csv, ("back-ankle", "back-toe", "hip", "iliac_crest"))
    _write_dlc_csv(right_csv, ("back-ankle", "back-toe", "hip", "iliac_crest"))
    _write_dlc_csv(bottom_csv, ("center-back", "back-left", "back-right"))

    view_set = AlmaViewCsvSet(
        name="mouse",
        left_csv=left_csv,
        right_csv=right_csv,
        bottom_csv=bottom_csv,
    )
    merged = merge_multiview_rustlab1_dataframe(view_set, pd)

    assert ("l-back-toe", "x") in merged.columns
    assert ("r-back-ankle", "y") in merged.columns
    assert ("d-center-back", "likelihood") in merged.columns

    alma_parameters = pd.DataFrame({"stride_start (frame)": [0], "stride_end (frame)": [4]})
    settings = AlmaSettings(calibration_method="manual", pixels_per_cm=10.0)
    identity_kinematics = SimpleNamespace(butterworth_filter=lambda values, _fps, _cutoff: values)

    result = extract_rustlab1_parameters(merged, alma_parameters, settings, identity_kinematics)

    assert result.dataframe is not None
    assert result.missing_markers == ()
    assert set(result.available_parameters).issubset(RUSTLAB1_PARAMETER_NAMES)


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


def test_alma_bodypart_normalization_accepts_hyphenated_iliac_crest_aliases(alma_root):
    import pandas as pd

    kinematics = load_kinematics_functions(alma_root)

    for crest_label in ("iliac-crest", "iliac_crest", "l-iliac-crest", "r-iliac-crest"):
        columns = []
        for bodypart in ("toe", "mtp", "ankle", "knee", "hip", crest_label):
            for coord in ("x", "y", "likelihood"):
                columns.append((bodypart, coord))

        raw = pd.DataFrame(
            1.0,
            index=range(3),
            columns=pd.MultiIndex.from_tuples(columns, names=("bodyparts", "coords")),
        )

        normalized, bodyparts, _bodyparts_raw = kinematics.fix_column_names(raw.copy())

        assert "iliac crest x" in normalized.columns
        assert "iliac crest y" in normalized.columns
        assert "iliac crest likelihood" in normalized.columns
        assert "iliac crest" in bodyparts

        custom_normalized, _bodyparts, _bodyparts_raw = kinematics.fix_column_names(
            raw.copy(),
            {
                "toe": "toe",
                "mtp": "mtp",
                "ankle": "ankle",
                "knee": "knee",
                "hip": "hip",
            },
        )

        assert "iliac crest x" in custom_normalized.columns


def test_low_confidence_filter_interpolates_parameters_and_masks_stickplot_frames():
    import numpy as np
    import pandas as pd

    dataframe = pd.DataFrame()
    for bodypart in ("toe", "mtp", "ankle", "knee", "hip", "iliac crest"):
        dataframe[f"{bodypart} x"] = [0.0, 1000.0, 2.0, 3.0]
        dataframe[f"{bodypart} y"] = [10.0, 1000.0, 12.0, 13.0]
        dataframe[f"{bodypart} likelihood"] = [0.9, 0.9, 0.9, 0.9]
    dataframe.loc[1, "toe likelihood"] = 0.1

    filtered, valid_mask, messages = filter_low_confidence_coordinates(dataframe, 0.5, pd)

    assert valid_mask["toe"].tolist() == [True, False, True, True]
    assert valid_mask["iliac crest"].tolist() == [True, True, True, True]
    assert "interpolated 1/24 low-confidence marker sample(s)" in messages[0]
    assert filtered.loc[1, "toe x"] == 1.0
    assert filtered.loc[1, "iliac crest y"] == 1000.0

    masked = hide_low_confidence_stickplot_frames(filtered, valid_mask)

    assert np.isnan(masked.loc[1, "toe x"])
    assert masked.loc[1, "iliac crest y"] == 1000.0
    assert masked.loc[2, "toe x"] == 2.0


def test_alma_config_uses_separate_kinematics_likelihood_threshold():
    assert settings_from_alma_config({"likelihood_threshold": 0.1}).likelihood_threshold == 0.5
    assert settings_from_alma_config({"kinematics_likelihood_threshold": 0.7}).likelihood_threshold == 0.7


def test_return_continuous_can_plot_one_valid_preview_stride(tmp_path, alma_root):
    import pandas as pd

    kinematics = load_kinematics_functions(alma_root)
    parameters = pd.DataFrame(
        {
            "stride_start (frame)": [0],
            "stride_end (frame)": [3],
            "cycle duration (s)": [0.025],
        }
    )
    coords = pd.DataFrame(
        {
            "toe x": [0.0, 1.0, 2.0, 3.0],
            "toe y": [10.0, 11.0, 10.0, 11.0],
            "mtp x": [0.5, 1.5, 2.5, 3.5],
            "mtp y": [9.0, 10.0, 9.0, 10.0],
            "ankle x": [1.0, 2.0, 3.0, 4.0],
            "ankle y": [8.0, 9.0, 8.0, 9.0],
            "knee x": [1.5, 2.5, 3.5, 4.5],
            "knee y": [7.0, 8.0, 7.0, 8.0],
            "hip x": [2.0, 3.0, 4.0, 5.0],
            "hip y": [6.0, 7.0, 6.0, 7.0],
            "iliac crest x": [2.5, 3.5, 4.5, 5.5],
            "iliac crest y": [5.0, 6.0, 5.0, 6.0],
        }
    )
    stickplot_path = tmp_path / "single_stride.svg"

    kinematics.return_continuous(
        parameters,
        n_continuous=1,
        plot=True,
        pd_dataframe_coords=coords,
        bodyparts=["toe", "mtp", "ankle", "knee", "hip", "iliac crest"],
        is_stance=[1, 1, 0, 0],
        filename=str(stickplot_path),
    )

    assert stickplot_path.exists()


def test_spontaneous_manual_pixel_ratio_matches_real_alma_parameters_csv(tmp_path, alma_root, alma_fixtures_dir):
    _assert_generated_parameters_match_real_alma(
        tmp_path,
        alma_root=alma_root,
        input_csv=alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv",
        expected_parameters_csv=alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered_parameters.csv",
        settings=_spontaneous_manual_50_px_per_cm_settings(),
    )


def test_edge_case_spontaneous_manual_pixel_ratio_matches_real_alma_parameters_csv(
    tmp_path, alma_root, alma_fixtures_dir
):
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
        likelihood_threshold=0.0,
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
        likelihood_threshold=0.0,
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
    if settings.generate_alma_representations:
        assert tmp_path / f"{input_csv.stem}_parameters_long.csv" in results[0].output_files
        assert tmp_path / f"{input_csv.stem}_parameter_summary.csv" in results[0].output_files
        assert all(
            tmp_path / f"{input_csv.stem}_alma_figures" / filename in results[0].output_files
            for filename in ALMA_FIGURE_FILENAMES
        )
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
        assert actual == expected, f"CSV differs at line {line_number}\nactual:   {actual}\nexpected: {expected}"


def _normalized_csv_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write_dlc_csv(path: Path, markers: tuple[str, ...], frame_count: int = 5) -> None:
    columns = [(marker, coord) for marker in markers for coord in ("x", "y", "likelihood")]
    rows = [
        ["scorer" for _marker, _coord in columns],
        [marker for marker, _coord in columns],
        [coord for _marker, coord in columns],
    ]
    for frame in range(frame_count):
        values = []
        for marker_index, (_marker, coord) in enumerate(columns):
            if coord == "x":
                values.append(str(frame + marker_index))
            elif coord == "y":
                values.append(str(frame * 2 + marker_index))
            else:
                values.append("1.0")
        rows.append(values)
    path.write_text("\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8")
