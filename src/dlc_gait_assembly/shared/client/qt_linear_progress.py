"""Present the shared styled linear progress indicator."""

from __future__ import annotations

from math import cos, pi, sin
from time import monotonic

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QProgressBar

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex as _dependency_theme_mix_hex

ACCENT_ROLES = {
    "tool_1": "TOOL_1",
    "tool_2": "TOOL_2",
    "tool_3": "TOOL_3",
    "primary": "PRIMARY",
    "running": "STATUS_RUNNING",
    "ready": "STATUS_READY",
    "error": "STATUS_ERROR",
}


class DynamicProgressBar(QProgressBar):
    """Minimal progress bar with a smooth elastic loading state."""

    def __init__(self, parent=None, accent_role: str = "tool_1"):
        super().__init__(parent)
        self._accent_role = accent_role
        self._active = False
        self._indeterminate_animated = True
        self._display_value = float(self.value())
        self._animation_start_value = self._display_value
        self._animation_target_value = self._display_value
        self._animation_elapsed = 0.0
        self._animation_duration = 0.0
        self._phase = 0.0
        self._last_tick_time = monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(16)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._sync_timer()
        self.update()

    def set_indeterminate_animated(self, animated: bool) -> None:
        """Choose whether an unknown-duration task uses a moving indicator."""
        self._indeterminate_animated = bool(animated)
        self._sync_timer()
        self.update()

    def set_accent_role(self, accent_role: str) -> None:
        self._accent_role = accent_role
        self.update()

    def setRange(self, minimum: int, maximum: int) -> None:
        super().setRange(minimum, maximum)
        self._display_value = max(float(minimum), min(float(maximum), self._display_value))
        self._animation_start_value = self._display_value
        self._animation_target_value = self._display_value
        self._animation_elapsed = 0.0
        self._animation_duration = 0.0
        self._sync_timer()
        self.update()

    def setValue(self, value: int) -> None:
        super().setValue(value)
        self._begin_value_animation()
        self._sync_timer()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = max(2.0, min(5.0, rect.height() * 0.34))
        track_path = QPainterPath()
        track_path.addRoundedRect(rect, radius, radius)
        painter.fillPath(track_path, QColor(_dependency_theme_mix_hex(theme.SURFACE, theme.BACKGROUND, 0.16)))
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawPath(track_path)
        if self._is_indeterminate():
            self._paint_indeterminate(painter, rect, radius)
        else:
            self._paint_determinate(painter, rect, radius)
        text = self.text() if self.isTextVisible() else ""
        if text:
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_determinate(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        minimum = self.minimum()
        maximum = self.maximum()
        if maximum <= minimum:
            return
        fraction = self._display_fraction()
        if fraction <= 0:
            return
        fill_rect = QRectF(rect)
        fill_rect.setWidth(max(2.0, rect.width() * fraction))
        fill_path = QPainterPath()
        fill_path.addRoundedRect(fill_rect, radius, radius)
        painter.save()
        painter.setClipPath(rounded_path(rect, radius))
        painter.fillPath(fill_path, self._fill_brush(fill_rect))
        painter.restore()

    def _paint_indeterminate(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        if not self._indeterminate_animated:
            painter.save()
            painter.setClipPath(rounded_path(rect, radius))
            painter.fillPath(rounded_path(rect, radius), self._fill_brush(rect, 0.24))
            painter.restore()
            return
        speed = abs(sin(self._phase * 2.0 * pi))
        chunk_width = max(26.0, rect.width() * (0.18 + 0.12 * speed))
        x = rect.left() + (rect.width() - chunk_width) * self._yoyo()
        chunk = QRectF(x, rect.top(), chunk_width, rect.height())
        painter.save()
        painter.setClipPath(rounded_path(rect, radius))
        chunk_path = QPainterPath()
        chunk_path.addRoundedRect(chunk, radius, radius)
        painter.fillPath(chunk_path, self._fill_brush(chunk, 0.95))
        painter.restore()

    def _fill_brush(self, rect: QRectF, alpha: float | None = None) -> QBrush:
        base_alpha = alpha
        if base_alpha is None and self._active and (not self._is_indeterminate()):
            base_alpha = 0.88 + 0.1 * self._pulse()
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(
            0.0, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.SURFACE, 0.28), base_alpha)
        )
        gradient.setColorAt(
            0.48, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.SURFACE, 0.08), base_alpha)
        )
        gradient.setColorAt(
            1.0, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.BACKGROUND, 0.12), base_alpha)
        )
        return QBrush(gradient)

    def _pulse(self) -> float:
        return 0.5 + 0.5 * sin(self._phase * 2.0 * pi)

    def _yoyo(self) -> float:
        return 0.5 - 0.5 * cos(self._phase * 2.0 * pi)

    def _tick(self) -> None:
        now = monotonic()
        elapsed = max(0.001, min(0.06, now - self._last_tick_time))
        self._last_tick_time = now
        self._phase = (self._phase + elapsed * 0.58) % 1.0
        self._advance_display_value(elapsed)
        self.update()
        self._sync_timer()

    def _sync_timer(self) -> None:
        should_run = (
            self._is_indeterminate()
            and self._indeterminate_animated
            or (self._active and (not self._is_indeterminate()))
            or self._is_value_animating()
        )
        if should_run and (not self._timer.isActive()):
            self._last_tick_time = monotonic()
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()

    def _is_indeterminate(self) -> bool:
        return self.minimum() == 0 and self.maximum() == 0

    def _accent_hex(self) -> str:
        return getattr(theme, ACCENT_ROLES.get(self._accent_role, "TOOL_1"), theme.TOOL_1)

    def _display_fraction(self) -> float:
        minimum = self.minimum()
        maximum = self.maximum()
        if maximum <= minimum:
            return 0.0
        return max(0.0, min(1.0, (self._display_value - minimum) / (maximum - minimum)))

    def _advance_display_value(self, elapsed: float) -> None:
        if self._is_indeterminate():
            return
        if self._animation_duration <= 0:
            return
        self._animation_elapsed = min(self._animation_duration, self._animation_elapsed + elapsed)
        progress = self._animation_elapsed / self._animation_duration
        eased_progress = 1.0 - (1.0 - progress) ** 3
        self._display_value = (
            self._animation_start_value + (self._animation_target_value - self._animation_start_value) * eased_progress
        )
        if self._animation_elapsed >= self._animation_duration:
            self._display_value = self._animation_target_value
            self._animation_duration = 0.0

    def _is_value_animating(self) -> bool:
        return not self._is_indeterminate() and self._animation_duration > 0

    def _begin_value_animation(self) -> None:
        if self._is_indeterminate():
            return
        target = float(self.value())
        if abs(target - self._animation_target_value) < 0.04:
            return
        span = max(1.0, float(self.maximum() - self.minimum()))
        distance = abs(target - self._display_value) / span
        self._animation_start_value = self._display_value
        self._animation_target_value = target
        self._animation_elapsed = 0.0
        self._animation_duration = min(0.48, max(0.14, 0.14 + 0.64 * distance))


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def with_alpha(color_hex: str, alpha: float | None) -> QColor:
    color = QColor(color_hex)
    if alpha is not None:
        color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color
