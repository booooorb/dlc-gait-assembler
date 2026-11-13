"""Research outcomes must preserve physical units, limb identity, and sampling evidence."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_recovery_summary import recovery_summary
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_swing_extraction import extract_swing_features
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_bottom_windows import BottomWindows
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.stroke_recovery_parameter_definitions import (
    STROKE_STRIDE_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_timing import read_view_track

IDENTITY_FILTER = SimpleNamespace(butterworth_filter=lambda values, *_: np.asarray(values, float))


def swing_recording():
    theta = np.deg2rad([90] * 5 + [90, 60, 30, 60, 90, 90])
    ankle_x, ankle_y = -np.sin(theta), np.cos(theta)
    positions = {
        "toe": (np.arange(11), [10] * 5 + [10, 8, 6, 8, 10, 10]),
        "hip": (np.zeros(11), np.ones(11)),
        "knee": (np.zeros(11), np.zeros(11)),
        "ankle": (ankle_x, ankle_y),
        "mtp": (ankle_x, ankle_y - 1),
    }
    frame = pd.DataFrame(
        {(m, a): np.asarray(v, float) for m, xy in positions.items() for a, v in zip(("x", "y"), xy, strict=True)}
    )
    for marker in positions:
        frame[marker, "likelihood"] = 1.0
    cycles = pd.DataFrame(
        {
            "stride_start (frame)": [0],
            "stride_end (frame)": [10],
            "cycle duration (s)": [1.0],
            "stance duration (s)": [0.5],
        }
    )
    return frame, cycles, AlmaSettings(frame_rate=10, filter_cutoff=2, pixels_per_cm=2, likelihood_threshold=0.95)


def test_swing_extraction_uses_stance_ground_and_swing_time_in_physical_units():
    raw, cycles, settings = swing_recording()
    result = extract_swing_features(raw, cycles, settings, IDENTITY_FILTER, 2).iloc[0]
    assert result["hindpaw_robust_excursion (cm)"] == pytest.approx(4.05)
    assert result["swing_mean_toe_clearance (cm)"] == pytest.approx(0.8)
    assert result["swing_peak_clearance_time (%)"] == pytest.approx(40)
    assert result["swing_knee_range_of_motion (deg)"] == pytest.approx(60)
    assert result["swing_ankle_range_of_motion (deg)"] == pytest.approx(60)
    changed_scale = extract_swing_features(raw, cycles, settings, IDENTITY_FILTER, 4).iloc[0]
    assert changed_scale["swing_mean_toe_clearance (cm)"] == pytest.approx(0.4)
    assert changed_scale["hindpaw_robust_excursion (cm)"] == pytest.approx(2.025)
    np.testing.assert_allclose(changed_scale.iloc[2:], result.iloc[2:])


def test_swing_measurements_require_observed_marker_samples_and_accepted_cycles():
    raw, cycles, settings = swing_recording()
    raw.loc[6, ("toe", "likelihood")] = 0.2
    result = extract_swing_features(raw, cycles, settings, IDENTITY_FILTER, 2).iloc[0]
    assert result.iloc[:3].isna().all()
    assert result["swing_knee_range_of_motion (deg)"] == pytest.approx(60)
    cycles["cycle duration (s)"] = np.nan
    assert extract_swing_features(raw, cycles, settings, IDENTITY_FILTER, 2).isna().all().all()


def test_swing_extraction_handles_missing_joints_stationary_toes_and_no_scale():
    raw, cycles, settings = swing_recording()
    missing = raw.drop(columns="hip", level=0)
    result = extract_swing_features(missing, cycles, settings, IDENTITY_FILTER, 2).iloc[0]
    assert pd.isna(result["hindpaw_robust_excursion (cm)"])
    assert pd.isna(result["swing_knee_range_of_motion (deg)"])
    assert result["swing_mean_toe_clearance (cm)"] == pytest.approx(0.8)
    no_scale = extract_swing_features(raw, cycles, settings, IDENTITY_FILTER, None).iloc[0]
    assert no_scale.iloc[:2].isna().all() and no_scale.iloc[2:].notna().all()
    raw["toe", "y"] = 10.0
    assert pd.isna(extract_swing_features(raw, cycles, settings, IDENTITY_FILTER, 2).iloc[0, 2])
    assert list(extract_swing_features(raw, cycles.iloc[:0], settings, IDENTITY_FILTER, 2)) == list(STROKE_STRIDE_NAMES)


def stride_table(values):
    return pd.DataFrame(
        {
            "stride_start (s)": np.arange(len(values), dtype=float),
            "stride_stop (s)": np.arange(len(values), dtype=float) + 1,
            "passed_stride_filters": True,
            "cycle duration (s)": values,
            "cycle velocity (cm/s)": 15.0,
            "step height (cm)": 0.0,
        }
    )


def test_summary_uses_independent_medians_and_signed_lesion_side_without_row_pairing():
    left = stride_table([1.0, 2.0, 3.0, 100.0, 999.0])
    left.loc[3, "passed_stride_filters"] = False
    right = stride_table([2.0, 4.0, 6.0])
    settings = AlmaSettings(minimum_synchronized_cycles=3)
    result = recovery_summary({"left": left.iloc[::-1], "right": right}, settings, 0, 4, "right")
    assert result["left__stride_duration_valid_strides"] == 3
    assert result["right__stride_duration_valid_strides"] == 3
    assert result["left__stride_duration_median (s)"] == 2.0
    assert result["right__stride_duration_median (s)"] == 4.0
    assert result["stride_duration_symmetry_index (%)"] == pytest.approx(200 / 3)
    assert result["stride_duration_lesion_asymmetry (%)"] == pytest.approx(-200 / 3)
    assert result["left__stride_duration_cv (%)"] == pytest.approx(50.0)
    assert result["right__stride_duration_cv (%)"] == pytest.approx(50.0)
    assert result["left__median_cycle_velocity (cm/s)"] == 15.0
    flipped = recovery_summary({"left": left, "right": right}, settings, 0, 4, "left")
    assert flipped["stride_duration_lesion_asymmetry (%)"] == pytest.approx(200 / 3)
    assert flipped["stride_duration_symmetry_index (%)"] == result["stride_duration_symmetry_index (%)"]


@pytest.mark.parametrize("lesion", ["unknown", "none", ""])
def test_lesion_metadata_is_required_only_for_signed_asymmetry(lesion):
    result = recovery_summary(
        {"left": stride_table([1, 2, 3]), "right": stride_table([2, 4, 6])},
        AlmaSettings(minimum_synchronized_cycles=3),
        0,
        3,
        lesion,
    )
    assert result["stride_duration_symmetry_index (%)"] == pytest.approx(200 / 3)
    assert pd.isna(result["stride_duration_lesion_asymmetry (%)"])
    assert result["contralesional_side"] == "unknown"
    assert pd.isna(result["step_height_symmetry_index (%)"])
    assert result["step_height_asymmetry_status"] == "undefined: zero denominator"


def test_summary_minimum_counts_and_cv_do_not_treat_missing_samples_as_zero():
    left, right = stride_table([1, np.inf, 3]), stride_table([1, 2, 3])
    settings = AlmaSettings(minimum_synchronized_cycles=3)
    result = recovery_summary({"left": left, "right": right}, settings, 0, 3)
    assert result["left__stride_duration_valid_strides"] == 2
    assert pd.isna(result["stride_duration_symmetry_index (%)"])
    assert pd.isna(result["left__stride_duration_cv (%)"])
    assert result["stride_duration_asymmetry_status"] == "insufficient valid strides"
    partial = recovery_summary(
        {"left": right, "right": right}, replace(settings, minimum_synchronized_cycles=1), 0.5, 2.5
    )
    assert partial["left__recovery_stride_count"] == 1  # only [1, 2) is complete
    assert partial["stride_duration_symmetry_index (%)"] == 0
    assert pd.isna(partial["left__stride_duration_cv (%)"])


def test_bottom_coordination_is_invariant_to_camera_pixel_scale():
    from pathlib import Path

    results = []
    for scale in (10.0, 100.0):
        raw = {}
        for offset, marker in zip((0, 25, 10, 35), ("lhpaw", "rhpaw", "lfpaw", "rfpaw"), strict=True):
            speeds = np.where((np.arange(100) + offset) % 50 < 30, 2.0, 20.0)
            raw[marker, "x"] = np.cumsum(speeds) / 100 * scale
            raw[marker, "y"] = np.full(100, offset / 10 * scale)
            raw[marker, "likelihood"] = np.ones(100)
        raw = pd.DataFrame(raw)
        settings = AlmaSettings(frame_rate=100, calibration_method="manual", pixels_per_cm=scale)
        track = read_view_track(raw, Path("bottom.csv"), "bottom", settings)
        bottom = BottomWindows(track, settings, None, IDENTITY_FILTER, raw)
        results.append(bottom.stride(0, 0.9, "left", forelimbs=True))
    for name in (
        "FLBR_RATIO",
        "FRBL_RATIO",
        "left__front__seconds",
        "hindlimb_single_support (%)",
        "opposite_hindlimb_single_support (%)",
    ):
        assert np.isfinite(results[0][name])
        assert results[0][name] == pytest.approx(results[1][name])
    assert results[0]["FLBR_RATIO"] > 0  # both views would be all-stance under a fixed 7 px/frame cutoff at scale=10
    single_support = (results[0]["hindlimb_single_support (%)"], results[0]["opposite_hindlimb_single_support (%)"])
    assert all(0 <= value <= 100 for value in single_support)
    assert sum(single_support) <= 100
    from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.retired_custom_parameters import RETIRED_CUSTOM_NAMES
    assert not RETIRED_CUSTOM_NAMES.intersection(results[0])
