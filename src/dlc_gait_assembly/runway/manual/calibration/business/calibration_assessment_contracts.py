"""Define spatial-scale assessment checks, pass/fail results, and recommendations."""

from __future__ import annotations

from dataclasses import dataclass

from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import Axis, CalibrationStick


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


@dataclass(frozen=True)
class CalibrationSettingsSnapshot:
    """A measured calibration assessment ready for serialization by an adapter."""

    sticks: tuple[CalibrationStick, ...]
    report: CalibrationReport
