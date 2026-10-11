"""Calculate marker positions and axis-aligned or Euclidean stick-segment distances."""

from __future__ import annotations


def normalized_measurement_unit(unit: str) -> str:
    normalized = unit.strip().lower()
    if normalized in {"in", "inch", "inches"}:
        return "in"
    return "cm"


def centimeters_per_marker_interval(value: float, unit: str) -> float:
    if unit == "in":
        return value * 2.54
    return value
