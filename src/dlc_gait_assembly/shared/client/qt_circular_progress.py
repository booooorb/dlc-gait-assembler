"""Present the shared animated circular progress indicator."""

from __future__ import annotations

from math import cos, pi, sin
from time import monotonic

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QProgressBar

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.qt_linear_progress import ACCENT_ROLES, with_alpha
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex as _dependency_theme_mix_hex


class CircularProgressIndicator(QProgressBar):
    """Compact circular progress indicator for dense stage/status summaries."""

    def __init__(self, parent=None, accent_role: str = "tool_1"):
        super().__init__(parent)
        self._accent_role = accent_role
        self._active = False
        self._center_text = ""
        self._center_font_max = 11.0
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
        self.setMinimumSize(52, 52)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._sync_timer()
        self.update()

    def set_accent_role(self, accent_role: str) -> None:
        self._accent_role = accent_role
        self.update()

    def set_center_text(self, text: str) -> None:
        self._center_text = text
        self.update()

    def set_center_font_max(self, point_size: float) -> None:
        self._center_font_max = max(8.0, float(point_size))
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
        side = min(self.width(), self.height())
        ring_scale = 0.17 if side < 80 else 0.11
        ring_width = max(6.0, min(12.0, side * ring_scale))
        rect = QRectF(
            (self.width() - side) / 2.0 + ring_width / 2.0 + 0.5,
            (self.height() - side) / 2.0 + ring_width / 2.0 + 0.5,
            side - ring_width - 1.0,
            side - ring_width - 1.0,
        )
        self._paint_center(painter, rect, ring_width)
        painter.setPen(
            QPen(
                QColor(_dependency_theme_mix_hex(theme.BORDER, theme.BACKGROUND, 0.44)),
                ring_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawArc(rect, 0, 360 * 16)
        if self._is_indeterminate():
            self._paint_indeterminate_arc(painter, rect, ring_width)
        else:
            self._paint_determinate_arc(painter, rect, ring_width)
        text = self._center_text or (self.text() if self.isTextVisible() else "")
        if text:
            painter.setPen(QColor(self._text_color_hex()))
            font = painter.font()
            font.setBold(True)
            font.setPointSizeF(max(8.0, min(self._center_font_max, side * 0.28)))
            painter.setFont(font)
            painter.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, text)

    def _paint_determinate_arc(self, painter: QPainter, rect: QRectF, ring_width: float) -> None:
        minimum = self.minimum()
        maximum = self.maximum()
        if maximum <= minimum:
            return
        fraction = self._fraction()
        if fraction <= 0 and self._active:
            self._paint_indeterminate_arc(painter, rect, ring_width)
            return
        if fraction <= 0:
            return
        start = 90.0
        span = -360.0 * fraction
        self._draw_arc(painter, rect, ring_width + 1.4, start, span, alpha=0.24)
        self._draw_arc(painter, rect, ring_width, start, span)

    def _paint_indeterminate_arc(self, painter: QPainter, rect: QRectF, ring_width: float) -> None:
        sweep = 96.0 + 116.0 * self._pulse()
        start = 90.0 - 360.0 * self._phase
        self._draw_arc(painter, rect, ring_width + 1.4, start, -sweep, alpha=0.22)
        self._draw_arc(painter, rect, ring_width, start, -sweep)
        self._paint_arc_cap(painter, rect, ring_width, start - sweep)

    def _draw_arc(
        self,
        painter: QPainter,
        rect: QRectF,
        ring_width: float,
        start_degrees: float,
        span_degrees: float,
        alpha: float | None = None,
    ) -> None:
        painter.setPen(QPen(self._arc_brush(rect, alpha), ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, round(start_degrees * 16), round(span_degrees * 16))

    def _paint_center(self, painter: QPainter, rect: QRectF, ring_width: float) -> None:
        fraction = self._fraction()
        if self._accent_role == "ready":
            fill = _dependency_theme_mix_hex(theme.STATUS_READY, theme.SURFACE, 0.78)
            border = theme.STATUS_READY
        elif self._accent_role == "error":
            fill = _dependency_theme_mix_hex(theme.STATUS_ERROR, theme.SURFACE, 0.82)
            border = theme.STATUS_ERROR
        elif self._active or self._is_indeterminate():
            fill = _dependency_theme_mix_hex(self._accent_hex(), theme.SURFACE, 0.84 - 0.08 * self._pulse())
            border = self._accent_hex()
        elif fraction > 0:
            fill = _dependency_theme_mix_hex(self._accent_hex(), theme.SURFACE, 0.88)
            border = self._accent_hex()
        else:
            fill = theme.SURFACE
            border = theme.BORDER
        center = QRectF(rect).adjusted(ring_width + 1.5, ring_width + 1.5, -ring_width - 1.5, -ring_width - 1.5)
        painter.setPen(QPen(QColor(_dependency_theme_mix_hex(border, theme.BACKGROUND, 0.38)), 1.0))
        painter.setBrush(QBrush(QColor(fill)))
        painter.drawEllipse(center)
        self._paint_progress_wash(painter, center, fraction)

    def _paint_progress_wash(self, painter: QPainter, rect: QRectF, fraction: float) -> None:
        if fraction <= 0:
            return
        gradient = QRadialGradient(rect.center(), max(rect.width(), rect.height()) / 2.0)
        gradient.setColorAt(0.0, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.SURFACE, 0.18), 0.54))
        gradient.setColorAt(
            1.0, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.BACKGROUND, 0.04), 0.72)
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        if fraction >= 1.0:
            painter.drawEllipse(rect)
            return
        path = QPainterPath()
        path.moveTo(rect.center())
        path.arcTo(rect, 90.0, -360.0 * fraction)
        path.closeSubpath()
        painter.drawPath(path)

    def _paint_arc_cap(self, painter: QPainter, rect: QRectF, ring_width: float, degrees: float) -> None:
        radians = degrees * pi / 180.0
        center = rect.center()
        radius_x = rect.width() / 2.0
        radius_y = rect.height() / 2.0
        cap_size = ring_width * (0.82 + 0.16 * self._pulse())
        cap = QRectF(
            center.x() + cos(radians) * radius_x - cap_size / 2.0,
            center.y() - sin(radians) * radius_y - cap_size / 2.0,
            cap_size,
            cap_size,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QBrush(
                QColor(
                    _dependency_theme_mix_hex(
                        theme.PRIMARY_TEXT if not theme.IS_DARK else theme.SURFACE, self._accent_hex(), 0.36
                    )
                )
            )
        )
        painter.drawEllipse(cap)

    def _arc_brush(self, rect: QRectF, alpha: float | None = None) -> QBrush:
        base_alpha = 0.95 if alpha is None else alpha
        gradient = QConicalGradient(rect.center(), -90.0)
        gradient.setColorAt(
            0.0, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.SURFACE, 0.04), base_alpha)
        )
        gradient.setColorAt(
            0.58, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.BACKGROUND, 0.1), base_alpha)
        )
        gradient.setColorAt(
            1.0, with_alpha(_dependency_theme_mix_hex(self._accent_hex(), theme.PRIMARY_TEXT, 0.22), base_alpha)
        )
        return QBrush(gradient)

    def _fraction(self) -> float:
        minimum = self.minimum()
        maximum = self.maximum()
        if maximum <= minimum:
            return 0.0
        return max(0.0, min(1.0, (self._display_value - minimum) / (maximum - minimum)))

    def _pulse(self) -> float:
        return 0.5 + 0.5 * sin(self._phase * 2.0 * pi)

    def _tick(self) -> None:
        now = monotonic()
        elapsed = max(0.001, min(0.06, now - self._last_tick_time))
        self._last_tick_time = now
        self._phase = (self._phase + elapsed * 0.68) % 1.0
        self._advance_display_value(elapsed)
        self.update()
        self._sync_timer()

    def _sync_timer(self) -> None:
        should_run = self._is_indeterminate() or self._active or self._is_value_animating()
        if should_run and (not self._timer.isActive()):
            self._last_tick_time = monotonic()
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()

    def _is_indeterminate(self) -> bool:
        return self.minimum() == 0 and self.maximum() == 0

    def _accent_hex(self) -> str:
        return getattr(theme, ACCENT_ROLES.get(self._accent_role, "TOOL_1"), theme.TOOL_1)

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

    def _text_color_hex(self) -> str:
        if self._accent_role == "ready":
            return theme.STATUS_READY
        if self._accent_role == "error":
            return theme.STATUS_ERROR
        if self._active or self._is_indeterminate():
            return self._accent_hex()
        return theme.CONNECTOR
