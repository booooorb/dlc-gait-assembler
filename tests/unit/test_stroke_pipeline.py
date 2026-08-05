from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.services.pipeline.alma import AlmaSettings, StrokeStudyMetadata
from dlc_gait_assembly.services.pipeline.stroke import (
    CANONICAL_CYCLE_COLUMNS,
    add_asymmetry_features,
    align_parameters_to_cycles,
    calculate_stroke_features,
    detect_canonical_cycles,
    summarize_session,
)
from dlc_gait_assembly.services.pipeline.stroke_analysis import (
    add_baseline_phase_deviation,
    audit_and_select_features,
    run_stroke_cohort_analysis,
)


def _trajectory_with_known_events() -> pd.DataFrame:
    frame = pd.DataFrame(index=range(40))
    frame["left_stance"] = False
    frame["right_stance"] = False
    for start in (0, 10, 20, 30):
        frame.loc[start : start + 5, "left_stance"] = True
        frame.loc[start + 3 : start + 7, "right_stance"] = True
    frame["required_tracking_valid"] = True
    frame["body_speed_cm_s"] = 20.0
    frame["left_x"] = 0.0
    frame["left_y"] = 0.0
    frame["right_x"] = 3.0
    frame["right_y"] = 0.0
    frame["center_x"] = 1.0
    frame["center_y"] = 0.0
    frame["left_mtp_y"] = np.tile(np.arange(10, dtype=float), 4)
    frame["right_mtp_y"] = np.tile(np.arange(10, dtype=float), 4)
    frame["left_knee_y"] = np.tile(np.arange(10, dtype=float) * 2.0, 4)
    frame["right_knee_y"] = np.tile(np.arange(10, dtype=float) * 2.0, 4)
    return frame


def _metadata() -> StrokeStudyMetadata:
    return StrokeStudyMetadata(
        animal_id="mouse-01",
        group="stroke",
        sex="female",
        lesion_hemisphere="right",
        timepoint="7 dpi",
        trial="1",
        session_id="mouse-01_7dpi",
    )


def test_canonical_cycles_use_left_onsets_and_pair_right_events():
    cycles = detect_canonical_cycles(
        _trajectory_with_known_events(),
        AlmaSettings(),
        _metadata(),
        pd,
        np,
    )

    assert len(cycles) == 3
    assert list(cycles["stride_start (frame)"]) == [0, 10, 20]
    assert list(cycles["stride_end (frame)"]) == [9, 19, 29]
    assert list(cycles["right_stance_start_frame"]) == [3, 13, 23]
    assert cycles["left_right_hindlimb_phase_offset"].tolist() == pytest.approx([30.0] * 3)
    assert cycles["hindlimb_stance_overlap_fraction"].tolist() == pytest.approx([30.0] * 3)
    assert cycles["cycle_valid"].all()
    assert cycles["animal_id"].eq("mouse-01").all()
    assert cycles["contralesional_side"].eq("left").all()


def test_empty_canonical_cycle_table_preserves_output_schema():
    trajectory = _trajectory_with_known_events().iloc[:1]

    cycles = detect_canonical_cycles(trajectory, AlmaSettings(), _metadata(), pd, np)

    assert cycles.empty
    assert tuple(cycles.columns) == CANONICAL_CYCLE_COLUMNS


def test_custom_stroke_features_have_known_geometry():
    trajectory = _trajectory_with_known_events()
    cycles = detect_canonical_cycles(trajectory, AlmaSettings(), _metadata(), pd, np)

    features = calculate_stroke_features(
        cycles,
        trajectory,
        {"x_pixels_per_cm": 1.0, "y_pixels_per_cm": 1.0},
        pd,
        np,
    )

    assert features["mean_hindlimb_base_support"].tolist() == pytest.approx([3.0] * 3)
    assert features["variance_hindlimb_base_support"].tolist() == pytest.approx([0.0] * 3)
    assert features["left_hindpaw_midline_distance"].tolist() == pytest.approx([1.0] * 3)
    assert features["right_hindpaw_midline_distance"].tolist() == pytest.approx([2.0] * 3)
    assert features["left_mtp_average_height"].tolist() == pytest.approx([4.5] * 3)
    assert features["right_mtp_vertical_excursion"].tolist() == pytest.approx([9.0] * 3)
    assert features["left_knee_average_height"].tolist() == pytest.approx([9.0] * 3)
    assert features["right_knee_vertical_excursion"].tolist() == pytest.approx([18.0] * 3)


def test_cycle_alignment_is_one_to_one_and_uses_frame_overlap():
    cycles = detect_canonical_cycles(
        _trajectory_with_known_events(),
        AlmaSettings(),
        _metadata(),
        pd,
        np,
    )
    parameters = pd.DataFrame(
        {
            "stride_start (frame)": [1, 11, 21],
            "stride_end (frame)": [9, 19, 29],
            "step height (cm)": [1.0, 2.0, 3.0],
        }
    )

    aligned = align_parameters_to_cycles(cycles, parameters, "left", pd, np)

    assert aligned["left__step height (cm)"].tolist() == [1.0, 2.0, 3.0]
    assert aligned["left__cycle_match_valid"].all()
    assert aligned["left__cycle_match_iou"].tolist() == pytest.approx([0.9] * 3)


