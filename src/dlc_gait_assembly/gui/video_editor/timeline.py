from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider

from dlc_gait_assembly.services.domain.trimming import TrimRange
from dlc_gait_assembly.gui import theme


class TrimTimelineSlider(QSlider):
    trim_active_changed = Signal(int)
    trim_range_changed = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._duration_ms = 0
        self._trim_ranges: list[TrimRange] = []
        self._active_trim_index = 0
        self._trim_editing_enabled = False
        self._drag_handle: tuple[int, str] | None = None
        self.setMouseTracking(True)

    def set_trim_editing_enabled(self, enabled: bool) -> None:
        self._trim_editing_enabled = enabled
        self.unsetCursor()
        self.update()

    def set_trim_ranges(self, duration_ms: int, ranges: list[TrimRange], active_index: int = 0) -> None:
        self._duration_ms = max(0, int(duration_ms))
        self._trim_ranges = [trim.clamped(self._duration_ms) for trim in ranges if trim.clamped(self._duration_ms).is_usable()]
        if not self._trim_ranges and self._duration_ms > 0:
            self._trim_ranges = [TrimRange(0, self._duration_ms)]

        self._active_trim_index = _clamp_int(active_index, 0, max(0, len(self._trim_ranges) - 1))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._trim_editing_enabled or self._duration_ms <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        orange = QColor(theme.TOOL_1)
        inactive = QColor(theme.ACCENT)
        y = self.height() // 2

        for index, trim in enumerate(self._trim_ranges):
            active = index == self._active_trim_index
            color = orange if active else inactive
            start_x = self._x_for_ms(trim.start_ms)
            end_x = self._x_for_ms(trim.end_ms)
            painter.setPen(QPen(color, 5 if active else 3, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(start_x, y, end_x, y)
            self._draw_handle(painter, start_x, y, color, left=True, active=active)
            self._draw_handle(painter, end_x, y, color, left=False, active=active)

        painter.end()

    def mousePressEvent(self, event):
        if self._trim_editing_enabled and event.button() == Qt.LeftButton:
            handle = self._hit_handle(event.position().toPoint().x())
            if handle is not None:
                self._drag_handle = handle
                self._active_trim_index = handle[0]
                self.trim_active_changed.emit(handle[0])
                event.accept()
                self.update()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_handle is not None:
            index, side = self._drag_handle
            trim = self._trim_ranges[index]
            value = self._ms_for_x(event.position().toPoint().x())
            min_gap = min(100, max(1, self._duration_ms))
            if side == "start":
                trim = TrimRange(min(value, trim.end_ms - min_gap), trim.end_ms).clamped(self._duration_ms)
            else:
                trim = TrimRange(trim.start_ms, max(value, trim.start_ms + min_gap)).clamped(self._duration_ms)

            self._trim_ranges[index] = trim
            self.trim_range_changed.emit(index, trim.start_ms, trim.end_ms)
            event.accept()
            self.update()
            return

        if self._trim_editing_enabled:
            self.setCursor(Qt.SplitHCursor if self._hit_handle(event.position().toPoint().x()) is not None else Qt.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_handle is not None:
            self._drag_handle = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _draw_handle(self, painter: QPainter, x: int, y: int, color: QColor, left: bool, active: bool) -> None:
        height = 22 if active else 18
        top = y - height // 2
        bottom = y + height // 2
        cap = 6
        painter.setPen(QPen(color, 3 if active else 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(x, top, x, bottom)
        if left:
            painter.drawLine(x, top, x + cap, top)
            painter.drawLine(x, bottom, x + cap, bottom)
        else:
            painter.drawLine(x - cap, top, x, top)
            painter.drawLine(x - cap, bottom, x, bottom)

    def _hit_handle(self, x: int) -> tuple[int, str] | None:
        if self._duration_ms <= 0:
            return None

        candidates: list[tuple[int, int, str]] = []
        threshold = 9
        for index, trim in enumerate(self._trim_ranges):
            start_distance = abs(x - self._x_for_ms(trim.start_ms))
            end_distance = abs(x - self._x_for_ms(trim.end_ms))
            if start_distance <= threshold:
                candidates.append((start_distance, index, "start"))
            if end_distance <= threshold:
                candidates.append((end_distance, index, "end"))

        if not candidates:
            return None

        candidates.sort(key=lambda candidate: (candidate[0], abs(candidate[1] - self._active_trim_index)))
        _distance, index, side = candidates[0]
        return index, side

    def _track_rect(self) -> QRect:
        return self.rect().adjusted(12, 0, -12, 0)

    def _x_for_ms(self, value: int) -> int:
        track = self._track_rect()
        if self._duration_ms <= 0:
            return track.left()
        ratio = _clamp_float(value / self._duration_ms, 0.0, 1.0)
        return round(track.left() + track.width() * ratio)

    def _ms_for_x(self, x: int) -> int:
        track = self._track_rect()
        if self._duration_ms <= 0 or track.width() <= 0:
            return 0
        ratio = _clamp_float((x - track.left()) / track.width(), 0.0, 1.0)
        return round(self._duration_ms * ratio)


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
