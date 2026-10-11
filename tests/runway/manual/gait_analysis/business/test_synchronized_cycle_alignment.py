from __future__ import annotations


import numpy as np


import pandas as pd


import pytest


from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings


from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet


from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import StrokeStudyMetadata


from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_PARAMETER_NAMES,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_PARAMETER_NAMES,
)


import dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_analysis_engine as stroke_module


from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter


from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    CANONICAL_CYCLE_COLUMNS,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_asymmetry import (
    add_asymmetry_features,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_alignment import (
    align_feature_rows_to_cycles,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_alignment import (
    align_parameters_to_cycles,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_feature_calculations import (
    calculate_stroke_features,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_alignment import (
    canonical_cycles_from_alma,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_detection import (
    detect_canonical_cycles,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_analysis_use_cases import (
    generate_stroke_analysis_outputs,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_session_summary import (
    summarize_session,
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
    cycles = detect_canonical_cycles(_trajectory_with_known_events(), AlmaSettings(), _metadata(), pd, np)
    assert len(cycles) == 3
    assert list(cycles["stride_start (frame)"]) == [0, 10, 20]
    assert list(cycles["stride_end (frame)"]) == [9, 19, 29]
    assert list(cycles["right_stance_start_frame"]) == [3, 13, 23]
    assert cycles["left_right_hindlimb_phase_offset"].tolist() == pytest.approx([30.0] * 3)
    assert cycles["hindlimb_stance_overlap_fraction"].tolist() == pytest.approx([30.0] * 3)
    assert cycles["cycle_valid"].all()
    assert cycles["animal_id"].eq("mouse-01").all()
    assert cycles["contralesional_side"].eq("left").all()


def test_synchronized_cycles_keep_alma_stride_boundaries_authoritative():
    alma_parameters = pd.DataFrame({"stride_start (frame)": [1, 11, 21], "stride_end (frame)": [9, 19, 29]})
    cycles = canonical_cycles_from_alma(alma_parameters, _trajectory_with_known_events(), _metadata(), pd, np)
    assert cycles["stride_start (frame)"].tolist() == [1, 11, 21]
    assert cycles["stride_end (frame)"].tolist() == [9, 19, 29]
    assert cycles["right_stance_start_frame"].tolist() == [3, 13, 23]


def test_post_alma_features_cannot_change_stride_identity():
    cycles = pd.DataFrame({"stride_start (frame)": [1], "stride_end (frame)": [9]})
    feature_rows = pd.DataFrame({"stride_start (frame)": [0], "stride_end (frame)": [9], "LB__avg_Angle": [12.0]})
    with pytest.raises(ValueError, match="changed authoritative ALMA stride_start"):
        align_feature_rows_to_cycles(cycles, feature_rows, ("LB__avg_Angle",), pd, np)


def test_empty_canonical_cycle_table_preserves_output_schema():
    trajectory = _trajectory_with_known_events().iloc[:1]
    cycles = detect_canonical_cycles(trajectory, AlmaSettings(), _metadata(), pd, np)
    assert cycles.empty
    assert tuple(cycles.columns) == CANONICAL_CYCLE_COLUMNS


def test_custom_stroke_features_have_known_geometry():
    trajectory = _trajectory_with_known_events()
    cycles = detect_canonical_cycles(trajectory, AlmaSettings(), _metadata(), pd, np)
    features = calculate_stroke_features(cycles, trajectory, {"x_pixels_per_cm": 1.0, "y_pixels_per_cm": 1.0}, pd, np)
    assert features["mean_hindlimb_base_support"].tolist() == pytest.approx([3.0] * 3)
    assert features["variance_hindlimb_base_support"].tolist() == pytest.approx([0.0] * 3)
    assert "left_hindpaw_midline_distance" not in features
    assert "right_hindpaw_midline_distance" not in features
    assert features["left_mtp_average_height"].tolist() == pytest.approx([4.5] * 3)
    assert features["right_mtp_vertical_excursion"].tolist() == pytest.approx([9.0] * 3)
    assert features["left_knee_average_height"].tolist() == pytest.approx([9.0] * 3)
    assert features["right_knee_vertical_excursion"].tolist() == pytest.approx([18.0] * 3)


def test_cycle_alignment_is_one_to_one_and_uses_frame_overlap():
    cycles = detect_canonical_cycles(_trajectory_with_known_events(), AlmaSettings(), _metadata(), pd, np)
    parameters = pd.DataFrame(
        {"stride_start (frame)": [1, 11, 21], "stride_end (frame)": [9, 19, 29], "step height (cm)": [1.0, 2.0, 3.0]}
    )
    aligned = align_parameters_to_cycles(cycles, parameters, "left", pd, np)
    assert aligned["left__step height (cm)"].tolist() == [1.0, 2.0, 3.0]
    assert aligned["left__cycle_match_valid"].all()
    assert aligned["left__cycle_match_iou"].tolist() == pytest.approx([0.9] * 3)


def test_forelimb_rustlab_features_merge_on_canonical_alma_stride_rows(tmp_path, monkeypatch):
    frame_count = 40
    block_angles = np.repeat([10.0, 30.0, 50.0, 70.0], 10)
    radians = np.deg2rad(block_angles)
    markers = (
        "d-center-back",
        "d-back-left",
        "d-back-right",
        "d-center-front",
        "d-front-left",
        "d-front-right",
        "l-back-ankle",
        "l-back-toe",
        "l-hip",
        "l-iliac-crest",
        "r-back-ankle",
        "r-back-toe",
        "r-hip",
        "r-iliac-crest",
        "l-front-toe-tip",
        "l-wrist",
        "l-elbow",
        "l-shoulder",
        "r-front-toe-tip",
        "r-wrist",
        "r-elbow",
        "r-shoulder",
    )
    coordinates: dict[tuple[str, str], object] = {}
    for index, marker in enumerate(markers):
        coordinates[marker, "x"] = np.arange(frame_count, dtype=float) + index
        coordinates[marker, "y"] = np.sin(np.arange(frame_count) / 4.0 + index) * 3.0 + index
        coordinates[marker, "likelihood"] = np.ones(frame_count)
    for marker in ("d-center-back", "d-center-front"):
        coordinates[marker, "x"] = np.zeros(frame_count)
        coordinates[marker, "y"] = np.zeros(frame_count)
    coordinates["d-front-left", "x"] = np.cos(radians)
    coordinates["d-front-left", "y"] = np.sin(radians)
    merged = pd.DataFrame(coordinates)
    trajectories = _trajectory_with_known_events()
    trajectory_qc = {"marker_coordinate_coverage": {}, "interpolated_samples": {}, "required_tracking_coverage": 1.0}
    outputs = GaitResultWriter()
    monkeypatch.setattr(outputs, "read_views", lambda *_args: merged)
    monkeypatch.setattr(stroke_module, "_bottom_trajectories", lambda *_args: (trajectories, trajectory_qc))
    metadata = _metadata()
    view_set = AlmaViewCsvSet(
        name="mouse-01_7dpi",
        left_csv=tmp_path / "left.csv",
        right_csv=tmp_path / "right.csv",
        bottom_csv=tmp_path / "bottom.csv",
        metadata=metadata,
    )
    left_parameters = pd.DataFrame(
        {"stride_start (frame)": [1, 11, 21], "stride_end (frame)": [9, 19, 29], "step height (cm)": [1.0, 2.0, 3.0]}
    )
    right_parameters = pd.DataFrame(
        {"stride_start (frame)": [1, 11, 21], "stride_end (frame)": [9, 19, 29], "step height (cm)": [4.0, 5.0, 6.0]}
    )
    settings = AlmaSettings(
        limb_scope="Hindlimb + Forelimb", calibration_method="manual", pixels_per_cm=10.0, minimum_synchronized_cycles=3
    )
    identity_kinematics = type(
        "IdentityKinematics", (), {"butterworth_filter": staticmethod(lambda values, _fps, _cutoff: values)}
    )()
    bundle = generate_stroke_analysis_outputs(
        view_set, tmp_path, settings, left_parameters, right_parameters, None, identity_kinematics, pd, outputs=outputs
    )
    merged_features = pd.read_csv(bundle.stride_features)
    assert len(merged_features) == 3
    assert merged_features.columns.is_unique
    assert set(RUSTLAB1_PARAMETER_NAMES).issubset(merged_features.columns)
    assert set(CUSTOM_SOP_PARAMETER_NAMES).issubset(merged_features.columns)
    assert merged_features["left__step height (cm)"].tolist() == [1.0, 2.0, 3.0]
    assert merged_features["right__step height (cm)"].tolist() == [4.0, 5.0, 6.0]
    assert merged_features["left__cycle_match_valid"].all()
    assert merged_features["right__cycle_match_valid"].all()
    assert "LF__avg_Angle" not in merged_features
    assert merged_features["stride_start (frame)"].tolist() == [1, 11, 21]


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
    summary = summarize_session(strides, _metadata(), {"required_tracking_coverage": 0.98}, True, pd, np)
    assert summary.loc[0, "valid_cycle_count"] == 2
    assert not {"session_speed_cm_s", "mean_speed_cm_s", "speed_cv"}.intersection(summary.columns)
    assert summary.loc[0, "step_height_asymmetry"] == pytest.approx(0.2)
