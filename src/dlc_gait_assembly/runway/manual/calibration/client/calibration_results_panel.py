"""Present location, axis, and view checks with their assessment recommendations."""

from __future__ import annotations

from math import hypot, isfinite

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGroupBox, QLabel, QPushButton, QScrollArea, QVBoxLayout

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick


def report_to_html(report: CalibrationReport) -> str:
    if not report.view_axis:
        return f"<p style='color:{theme.TEXT};'>Create an x calibration stick, a y calibration stick, and add markers. Stick endpoints already count as markers.</p><p><b>Tau:</b> {report.tau_percent:.2f}%</p>"
    interval_label = marker_interval_label(report)
    parts = [
        f"<p><b>Overall:</b> {status_text(report.overall_passed)}<br><span style='color:{theme.TEXT};'>{report.recommendation}</span></p>",
        f"<p><b>Tau:</b> {report.tau_percent:.2f}% &nbsp; <b>Axis threshold:</b> {2.0 * report.tau_percent:.2f}%<br><b>Marker gap:</b> {interval_label}</p>",
        f"<p><b>Measured {interval_label} intervals</b></p>",
        "<table cellspacing='0' cellpadding='3'>",
        "<tr><th align='left'>Stick</th><th align='right'>Segments</th><th align='right'>Mean px/cm</th><th align='right'>s cm/px</th></tr>",
    ]
    for stat in report.view_axis:
        mean_px = "--" if stat.mean_conversion_factor in {None, 0} else f"{1.0 / stat.mean_conversion_factor:.2f}"
        mean_s = "--" if stat.mean_conversion_factor is None else f"{stat.mean_conversion_factor:.6f}"
        parts.append(
            f"<tr><td>{stat.axis}line_view{stat.view_index}</td><td align='right'>{stat.segment_count}</td><td align='right'>{mean_px}</td><td align='right'>{mean_s}</td></tr>"
        )
    parts.append("</table>")
    parts.append("<p><b>Check 1: location distortion</b></p><ul>")
    for stat in report.view_axis:
        parts.append(
            f"<li>{stat.axis}line_view{stat.view_index}: {percent(stat.location_delta_percent)} ({status_text(stat.location_passed)})</li>"
        )
    parts.append("</ul>")
    parts.append("<p><b>Check 2: x/y axis difference</b></p><ul>")
    for view in report.views:
        parts.append(
            f"<li>view{view.view_index}: {percent(view.axis_delta_percent)} ({status_text(view.axis_passed)})</li>"
        )
    parts.append("</ul>")
    parts.append("<p><b>Check 3: view difference</b></p><ul>")
    for view in report.views:
        parts.append(
            f"<li>view{view.view_index}: {percent(view.view_delta_percent)} ({status_text(view.view_passed)})</li>"
        )
    parts.append("</ul>")
    return "".join(parts)


def status_text(value: bool | None) -> str:
    if value is True:
        return f"<span style='color:{theme.STATUS_READY}; font-weight:700;'>PASS</span>"
    if value is False:
        return f"<span style='color:{theme.STATUS_ERROR}; font-weight:700;'>FAIL</span>"
    return f"<span style='color:{theme.CONNECTOR}; font-weight:700;'>NEEDS DATA</span>"


def percent(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}%"


def marker_interval_label(report: CalibrationReport) -> str:
    unit = "inches" if report.measurement_unit == "in" else "cm"
    if report.measurement_unit == "in":
        return f"{report.units_per_marker_interval:g} {unit} ({report.centimeters_per_marker_interval:g} cm)"
    return f"{report.units_per_marker_interval:g} {unit}"


def failed_location_marker_indices(
    stick: CalibrationStick,
    mean_conversion_factor: float,
    tau_percent: float,
    use_euclidean_lengths: bool,
    centimeters_per_marker_interval: float,
) -> set[int]:
    if mean_conversion_factor <= 0 or not isfinite(mean_conversion_factor):
        return set()
    worst_delta = 0.0
    worst_segment_index: int | None = None
    points = stick.marker_points()
    for segment_index, (first, second) in enumerate(zip(points, points[1:], strict=False)):
        pixel_length = segment_pixel_length(stick.axis, first, second, use_euclidean_lengths)
        if pixel_length <= 0 or not isfinite(pixel_length):
            continue
        conversion_factor = centimeters_per_marker_interval / pixel_length
        delta_percent = abs((conversion_factor - mean_conversion_factor) / mean_conversion_factor) * 100.0
        if delta_percent > worst_delta:
            worst_delta = delta_percent
            worst_segment_index = segment_index
    if worst_segment_index is None or worst_delta <= tau_percent:
        return set()
    return {worst_segment_index, worst_segment_index + 1}


def segment_pixel_length(axis: str, first, second, use_euclidean_lengths: bool) -> float:
    if use_euclidean_lengths:
        return hypot(second.x - first.x, second.y - first.y)
    if axis == "x":
        return abs(second.x - first.x)
    if axis == "y":
        return abs(second.y - first.y)
    return 0.0


def stick_key(axis: str, view_index: int) -> str:
    return f"{axis}:{view_index}"


def build_calibration_results(self, left_layout):
    results_box = QGroupBox("SOP checks")
    results_layout = QVBoxLayout(results_box)
    self.results_label = QLabel()
    self.results_label.setObjectName("ResultsLabel")
    self.results_label.setWordWrap(True)
    self.results_label.setTextFormat(Qt.RichText)
    self.results_label.setOpenExternalLinks(False)
    results_scroll = QScrollArea()
    results_scroll.setObjectName("ResultsScroll")
    results_scroll.setWidgetResizable(True)
    results_scroll.setFrameShape(QFrame.NoFrame)
    results_scroll.setWidget(self.results_label)
    results_layout.addWidget(results_scroll)
    self.export_conversion_button = QPushButton("Export conversion map")
    self.export_conversion_button.setObjectName("ExportButton")
    results_layout.addWidget(self.export_conversion_button)
    left_layout.addWidget(results_box, 1)
