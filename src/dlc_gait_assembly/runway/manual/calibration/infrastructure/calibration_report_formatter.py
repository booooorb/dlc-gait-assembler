"""Format measured scale values, consistency checks, and assessment recommendations for reports."""

from __future__ import annotations

from datetime import datetime

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick


def calibration_report_markdown(
    report: CalibrationReport, conversion_map: dict, sticks: list[CalibrationStick], generated_at: datetime
) -> str:
    lines = [
        "# Calibration Conversion Factor Map",
        "",
        f"Generated: {generated_at.isoformat()}",
        "",
        "## How To Apply",
        "",
        "Use `conversion_factor_map.json` to convert pixel coordinates into centimeters.",
        "For a coordinate in a view, use the matching view entry:",
        "",
        "```text",
        "x_cm = x_px * recommended_x_centimeters_per_pixel",
        "y_cm = y_px * recommended_y_centimeters_per_pixel",
        "```",
        "",
        f"Recommended scope: `{conversion_map['recommended_scope']}`",
        f"Recommendation: {report.recommendation}",
        f"Marker gap: {marker_interval_label(report)}",
        "",
        "## Overall",
        "",
        f"- Overall cm/px: {format_optional(report.overall_mean)}",
        f"- Overall px/cm: {format_optional(safe_inverse(report.overall_mean))}",
        f"- Overall status: {status(report.overall_passed)}",
        f"- Tau: {report.tau_percent:.2f}%",
        "",
        "## View Factors",
        "",
        "| View | X cm/px | Y cm/px | Mean cm/px | Axis check | View check |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for view in report.views:
        lines.append(
            f"| {view.view_index} | {format_optional(view.x_mean)} | {format_optional(view.y_mean)} | {format_optional(view.view_mean)} | {status(view.axis_passed)} | {status(view.view_passed)} |"
        )
    lines.extend(["", "## Calibration Sticks", ""])
    for stick in sticks:
        lines.append(
            f"- {stick.name}: {len(stick.segment_pixel_lengths())} measured {marker_interval_label(report)} interval(s), markers at {', '.join(f'{position:.4f}' for position in stick.ordered_marker_positions())}"
        )
    return "\n".join(lines) + "\n"


def stick_to_dict(stick: CalibrationStick) -> dict:
    return {
        "name": stick.name,
        "axis": stick.axis,
        "view_index": stick.view_index,
        "start": {"x": stick.start.x, "y": stick.start.y},
        "end": {"x": stick.end.x, "y": stick.end.y},
        "marker_positions": list(stick.marker_positions),
        "segment_pixel_lengths": list(stick.segment_pixel_lengths()),
        "centimeter_pixel_lengths": list(stick.centimeter_pixel_lengths()),
    }


def format_optional(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.8f}"


def marker_interval_label(report: CalibrationReport) -> str:
    if report.measurement_unit == "in":
        return f"{report.units_per_marker_interval:g} inches ({report.centimeters_per_marker_interval:g} cm)"
    return f"{report.units_per_marker_interval:g} cm"


def status(value: bool | None) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "NEEDS DATA"


def safe_inverse(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return 1.0 / value
