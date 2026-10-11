"""Build the reusable spatial conversion map from the assessed stick measurements."""

from __future__ import annotations

from math import isfinite

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.shared.business.calibration_map_contracts import CalibrationConversionMap


def build_conversion_factor_map(report: CalibrationReport) -> CalibrationConversionMap:
    """Build a coordinate conversion map from pixel coordinates to centimeters."""
    views = {}
    axis_stats = {(stat.view_index, stat.axis): stat for stat in report.view_axis}
    for view in report.views:
        view_axes = {}
        for axis in ("x", "y"):
            stat = axis_stats.get((view.view_index, axis))
            mean = stat.mean_conversion_factor if stat is not None else None
            view_axes[axis] = {
                "centimeters_per_pixel": mean,
                "pixels_per_centimeter": inverse(mean),
                "segment_count": stat.segment_count if stat is not None else 0,
                "segment_centimeters_per_pixel": list(stat.conversion_factors) if stat is not None else [],
                "location_delta_percent": stat.location_delta_percent if stat is not None else None,
                "location_passed": stat.location_passed if stat is not None else None,
            }
        views[str(view.view_index)] = {
            "view_index": view.view_index,
            "recommended_x_centimeters_per_pixel": view.x_mean,
            "recommended_y_centimeters_per_pixel": view.y_mean,
            "mean_centimeters_per_pixel": view.view_mean,
            "mean_pixels_per_centimeter": inverse(view.view_mean),
            "axis_delta_percent": view.axis_delta_percent,
            "axis_passed": view.axis_passed,
            "view_delta_percent": view.view_delta_percent,
            "view_passed": view.view_passed,
            "axes": view_axes,
        }
    return {
        "version": 1,
        "units": {"input": "pixels", "output": "centimeters", "conversion_factor": "centimeters_per_pixel"},
        "marker_interval": {
            "value": report.units_per_marker_interval,
            "unit": report.measurement_unit,
            "centimeters": report.centimeters_per_marker_interval,
        },
        "coordinate_system": {
            "origin": "top-left pixel origin",
            "x_direction": "right",
            "y_direction": "down",
            "apply": "x_cm = x_px * recommended_x_centimeters_per_pixel; y_cm = y_px * recommended_y_centimeters_per_pixel",
        },
        "recommended_scope": recommended_scope(report),
        "tau_percent": report.tau_percent,
        "overall": {
            "centimeters_per_pixel": report.overall_mean,
            "pixels_per_centimeter": inverse(report.overall_mean),
            "location_passed": report.location_passed,
            "axis_passed": report.axis_passed,
            "view_passed": report.view_passed,
            "overall_passed": report.overall_passed,
            "recommendation": report.recommendation,
        },
        "views": views,
    }


def inverse(value: float | None) -> float | None:
    if value is None or value <= 0 or (not isfinite(value)):
        return None
    return 1.0 / value


def recommended_scope(report: CalibrationReport) -> str:
    if not report.view_axis:
        return "none"
    if any(view.x_mean is None or view.y_mean is None for view in report.views):
        return "view_axis"
    if report.overall_passed is True:
        return "shared"
    if report.axis_passed is False:
        return "view_axis"
    if report.view_passed is False:
        return "view"
    return "view_axis"