def test_asymmetry_is_signed_contralesional_minus_ipsilesional():
    features = pd.DataFrame(
        {
            "left__step height (cm)": [4.0],
            "right__step height (cm)": [2.0],
            "left__stride length (cm)": [6.0],
            "right__stride length (cm)": [3.0],
            "left__stance percentage (%)": [60.0],
            "right__stance percentage (%)": [40.0],
            "left__knee joint amplitude (deg)": [30.0],
            "right__knee joint amplitude (deg)": [20.0],
            "left__drag percentage (%)": [10.0],
            "right__drag percentage (%)": [5.0],
            "left__back__protraction": [4.0],
            "left__back__retraction": [1.0],
            "right__back__protraction": [2.0],
            "right__back__retraction": [1.0],
        }
    )

    result = add_asymmetry_features(features, "right", np)

    assert result.loc[0, "step_height_asymmetry"] == pytest.approx(2.0 / 3.0)
    assert result.loc[0, "stride_length_asymmetry"] == pytest.approx(2.0 / 3.0)
    assert result.loc[0, "protraction_retraction_excursion_asymmetry"] == pytest.approx(1.0)


def test_session_summary_excludes_rejected_cycles():
    strides = pd.DataFrame(
        {
            "cycle_valid": [True, False, True],
            "mean_speed_cm_s": [20.0, 100.0, 22.0],
            "speed_cv": [0.05, 0.9, 0.07],
            "step_height_asymmetry": [0.1, 9.0, 0.3],
        }
    )
    summary = summarize_session(
        strides,
        _metadata(),
        {"required_tracking_coverage": 0.98},
        True,
        pd,
        np,
    )

    assert summary.loc[0, "valid_cycle_count"] == 2
    assert summary.loc[0, "session_speed_cm_s"] == pytest.approx(21.0)
    assert summary.loc[0, "step_height_asymmetry"] == pytest.approx(0.2)


def test_baseline_phase_deviation_is_calculated_within_animal():
    data = pd.DataFrame(
        {
            "animal_id": ["a", "a", "b", "b"],
            "timepoint": ["baseline", "7 dpi", "baseline", "7 dpi"],
            "left_right_hindlimb_phase_offset": [48.0, 55.0, 52.0, 49.0],
        }
    )

    result = add_baseline_phase_deviation(data, pd)

    assert result["hindlimb_phase_offset_deviation_from_baseline"].tolist() == pytest.approx(
        [0.0, 7.0, 0.0, -3.0]
    )


def test_redundancy_audit_prefers_primary_feature_without_outcome_labels():
    data = pd.DataFrame(
        {
            "animal_id": ["a", "b", "c", "d"],
            "group": ["sham", "sham", "stroke", "stroke"],
            "step_height_asymmetry": [0.0, 0.1, 0.3, 0.4],
            "duplicate_measure": [0.0, 1.0, 3.0, 4.0],
            "independent_measure": [1.0, 0.0, 1.0, 0.0],
        }
    )

    retained, report = audit_and_select_features(data, pd, np)

    assert "step_height_asymmetry" in retained
    assert "duplicate_measure" not in retained
    assert "independent_measure" in retained
    assert report["dropped_feature"].eq("duplicate_measure").any()


def test_random_forest_cross_validation_keeps_each_animal_in_one_fold(tmp_path):
    rows = []
    timepoints = ("baseline", "3 dpi", "14 dpi")
    for animal_number in range(8):
        group = "stroke" if animal_number >= 4 else "sham"
        for time_number, timepoint in enumerate(timepoints):
            rows.append(
                {
                    "animal_id": f"mouse-{animal_number}",
                    "group": group,
                    "timepoint": timepoint,
                    "session_id": f"mouse-{animal_number}-{time_number}",
                    "session_speed_cm_s": 18.0 + ((animal_number + time_number) % 5),
                    "left_right_hindlimb_phase_offset": (
                        50.0 + time_number * (2.0 if group == "stroke" else 0.2) + animal_number * 0.03
                    ),
                    "step_height_asymmetry": (
                        animal_number * 0.01 + time_number * (0.3 if group == "stroke" else 0.02)
                    ),
                    "independent_measure": ((animal_number * 7 + time_number * 3) % 11) / 10.0,
                }
            )
    source = tmp_path / "cohort_session_summary.csv"
    pd.DataFrame(rows).to_csv(source, index=False)

    result = run_stroke_cohort_analysis(
        [source],
        tmp_path / "analysis",
        run_pca=True,
        run_random_forest=True,
        run_mixed_effects=False,
    )

    predictions = pd.read_csv(tmp_path / "analysis" / "random_forest_grouped_predictions.csv")
    assert predictions.groupby("animal_id")["fold"].nunique().max() == 1
    assert len(pd.read_csv(tmp_path / "analysis" / "PCA_scores.csv")) == len(rows)
    assert all(path.exists() for path in result.output_files)
