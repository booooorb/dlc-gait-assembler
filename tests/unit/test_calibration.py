from __future__ import annotations

import json

import pytest

from dlc_gait_assembly.domain.calibration import (
    CalibrationPoint,
    CalibrationStick,
    build_conversion_factor_map,
    calculate_calibration_report,
)
from dlc_gait_assembly.services.output_documents import write_calibration_conversion_export


def test_calibration_report_passes_for_consistent_three_view_measurements():
    report = calculate_calibration_report(_consistent_three_view_sticks(), tau_percent=2.0)

    assert report.location_passed is True
    assert report.axis_passed is True
    assert report.view_passed is True
    assert report.overall_passed is True
    assert report.recommendation.startswith("All checks pass")


def test_calibration_report_flags_location_dependent_distortion():
    sticks = [
        CalibrationStick(
            "x",
            1,
            CalibrationPoint(0, 10),
            CalibrationPoint(340, 10),
            (100 / 340, 200 / 340),
        ),
        CalibrationStick(
            "y",
            1,
            CalibrationPoint(10, 0),
            CalibrationPoint(10, 300),
            (1 / 3, 2 / 3),
        ),
    ]

    report = calculate_calibration_report(sticks, tau_percent=2.0)

    assert report.location_passed is False
    assert "Location-dependent distortion" in report.recommendation


def test_calibration_report_uses_two_tau_for_axis_check():
    sticks = [
        CalibrationStick("x", 1, CalibrationPoint(0, 10), CalibrationPoint(300, 10), (1 / 3, 2 / 3)),
        CalibrationStick("y", 1, CalibrationPoint(10, 0), CalibrationPoint(10, 240), (1 / 3, 2 / 3)),
    ]

    report = calculate_calibration_report(sticks, tau_percent=2.0)

    assert report.location_passed is True
    assert report.axis_passed is False
    assert report.views[0].axis_delta_percent > 4.0
    assert "Axis-specific scaling" in report.recommendation


def test_calibration_report_flags_view_specific_scaling():
    sticks = _consistent_three_view_sticks()
    sticks[4] = CalibrationStick("x", 3, CalibrationPoint(0, 10), CalibrationPoint(450, 10), (1 / 3, 2 / 3))
    sticks[5] = CalibrationStick("y", 3, CalibrationPoint(10, 0), CalibrationPoint(10, 450), (1 / 3, 2 / 3))

    report = calculate_calibration_report(sticks, tau_percent=2.0)

    assert report.location_passed is True
    assert report.axis_passed is True
    assert report.view_passed is False
    assert "View-specific scaling" in report.recommendation


def test_conversion_factor_map_can_be_applied_to_coordinates():
    report = calculate_calibration_report(_consistent_three_view_sticks(), tau_percent=2.0)

    conversion_map = build_conversion_factor_map(report)
    view_one = conversion_map["views"]["1"]

    assert conversion_map["recommended_scope"] == "shared"
    assert view_one["recommended_x_centimeters_per_pixel"] == 0.01
    assert view_one["recommended_y_centimeters_per_pixel"] == 0.01
    assert 250 * view_one["recommended_x_centimeters_per_pixel"] == 2.5
    assert 125 * view_one["recommended_y_centimeters_per_pixel"] == 1.25


def test_calibration_report_can_use_euclidean_segment_lengths():
    sticks = [
        CalibrationStick("x", 1, CalibrationPoint(0, 0), CalibrationPoint(300, 400), ()),
    ]

    axis_report = calculate_calibration_report(sticks, tau_percent=2.0)
    euclidean_report = calculate_calibration_report(sticks, tau_percent=2.0, use_euclidean_lengths=True)

    assert axis_report.view_axis[0].mean_conversion_factor == 1 / 300
    assert euclidean_report.view_axis[0].mean_conversion_factor == 1 / 500


def test_calibration_report_uses_custom_marker_interval_units():
    sticks = [CalibrationStick("x", 1, CalibrationPoint(0, 0), CalibrationPoint(100, 0), ())]

    cm_report = calculate_calibration_report(sticks, tau_percent=2.0, units_per_marker_interval=5.0, measurement_unit="cm")
    inch_report = calculate_calibration_report(sticks, tau_percent=2.0, units_per_marker_interval=2.0, measurement_unit="inches")

    assert cm_report.view_axis[0].mean_conversion_factor == 5 / 100
    assert inch_report.view_axis[0].mean_conversion_factor == 5.08 / 100
    assert inch_report.measurement_unit == "in"
    assert inch_report.centimeters_per_marker_interval == 5.08


def test_calibration_export_writes_conversion_map_and_report(tmp_path):
    sticks = _consistent_three_view_sticks()
    report = calculate_calibration_report(sticks, tau_percent=2.0, units_per_marker_interval=2.0, measurement_unit="inches")

    paths = write_calibration_conversion_export(tmp_path, sticks, report)

    payload = json.loads(paths["map"].read_text(encoding="utf-8"))
    assert paths["report"].exists()
    assert payload["conversion_factor_map"]["views"]["1"]["recommended_x_centimeters_per_pixel"] == pytest.approx(5.08 / 100)
    assert payload["conversion_factor_map"]["marker_interval"]["unit"] == "in"
    assert payload["conversion_factor_map"]["marker_interval"]["centimeters"] == 5.08
    assert payload["sticks"][0]["name"] == "xline_view1"
    assert payload["sticks"][0]["segment_pixel_lengths"] == [100.0, 100.0, 100.0]
    assert "x_cm = x_px" in paths["report"].read_text(encoding="utf-8")
    assert "Marker gap: 2 inches (5.08 cm)" in paths["report"].read_text(encoding="utf-8")


def _consistent_three_view_sticks() -> list[CalibrationStick]:
    sticks: list[CalibrationStick] = []
    for view_index in range(1, 4):
        y_offset = view_index * 20
        sticks.append(
            CalibrationStick(
                "x",
                view_index,
                CalibrationPoint(0, y_offset),
                CalibrationPoint(300, y_offset),
                (1 / 3, 2 / 3),
            )
        )
        sticks.append(
            CalibrationStick(
                "y",
                view_index,
                CalibrationPoint(y_offset, 0),
                CalibrationPoint(y_offset, 300),
                (1 / 3, 2 / 3),
            )
        )
    return sticks
