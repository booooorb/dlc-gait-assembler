"""Render editable stick endpoints, interior markers, and assessment failure highlights."""

from __future__ import annotations

from math import hypot

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import (
    CalibrationPoint,
    CalibrationStick,
)


class CalibrationStickItem(QGraphicsItem):
    def __init__(self, stick: CalibrationStick, bounds: QRectF, on_changed):
        super().__init__()
        self._stick = stick
        self._bounds = QRectF(bounds)
        self._on_changed = on_changed
        self._drag_mode: str | int | None = None
        self._location_failure_marker_indices: set[int] = set()
        self._press_pos = QPointF()
        self._press_stick = stick
        self.setZValue(BASE_Z)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def stick(self) -> CalibrationStick:
        return self._stick

    def set_stick(self, stick: CalibrationStick) -> None:
        self.prepareGeometryChange()
        self._stick = stick
        self.update()

    def set_bounds(self, bounds: QRectF) -> None:
        self._bounds = QRectF(bounds)

    def set_location_failure_marker_indices(self, marker_indices: set[int]) -> None:
        self._location_failure_marker_indices = set(marker_indices)
        self.update()

    def boundingRect(self) -> QRectF:
        start = to_qpoint(self._stick.start)
        end = to_qpoint(self._stick.end)
        rect = QRectF(start, end).normalized()
        margin = self.hit_radius() + 54.0 / self._view_scale()
        return rect.adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        start = to_qpoint(self._stick.start)
        end = to_qpoint(self._stick.end)
        path.moveTo(start)
        path.lineTo(end)
        stroker = QPainterPathStroker()
        stroker.setWidth(self.hit_radius() * 2.6)
        hit_path = stroker.createStroke(path)
        for point in [start, end, *self._marker_qpoints(include_ends=False)]:
            hit_path.addEllipse(point, self.hit_radius() * 1.45, self.hit_radius() * 1.45)
        return hit_path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        color = QColor(theme.TOOL_3 if self._stick.axis == "x" else theme.TOOL_2)
        scale = self._view_scale()
        line_width = max(2.0, 3.0 / scale)
        radius = self.visual_radius()
        start = to_qpoint(self._stick.start)
        end = to_qpoint(self._stick.end)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(color, line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(start, end)
        ordered_markers = self._marker_qpoints(include_ends=True)
        end_marker_index = len(ordered_markers) - 1
        self._paint_handle(painter, start, color, radius, scale, 0 in self._location_failure_marker_indices)
        self._paint_handle(
            painter, end, color, radius, scale, end_marker_index in self._location_failure_marker_indices
        )
        for marker_index, marker_point in enumerate(self._marker_qpoints(include_ends=False), start=1):
            self._paint_handle(
                painter,
                marker_point,
                QColor(theme.TOOL_1),
                radius * 0.88,
                scale,
                marker_index in self._location_failure_marker_indices,
            )
        self._paint_label(painter, color, start, end)
        painter.restore()

    def hoverMoveEvent(self, event) -> None:
        hit = self._hit_test(event.pos())
        self.setCursor(self._cursor_for_hit(hit))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_mode = self._hit_test(event.pos())
        self._press_pos = event.pos()
        self._press_stick = self._stick
        self.setSelected(True)
        self.setZValue(ACTIVE_Z)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_mode is None:
            super().mouseMoveEvent(event)
            return
        self._on_changed(self._stick_for_drag(self._drag_mode, event.pos() - self._press_pos))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_mode is not None:
            self._drag_mode = None
            self.setZValue(BASE_Z)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def distance_and_position_for_scene_point(self, point: QPointF) -> tuple[float, float]:
        start = to_qpoint(self._stick.start)
        end = to_qpoint(self._stick.end)
        return distance_and_fraction(point, start, end)

    def delete_target_for_scene_pos(self, scene_pos: QPointF) -> DeleteTarget | None:
        hit = self._hit_test(self.mapFromScene(scene_pos))
        key = stick_key(self._stick.axis, self._stick.view_index)
        if isinstance(hit, int):
            return (key, hit)
        if hit != "none":
            return (key, "stick")
        return None

    def hit_radius(self) -> float:
        return max(0.35, 13.0 / self._view_scale())

    def visual_radius(self) -> float:
        return max(0.12, 4.0 / self._view_scale())

    def creation_guard_radius(self) -> float:
        return max(self.hit_radius() * 2.4, 26.0 / self._view_scale())

    def _hit_test(self, point: QPointF) -> str | int:
        for index, marker_point in enumerate(self._marker_qpoints(include_ends=False)):
            if point_distance(point, marker_point) <= self.hit_radius() * 1.35:
                return index
        if point_distance(point, to_qpoint(self._stick.start)) <= self.hit_radius() * 1.45:
            return "start"
        if point_distance(point, to_qpoint(self._stick.end)) <= self.hit_radius() * 1.45:
            return "end"
        (distance, _fraction) = self.distance_and_position_for_scene_point(point)
        if distance <= self.hit_radius() * 1.3:
            return "move"
        return "none"

    def _cursor_for_hit(self, hit: str | int):
        if hit in {"start", "end"}:
            return QCursor(Qt.CrossCursor)
        if hit == "move":
            return QCursor(Qt.SizeAllCursor)
        if isinstance(hit, int):
            return QCursor(Qt.PointingHandCursor)
        return QCursor(Qt.ArrowCursor)

    def _stick_for_drag(self, mode: str | int, delta: QPointF) -> CalibrationStick:
        stick = self._press_stick
        start = to_qpoint(stick.start)
        end = to_qpoint(stick.end)
        markers = list(stick.marker_positions)
        if mode == "start":
            start = clamp_point(start + delta, self._bounds)
        elif mode == "end":
            end = clamp_point(end + delta, self._bounds)
        elif mode == "move":
            moved_start = start + delta
            moved_end = end + delta
            correction = translation_correction(moved_start, moved_end, self._bounds)
            start = moved_start + correction
            end = moved_end + correction
        elif isinstance(mode, int) and 0 <= mode < len(markers):
            target = clamp_point(self._press_pos + delta, self._bounds)
            (_distance, fraction) = distance_and_fraction(target, start, end)
            markers[mode] = max(0.01, min(0.99, fraction))
        return CalibrationStick(
            stick.axis, stick.view_index, to_calibration_point(start), to_calibration_point(end), tuple(sorted(markers))
        )

    def _marker_qpoints(self, include_ends: bool) -> list[QPointF]:
        points = []
        positions = self._stick.ordered_marker_positions() if include_ends else self._stick.marker_positions
        start = to_qpoint(self._stick.start)
        end = to_qpoint(self._stick.end)
        for position in positions:
            points.append(interpolate_qpoint(start, end, position))
        return points

    def _paint_label(self, painter: QPainter, color: QColor, start: QPointF, end: QPointF) -> None:
        scale = self._view_scale()
        midpoint = interpolate_qpoint(start, end, 0.52)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max(1.0, hypot(dx, dy))
        normal = QPointF(-dy / length, dx / length)
        anchor = midpoint + QPointF(normal.x() * (18.0 / scale), normal.y() * (18.0 / scale))
        font = painter.font()
        font.setPointSizeF(max(7.0, 9.0 / max(0.8, scale)))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text = self._stick.name
        text_rect = metrics.boundingRect(text)
        rect = QRectF(anchor.x(), anchor.y(), text_rect.width() + 10.0 / scale, text_rect.height() + 6.0 / scale)
        rect.moveCenter(anchor)
        background = QColor(theme.CANVAS)
        background.setAlpha(218)
        painter.setPen(QPen(color, max(1.0, 1.0 / scale)))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 4.0 / scale, 4.0 / scale)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _paint_handle(
        self, painter: QPainter, point: QPointF, color: QColor, radius: float, scale: float, failed: bool = False
    ) -> None:
        cross = max(radius * 2.2, 8.0 / scale)
        halo_pen_width = max(1.2, 2.1 / scale)
        mark_pen_width = max(0.8, 1.0 / scale)
        if failed:
            painter.setBrush(Qt.NoBrush)
            for multiplier, alpha in ((6.0, 54), (4.2, 92), (2.7, 150)):
                glow = QColor(theme.STATUS_ERROR)
                glow.setAlpha(alpha)
                glow_radius = max(radius * multiplier, multiplier * 3.0 / scale)
                painter.setPen(QPen(glow, max(1.6, 2.4 / scale)))
                painter.drawEllipse(point, glow_radius, glow_radius)
        painter.setPen(QPen(QColor(theme.CANVAS_TEXT), halo_pen_width))
        painter.setBrush(color)
        painter.drawEllipse(point, radius, radius)
        painter.setPen(QPen(QColor(theme.CANVAS_TEXT), halo_pen_width))
        painter.drawLine(QPointF(point.x() - cross, point.y()), QPointF(point.x() + cross, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - cross), QPointF(point.x(), point.y() + cross))
        painter.setPen(QPen(QColor(theme.CANVAS), mark_pen_width))
        painter.drawLine(QPointF(point.x() - cross, point.y()), QPointF(point.x() + cross, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - cross), QPointF(point.x(), point.y() + cross))
        painter.setPen(QPen(QColor(theme.CANVAS_TEXT), max(0.8, 0.8 / scale)))
        painter.setBrush(QColor(theme.CANVAS))
        painter.drawEllipse(point, max(0.9, 1.1 / scale), max(0.9, 1.1 / scale))

    def _view_scale(self) -> float:
        views = self.scene().views() if self.scene() is not None else []
        if not views:
            return 1.0
        scale = views[0].transform().m11()
        return scale if scale > 0 else 1.0


