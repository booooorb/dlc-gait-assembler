"""Verify local geometric recovery without promoting estimates to reliable observations."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_coordinate_correction import correct_knee_dataframe
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_preview_sampling import bodypart_point


SETTINGS = KneeCorrectionSettings(3.0, 3.0, 1.0, likelihood_threshold=0.5, knee_direction="positive")


def coordinates(distances=(4.0, 4.0, 4.0)):
    columns = pd.MultiIndex.from_product(
        [["DLC_test"], ["hip", "knee", "ankle"], ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"],
    )
    return pd.DataFrame(
        [[i, 0.0, 0.9, np.nan, np.nan, np.nan, i + distance, 0.0, 0.8] for i, distance in enumerate(distances)],
        columns=columns,
        dtype=float,
    )


def knee_points(dataframe):
    return dataframe.loc[:, [("DLC_test", "knee", axis) for axis in ("x", "y")]].to_numpy()


@pytest.mark.parametrize("distance", [0.1, 0.5, 4.0, 10.0, 10000.0])
def test_only_impossible_frames_change_lengths_and_obey_fallback_ratio(distance):
    dataframe = coordinates([4.0, distance, 4.0])
    original = dataframe.copy(deep=True)
    settings = replace(SETTINGS, hip_knee_length_cm=4.0, knee_ankle_length_cm=2.0)
    corrected, (report,) = correct_knee_dataframe(dataframe, settings)
    points = knee_points(corrected)
    assert np.isfinite(points).all()
    pd.testing.assert_frame_equal(dataframe, original)
    assert report.frame_lengths[0] == report.frame_lengths[2] == (4.0, 2.0)
    assert np.allclose(points[[0, 2], 1], np.sqrt(3.75))
    femur, tibia = report.frame_lengths[1]
    hip = dataframe.loc[1, [("DLC_test", "hip", axis) for axis in ("x", "y")]].to_numpy()
    ankle = dataframe.loc[1, [("DLC_test", "ankle", axis) for axis in ("x", "y")]].to_numpy()
    assert np.linalg.norm(points[1] - hip) == pytest.approx(femur)
    assert np.linalg.norm(points[1] - ankle) == pytest.approx(tibia)
    if distance < 2.0 or distance > 6.0:
        assert femur / tibia == pytest.approx(0.83)
        assert abs(femur - tibia) < distance < femur + tibia
        assert report.frame_methods[1] == "adjusted_geometry"
        assert 0 <= report.frame_confidences[1] <= 0.25
    else:
        assert report.frame_methods[1] == "configured_geometry"
        assert report.frame_confidences[1] == 0.8
    assert settings.hip_knee_length_cm == 4.0
    assert settings.knee_ankle_length_cm == 2.0


def test_larger_adjustments_reduce_confidence_and_fallback_ratio_is_editable():
    corrected, (report,) = correct_knee_dataframe(
        coordinates([10.0, 100.0, 10000.0]), replace(SETTINGS, fallback_femur_tibia_ratio=1.0)
    )
    assert np.isfinite(knee_points(corrected)).all()
    assert all(femur == tibia for femur, tibia in report.frame_lengths)
    assert report.frame_confidences[0] > report.frame_confidences[1] > report.frame_confidences[2] > 0


@pytest.mark.parametrize("value,expected", [(0.1, 0.1), (0.0, 0.0), (np.nan, 0.0), (np.inf, 0.0)])
def test_weak_or_unknown_source_confidence_is_never_promoted(value, expected):
    dataframe = coordinates()
    dataframe.loc[:, ("DLC_test", "hip", "likelihood")] = value
    corrected, (report,) = correct_knee_dataframe(dataframe, SETTINGS)
    assert np.isfinite(knee_points(corrected)).all()
    assert np.all(corrected[("DLC_test", "knee", "likelihood")] == expected)
    assert all("low-confidence hip" in status for status in report.frame_statuses)


def test_missing_likelihood_column_is_unknown_confidence():
    dataframe = coordinates().drop(columns=[("DLC_test", "hip", "likelihood")])
    corrected, _ = correct_knee_dataframe(dataframe, SETTINGS)
    assert np.isfinite(knee_points(corrected)).all()
    assert (corrected[("DLC_test", "knee", "likelihood")] == 0).all()


def test_missing_endpoints_get_zero_confidence_display_positions_with_nearest_edges():
    dataframe = coordinates([4.0] * 5)
    dataframe.loc[[0, 2, 4], ("DLC_test", "hip", "x")] = np.nan
    corrected, (report,) = correct_knee_dataframe(dataframe, SETTINGS)
    points = knee_points(corrected)
    assert np.isfinite(points).all()
    assert np.allclose(points[0], points[1])
    assert np.allclose(points[2], (points[1] + points[3]) / 2)
    assert np.allclose(points[4], points[3])
    assert np.allclose(corrected[("DLC_test", "knee", "likelihood")], [0.0, 0.8, 0.0, 0.8, 0.0])
    assert report.frame_methods == (
        "temporal_display",
        "configured_geometry",
        "temporal_display",
        "configured_geometry",
        "temporal_display",
    )


@pytest.mark.parametrize("fill", [False, True])
def test_recording_without_any_finite_anchor_remains_missing_at_zero_confidence(fill):
    dataframe = coordinates([0.0] * 3)
    corrected, (report,) = correct_knee_dataframe(dataframe, replace(SETTINGS, fill_missing_coordinates=fill))
    assert np.isnan(knee_points(corrected)).all()
    assert (corrected[("DLC_test", "knee", "likelihood")] == 0).all()
    assert report.frame_methods == ("unavailable",) * 3


def test_disabling_geometric_and_display_recovery_keeps_holes_at_zero_confidence():
    corrected, (report,) = correct_knee_dataframe(
        coordinates([4.0, 10.0, 4.0]),
        replace(SETTINGS, adapt_infeasible_lengths=False, fill_missing_coordinates=False),
    )
    assert np.isnan(knee_points(corrected)[1]).all()
    assert report.frame_statuses[1] == "Segment lengths cannot form a triangle"
    assert report.frame_confidences[1] == 0.0
    assert report.frame_methods[1] == "unavailable"


def test_failed_geometry_retains_existing_coordinate_and_never_increases_its_confidence():
    dataframe = coordinates([0.0])
    dataframe.loc[0, ("DLC_test", "knee", "x")] = 1.0
    dataframe.loc[0, ("DLC_test", "knee", "y")] = 2.0
    dataframe.loc[0, ("DLC_test", "knee", "likelihood")] = 0.3
    corrected, (report,) = correct_knee_dataframe(dataframe, SETTINGS)
    assert np.array_equal(knee_points(corrected), [[1.0, 2.0]])
    assert report.frame_confidences == (0.3,)
    assert report.frame_methods == ("retained_original",)


@pytest.mark.parametrize(
    "updates",
    [
        {"fallback_femur_tibia_ratio": 0},
        {"fallback_femur_tibia_ratio": np.nan},
        {"adjusted_confidence_cap": 1.1},
        {"adjusted_confidence_cap": -0.1},
        {"likelihood_threshold": np.inf},
        {"hip_knee_length_cm": np.inf},
    ],
)
def test_invalid_recovery_settings_are_rejected(updates):
    with pytest.raises(ValueError):
        correct_knee_dataframe(coordinates(), replace(SETTINGS, **updates))


def test_preview_does_not_treat_infinite_coordinates_as_renderable():
    dataframe = coordinates()
    dataframe.loc[0, ("DLC_test", "hip", "x")] = np.inf
    assert bodypart_point(dataframe, "hip", 0) is None
