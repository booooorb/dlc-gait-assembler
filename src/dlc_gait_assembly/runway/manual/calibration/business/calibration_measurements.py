"""Define reference points, sticks, marker intervals, and measurement collections."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot, isfinite

Axis = str


@dataclass(frozen=True)
class CalibrationPoint:
    x: float
    y: float

    def interpolate(self, other: CalibrationPoint, fraction: float) -> CalibrationPoint:
        fraction = max(0.0, min(1.0, fraction))
        return CalibrationPoint(self.x + (other.x - self.x) * fraction, self.y + (other.y - self.y) * fraction)


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
        for first, second in zip(points, points[1:], strict=False):
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