def stick_key(axis: str, view_index: int) -> str:
    return f"{axis}:{view_index}"


def event_pos(event) -> QPoint:
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def to_qpoint(point: CalibrationPoint) -> QPointF:
    return QPointF(point.x, point.y)


def to_calibration_point(point: QPointF) -> CalibrationPoint:
    return CalibrationPoint(point.x(), point.y())


def clamp_point(point: QPointF, bounds: QRectF) -> QPointF:
    return QPointF(
        min(max(point.x(), bounds.left()), bounds.right()), min(max(point.y(), bounds.top()), bounds.bottom())
    )


def interpolate_qpoint(start: QPointF, end: QPointF, fraction: float) -> QPointF:
    fraction = max(0.0, min(1.0, fraction))
    return QPointF(start.x() + (end.x() - start.x()) * fraction, start.y() + (end.y() - start.y()) * fraction)


def distance_and_fraction(point: QPointF, start: QPointF, end: QPointF) -> tuple[float, float]:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length_squared = dx * dx + dy * dy
    if length_squared <= 0.0001:
        return (point_distance(point, start), 0.0)
    fraction = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    projected = interpolate_qpoint(start, end, fraction)
    return (point_distance(point, projected), fraction)


def point_distance(first: QPointF, second: QPointF) -> float:
    return hypot(first.x() - second.x(), first.y() - second.y())


def translation_correction(start: QPointF, end: QPointF, bounds: QRectF) -> QPointF:
    min_x = min(start.x(), end.x())
    max_x = max(start.x(), end.x())
    min_y = min(start.y(), end.y())
    max_y = max(start.y(), end.y())
    dx = 0.0
    dy = 0.0
    if min_x < bounds.left():
        dx = bounds.left() - min_x
    elif max_x > bounds.right():
        dx = bounds.right() - max_x
    if min_y < bounds.top():
        dy = bounds.top() - min_y
    elif max_y > bounds.bottom():
        dy = bounds.bottom() - max_y
    return QPointF(dx, dy)


DeleteTarget = tuple[str, str | int]
ACTIVE_Z = 8.0
BASE_Z = 5.0
