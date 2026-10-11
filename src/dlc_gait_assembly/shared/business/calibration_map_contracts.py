"""Typed calibration-map records shared by calibration, knee correction, and gait analysis."""

from typing import TypedDict


class CalibrationScaleNode(TypedDict, total=False):
    centimeters_per_pixel: float | None
    pixels_per_centimeter: float | None
    mean_pixels_per_centimeter: float | None
    recommended_x_centimeters_per_pixel: float | None
    recommended_y_centimeters_per_pixel: float | None


class CalibrationAxisMap(CalibrationScaleNode, total=False):
    segment_count: int
    segment_centimeters_per_pixel: list[float]
    location_delta_percent: float | None
    location_passed: bool | None


class CalibrationViewMap(CalibrationScaleNode, total=False):
    view_index: int
    axes: dict[str, CalibrationAxisMap]
    axis_passed: bool | None
    view_passed: bool | None


class CalibrationConversionMap(TypedDict, total=False):
    version: int
    units: dict[str, str]
    marker_interval: dict[str, object]
    coordinate_system: dict[str, str]
    recommended_scope: str
    tau_percent: float
    overall: CalibrationScaleNode
    views: dict[str, CalibrationViewMap]
