"""Provide a horizontal media seek control with reusable position mapping."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider


class MediaSeekSlider(QSlider):
    """Map positions to values without owning trims, regions, or media decoding."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)

    def position_for_value(self, value: int, duration: int) -> int:
        track = self.rect().adjusted(12, 0, -12, 0)
        ratio = max(0.0, min(1.0, value / duration)) if duration > 0 else 0.0
        return round(track.left() + track.width() * ratio)

    def value_at_position(self, x: int, duration: int) -> int:
        track = self.rect().adjusted(12, 0, -12, 0)
        if duration <= 0 or track.width() <= 0:
            return 0
        ratio = max(0.0, min(1.0, (x - track.left()) / track.width()))
        return round(duration * ratio)
