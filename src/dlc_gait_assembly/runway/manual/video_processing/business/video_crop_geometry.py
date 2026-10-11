"""Calculate pixel crop bounds from normalized regions and source frame dimensions."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import NormalizedRect, PixelRect


def normalized_to_pixel_rect(rect: NormalizedRect, source_width: int, source_height: int) -> PixelRect:
    rect = rect.clamped()
    left = int(round(rect.x * source_width))
    top = int(round(rect.y * source_height))
    right = int(round((rect.x + rect.width) * source_width))
    bottom = int(round((rect.y + rect.height) * source_height))
    left = even(clamp_int(left, 0, max(0, source_width - 2)))
    top = even(clamp_int(top, 0, max(0, source_height - 2)))
    right = even(clamp_int(right, left + 2, source_width))
    bottom = even(clamp_int(bottom, top + 2, source_height))
    if right <= left:
        right = min(source_width, left + 2)
    if bottom <= top:
        bottom = min(source_height, top + 2)
    width = right - left
    height = bottom - top
    if width % 2:
        width -= 1
    if height % 2:
        height -= 1
    width = max(2, min(width, source_width - left))
    height = max(2, min(height, source_height - top))
    return PixelRect(x=left, y=top, width=width, height=height)


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def even(value: int) -> int:
    return value if value % 2 == 0 else value - 1
