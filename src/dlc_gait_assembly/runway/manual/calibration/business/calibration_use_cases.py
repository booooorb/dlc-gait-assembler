"""Assess reference measurements and coordinate conversion-map and report exports through ports."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.runway.manual.calibration.business.calibration_geometry import (
    centimeters_per_marker_interval as _centimeters_per_marker_interval,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_geometry import (
    normalized_measurement_unit as _normalized_measurement_unit,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick
from dlc_gait_assembly.runway.manual.calibration.business.calibration_quality_checks import (
    aggregate_optional_passes as _aggregate_optional_passes,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_quality_checks import (
    recommendation as _recommendation,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_quality_checks import (
    with_view_delta as _with_view_delta,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_scale_estimation import (
    calculate_view_axis_stats as _calculate_view_axis_stats,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_scale_estimation import (
    calculate_view_stats as _calculate_view_stats,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_scale_estimation import mean as _mean


def calculate_calibration_report(
    sticks: list[CalibrationStick],
    tau_percent: float = 2.0,
    use_euclidean_lengths: bool = False,
    units_per_marker_interval: float = 1.0,
    measurement_unit: str = "cm",
) -> CalibrationReport:
    tau_percent = max(0.0, float(tau_percent))
    measurement_unit = _normalized_measurement_unit(measurement_unit)
    units_per_marker_interval = max(1e-06, float(units_per_marker_interval))
    centimeters_per_marker_interval = _centimeters_per_marker_interval(units_per_marker_interval, measurement_unit)
    view_axis_stats = _calculate_view_axis_stats(
        sticks, tau_percent, use_euclidean_lengths, centimeters_per_marker_interval
    )
    view_stats = _calculate_view_stats(view_axis_stats, tau_percent)
    overall_mean = _mean([view.view_mean for view in view_stats])
    if overall_mean is not None:
        view_stats = tuple(_with_view_delta(view, overall_mean, tau_percent) for view in view_stats)
    location_passed = _aggregate_optional_passes(stat.location_passed for stat in view_axis_stats)
    axis_passed = _aggregate_optional_passes(view.axis_passed for view in view_stats)
    view_passed = _aggregate_optional_passes(view.view_passed for view in view_stats)
    overall_passed = _aggregate_optional_passes((location_passed, axis_passed, view_passed))
    recommendation = _recommendation(location_passed, axis_passed, view_passed)
    return CalibrationReport(
        tau_percent=tau_percent,
        measurement_unit=measurement_unit,
        units_per_marker_interval=units_per_marker_interval,
        centimeters_per_marker_interval=centimeters_per_marker_interval,
        view_axis=view_axis_stats,
        views=view_stats,
        overall_mean=overall_mean,
        location_passed=location_passed,
        axis_passed=axis_passed,
        view_passed=view_passed,
        overall_passed=overall_passed,
        recommendation=recommendation,
    )


class CalibrationUseCases:
    """Assess a measurement collection and export its assessed conversion map."""

    def __init__(self, exporter):
        self.exporter = exporter

    def assess(self, sticks, *args, **settings):
        return calculate_calibration_report(sticks, *args, **settings)

    def export(self, output_dir, sticks, report):
        return self.exporter.write(output_dir, sticks, report)

    def export_session(self, output_root, sticks, report):
        return self.export(self.exporter.allocate_session(output_root), sticks, report)
