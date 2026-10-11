"""Evaluate location, axis, and cross-view agreement against the configured tolerance."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import ViewCalibration


def with_view_delta(view: ViewCalibration, overall_mean: float, tau_percent: float) -> ViewCalibration:
    view_delta = None
    view_passed = None
    if view.view_mean is not None and overall_mean > 0:
        view_delta = abs((view.view_mean - overall_mean) / overall_mean) * 100.0
        view_passed = view_delta <= tau_percent
    return ViewCalibration(
        view_index=view.view_index,
        x_mean=view.x_mean,
        y_mean=view.y_mean,
        view_mean=view.view_mean,
        axis_delta_percent=view.axis_delta_percent,
        axis_passed=view.axis_passed,
        view_delta_percent=view_delta,
        view_passed=view_passed,
    )


def aggregate_optional_passes(values) -> bool | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return all(usable)


def recommendation(location_passed: bool | None, axis_passed: bool | None, view_passed: bool | None) -> str:
    if location_passed is None:
        return "Add calibration sticks and markers before interpreting calibration."
    if location_passed is False:
        return "Location-dependent distortion detected. Recapture if possible or use geometric calibration."
    if axis_passed is False and view_passed is False:
        return "View and axis scaling differ. Use separate view-axis conversion factors."
    if axis_passed is False:
        return "Axis-specific scaling detected. Use separate x and y conversion factors for affected views."
    if view_passed is False:
        return "View-specific scaling detected. Use one conversion factor per view."
    if axis_passed is None or view_passed is None:
        return "More paired x/y view measurements are needed for all SOP checks."
    return "All checks pass. A shared pixel-to-centimeter factor is acceptable."
