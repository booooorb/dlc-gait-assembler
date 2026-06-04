from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot, isfinite


Axis = str


@dataclass(frozen=True)
class CalibrationPoint:
    x: float
    y: float

    def interpolate(self, other: "CalibrationPoint", fraction: float) -> "CalibrationPoint":
        fraction = max(0.0, min(1.0, fraction))
        return CalibrationPoint(
            self.x + (other.x - self.x) * fraction,
            self.y + (other.y - self.y) * fraction,
        )


@dataclass(frozen=True)
class CalibrationStick:
    axis: Axis
    view_index: int
    start: CalibrationPoint
    end: CalibrationPoint
    marker_positions: tuple[float, ...] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        return f"{self.axis}line_view{self.view_index}"

    def ordered_marker_positions(self) -> tuple[float, ...]:
        interior = sorted(position for position in self.marker_positions if 0.0 < position < 1.0)
        return (0.0, *interior, 1.0)

    def marker_points(self) -> tuple[CalibrationPoint, ...]:
        return tuple(self.start.interpolate(self.end, position) for position in self.ordered_marker_positions())

    def segment_pixel_lengths(self, use_euclidean: bool = False) -> tuple[float, ...]:
        points = self.marker_points()
        lengths: list[float] = []
        for first, second in zip(points, points[1:]):
            if use_euclidean:
                pixel_length = hypot(second.x - first.x, second.y - first.y)
            elif self.axis == "x":
                pixel_length = abs(second.x - first.x)
            elif self.axis == "y":
                pixel_length = abs(second.y - first.y)
            else:
                raise ValueError(f"Unknown calibration axis: {self.axis}")
            if pixel_length > 0 and isfinite(pixel_length):
                lengths.append(pixel_length)
        return tuple(lengths)

    def centimeter_pixel_lengths(self, use_euclidean: bool = False) -> tuple[float, ...]:
        return self.segment_pixel_lengths(use_euclidean)


@dataclass(frozen=True)
class ViewAxisCalibration:
    view_index: int
    axis: Axis
    segment_count: int
    conversion_factors: tuple[float, ...]
    mean_conversion_factor: float | None
    location_delta_percent: float | None
    location_passed: bool | None


@dataclass(frozen=True)
class ViewCalibration:
    view_index: int
    x_mean: float | None
    y_mean: float | None
    view_mean: float | None
    axis_delta_percent: float | None
    axis_passed: bool | None
    view_delta_percent: float | None = None
    view_passed: bool | None = None


@dataclass(frozen=True)
class CalibrationReport:
    tau_percent: float
    measurement_unit: str
    units_per_marker_interval: float
    centimeters_per_marker_interval: float
    view_axis: tuple[ViewAxisCalibration, ...]
    views: tuple[ViewCalibration, ...]
    overall_mean: float | None
    location_passed: bool | None
    axis_passed: bool | None
    view_passed: bool | None
    overall_passed: bool | None
    recommendation: str


def build_conversion_factor_map(report: CalibrationReport) -> dict:
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
                "pixels_per_centimeter": _inverse(mean),
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
            "mean_pixels_per_centimeter": _inverse(view.view_mean),
            "axis_delta_percent": view.axis_delta_percent,
            "axis_passed": view.axis_passed,
            "view_delta_percent": view.view_delta_percent,
            "view_passed": view.view_passed,
            "axes": view_axes,
        }

    return {
        "version": 1,
        "units": {
            "input": "pixels",
            "output": "centimeters",
            "conversion_factor": "centimeters_per_pixel",
        },
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
        "recommended_scope": _recommended_scope(report),
        "tau_percent": report.tau_percent,
        "overall": {
            "centimeters_per_pixel": report.overall_mean,
            "pixels_per_centimeter": _inverse(report.overall_mean),
            "location_passed": report.location_passed,
            "axis_passed": report.axis_passed,
            "view_passed": report.view_passed,
            "overall_passed": report.overall_passed,
            "recommendation": report.recommendation,
        },
        "views": views,
    }


