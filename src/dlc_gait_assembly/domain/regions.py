from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedRect:
    """A rectangle stored as fractions of the source video frame."""

    x: float
    y: float
    width: float
    height: float

    def clamped(self) -> "NormalizedRect":
        left = _clamp(self.x, 0.0, 1.0)
        top = _clamp(self.y, 0.0, 1.0)
        right = _clamp(self.x + self.width, 0.0, 1.0)
        bottom = _clamp(self.y + self.height, 0.0, 1.0)
        if right < left:
            left, right = right, left
        if bottom < top:
            top, bottom = bottom, top
        return NormalizedRect(left, top, right - left, bottom - top)

    def is_usable(self, min_fraction: float = 0.002) -> bool:
        rect = self.clamped()
        return rect.width >= min_fraction and rect.height >= min_fraction


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
