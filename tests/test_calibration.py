from __future__ import annotations

from dlc_gait_assembly.domain.calibration import CalibrationPoint, CalibrationStick, calculate_calibration_report


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