def calculate_calibration_report(
    sticks: list[CalibrationStick],
    tau_percent: float = 2.0,
    use_euclidean_lengths: bool = False,
    units_per_marker_interval: float = 1.0,
    measurement_unit: str = "cm",
) -> CalibrationReport:
    tau_percent = max(0.0, float(tau_percent))
    measurement_unit = _normalized_measurement_unit(measurement_unit)
    units_per_marker_interval = max(0.000001, float(units_per_marker_interval))
    centimeters_per_marker_interval = _centimeters_per_marker_interval(units_per_marker_interval, measurement_unit)
    view_axis_stats = _calculate_view_axis_stats(
        sticks,
        tau_percent,
        use_euclidean_lengths,
        centimeters_per_marker_interval,
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


def _calculate_view_axis_stats(
    sticks: list[CalibrationStick],
    tau_percent: float,
    use_euclidean_lengths: bool,
    centimeters_per_marker_interval: float,
) -> tuple[ViewAxisCalibration, ...]:
    grouped: dict[tuple[int, Axis], list[float]] = {}
    for stick in sticks:
        key = (stick.view_index, stick.axis)
        for pixel_length in stick.segment_pixel_lengths(use_euclidean_lengths):
            grouped.setdefault(key, []).append(centimeters_per_marker_interval / pixel_length)

    stats: list[ViewAxisCalibration] = []
    for (view_index, axis), conversion_factors in sorted(grouped.items()):
        mean_conversion = _mean(conversion_factors)
        location_delta = None
        location_passed = None
        if mean_conversion is not None and conversion_factors:
            location_delta = max(abs((factor - mean_conversion) / mean_conversion) * 100.0 for factor in conversion_factors)
            location_passed = location_delta <= tau_percent

        stats.append(
            ViewAxisCalibration(
                view_index=view_index,
                axis=axis,
                segment_count=len(conversion_factors),
                conversion_factors=tuple(conversion_factors),
                mean_conversion_factor=mean_conversion,
                location_delta_percent=location_delta,
                location_passed=location_passed,
            )
        )
    return tuple(stats)


def _calculate_view_stats(
    view_axis_stats: tuple[ViewAxisCalibration, ...],
    tau_percent: float,
) -> tuple[ViewCalibration, ...]:
    means_by_view: dict[int, dict[Axis, float]] = {}
    for stat in view_axis_stats:
        if stat.mean_conversion_factor is None:
            continue
        means_by_view.setdefault(stat.view_index, {})[stat.axis] = stat.mean_conversion_factor

    views: list[ViewCalibration] = []
    for view_index, axis_means in sorted(means_by_view.items()):
        x_mean = axis_means.get("x")
        y_mean = axis_means.get("y")
        view_mean = _mean([x_mean, y_mean])
        axis_delta = None
        axis_passed = None
        if x_mean is not None and y_mean is not None and x_mean + y_mean > 0:
            axis_delta = abs((x_mean - y_mean) / (x_mean + y_mean)) * 100.0
            axis_passed = axis_delta <= (2.0 * tau_percent)

        views.append(
            ViewCalibration(
                view_index=view_index,
                x_mean=x_mean,
                y_mean=y_mean,
                view_mean=view_mean,
                axis_delta_percent=axis_delta,
                axis_passed=axis_passed,
            )
        )
    return tuple(views)


def _with_view_delta(view: ViewCalibration, overall_mean: float, tau_percent: float) -> ViewCalibration:
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


def _mean(values) -> float | None:
    usable = [float(value) for value in values if value is not None and isfinite(float(value))]
    if not usable:
        return None
    return sum(usable) / len(usable)


def _inverse(value: float | None) -> float | None:
    if value is None or value <= 0 or not isfinite(value):
        return None
    return 1.0 / value


def _recommended_scope(report: CalibrationReport) -> str:
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


def _aggregate_optional_passes(values) -> bool | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return all(usable)


def _recommendation(
    location_passed: bool | None,
    axis_passed: bool | None,
    view_passed: bool | None,
) -> str:
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


def _normalized_measurement_unit(unit: str) -> str:
    normalized = unit.strip().lower()
    if normalized in {"in", "inch", "inches"}:
        return "in"
    return "cm"


def _centimeters_per_marker_interval(value: float, unit: str) -> float:
    if unit == "in":
        return value * 2.54
    return value
