from __future__ import annotations


from dlc_gait_assembly.app.app_bootstrap import create_cohort_writer


import numpy as np


import pandas as pd


import pytest


from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import StrokeStudyMetadata


from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_baseline_deviation import (
    add_baseline_phase_deviation,
)


from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_feature_audit import audit_and_select_features


from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_use_cases import (
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


def test_baseline_phase_deviation_is_calculated_within_animal():
    data = pd.DataFrame(
        {
            "animal_id": ["a", "a", "b", "b"],
            "timepoint": ["baseline", "7 dpi", "baseline", "7 dpi"],
            "left_right_hindlimb_phase_offset": [48.0, 55.0, 52.0, 49.0],
        }
    )
    result = add_baseline_phase_deviation(data, pd)
    assert result["hindlimb_phase_offset_deviation_from_baseline"].tolist() == pytest.approx([0.0, 7.0, 0.0, -3.0])


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
    (retained, report) = audit_and_select_features(data, pd, np)
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
                    "session_speed_cm_s": 18.0 + (animal_number + time_number) % 5,
                    "left_right_hindlimb_phase_offset": 50.0
                    + time_number * (2.0 if group == "stroke" else 0.2)
                    + animal_number * 0.03,
                    "step_height_asymmetry": animal_number * 0.01 + time_number * (0.3 if group == "stroke" else 0.02),
                    "independent_measure": (animal_number * 7 + time_number * 3) % 11 / 10.0,
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
        outputs=create_cohort_writer(),
    )
    predictions = pd.read_csv(tmp_path / "analysis" / "random_forest_grouped_predictions.csv")
    assert predictions.groupby("animal_id")["fold"].nunique().max() == 1
    assert len(pd.read_csv(tmp_path / "analysis" / "PCA_scores.csv")) == len(rows)
    assert all(path.exists() for path in result.output_files)
