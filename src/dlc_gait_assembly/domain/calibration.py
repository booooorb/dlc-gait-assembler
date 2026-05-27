from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


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

    def centimeter_pixel_lengths(self) -> tuple[float, ...]:
        points = self.marker_points()
        lengths: list[float] = []
        for first, second in zip(points, points[1:]):
            if self.axis == "x":
                pixel_length = abs(second.x - first.x)
            elif self.axis == "y":
                pixel_length = abs(second.y - first.y)
            else:
                raise ValueError(f"Unknown calibration axis: {self.axis}")
            if pixel_length > 0 and isfinite(pixel_length):
                lengths.append(pixel_length)
        return tuple(lengths)


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
    view_axis: tuple[ViewAxisCalibration, ...]
    views: tuple[ViewCalibration, ...]
    overall_mean: float | None
    location_passed: bool | None
    axis_passed: bool | None
    view_passed: bool | None
    overall_passed: bool | None
    recommendation: str


def calculate_calibration_report(sticks: list[CalibrationStick], tau_percent: float = 2.0) -> CalibrationReport:
    tau_percent = max(0.0, float(tau_percent))
    view_axis_stats = _calculate_view_axis_stats(sticks, tau_percent)
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
) -> tuple[ViewAxisCalibration, ...]:
    grouped: dict[tuple[int, Axis], list[float]] = {}
    for stick in sticks:
        key = (stick.view_index, stick.axis)
        for pixel_length in stick.centimeter_pixel_lengths():
            grouped.setdefault(key, []).append(1.0 / pixel_length)

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
        return "Add calibration sticks and centimeter markers before interpreting calibration."
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
