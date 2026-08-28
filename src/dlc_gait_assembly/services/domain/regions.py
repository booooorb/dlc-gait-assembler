from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NormalizedRect:
    """A rectangle stored as fractions of the source video frame."""

    x: float
    y: float
    width: float
    height: float

    def clamped(self) -> NormalizedRect:
        if (
            0.0 <= self.x <= 1.0
            and 0.0 <= self.y <= 1.0
            and self.width >= 0.0
            and self.height >= 0.0
            and self.x + self.width <= 1.0
            and self.y + self.height <= 1.0
        ):
            # Preserve already-valid values exactly. Reconstructing width and
            # height from their right/bottom edges introduces floating-point
            # drift and makes a manifest write/read cycle lossy.
            return self
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


@dataclass(frozen=True)
class CropRegion:
    name: str
    rect: NormalizedRect
    flip_horizontal: bool = False
    flip_vertical: bool = False
    flip_horizontal_video_paths: frozenset[str] | None = field(default=None)

    def horizontal_flip_applies_to(self, input_path: str | None = None) -> bool:
        if not self.flip_horizontal:
            return False
        if self.flip_horizontal_video_paths is None or input_path is None:
            return True
        return _normalize_path(input_path) in self.flip_horizontal_video_paths

    def resolved_for_input(self, input_path: str) -> CropRegion:
        return CropRegion(
            self.name,
            self.rect,
            flip_horizontal=self.horizontal_flip_applies_to(input_path),
            flip_vertical=self.flip_vertical,
            flip_horizontal_video_paths=None,
        )

    def with_valid_horizontal_flip_paths(self, valid_paths: set[str] | frozenset[str]) -> CropRegion:
        if self.flip_horizontal_video_paths is None:
            return self
        selected = frozenset(path for path in self.flip_horizontal_video_paths if path in valid_paths)
        return CropRegion(
            self.name,
            self.rect,
            flip_horizontal=self.flip_horizontal and bool(selected),
            flip_vertical=self.flip_vertical,
            flip_horizontal_video_paths=selected,
        )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_path(path: str) -> str:
    """Compare boundary-normalized paths without introducing filesystem access."""

    return str(path)
