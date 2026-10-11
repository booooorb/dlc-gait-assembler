"""Aggregate pixels-per-unit measurements by location, axis, and view."""

from __future__ import annotations

from math import isfinite

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import (
    ViewAxisCalibration,
    ViewCalibration,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import Axis, CalibrationStick


def calculate_view_axis_stats(
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
        mean_conversion = mean(conversion_factors)
        location_delta = None
        location_passed = None
        if mean_conversion is not None and conversion_factors:
            location_delta = max(
                abs((factor - mean_conversion) / mean_conversion) * 100.0 for factor in conversion_factors
            )
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


def calculate_view_stats(
    view_axis_stats: tuple[ViewAxisCalibration, ...], tau_percent: float
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
        view_mean = mean([x_mean, y_mean])
        axis_delta = None
        axis_passed = None
        if x_mean is not None and y_mean is not None and (x_mean + y_mean > 0):
            axis_delta = abs((x_mean - y_mean) / (x_mean + y_mean)) * 100.0
            axis_passed = axis_delta <= 2.0 * tau_percent
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


def mean(values) -> float | None:
    usable = [float(value) for value in values if value is not None and isfinite(float(value))]
    if not usable:
        return None
    return sum(usable) / len(usable)
