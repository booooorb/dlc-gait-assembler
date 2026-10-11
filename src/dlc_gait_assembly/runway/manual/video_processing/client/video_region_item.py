"""Implement video-region handles, hit testing, dragging, resizing, and deletion."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import color as _dependency_theme_color


class RegionRectItem(QGraphicsRectItem):
    def __init__(self, name: str, color: QColor, bounds: QRectF, on_changed, on_deleted, fill_alpha: int = 36):
        super().__init__()
        self.name = name
        self._bounds = QRectF(bounds)
        self._on_changed = on_changed
        self._on_deleted = on_deleted
        self._drag_mode: str | None = None
        self._press_scene_pos = QPointF()
        self._press_scene_rect = QRectF()
        fill = QColor(color)
        fill.setAlpha(fill_alpha)
        self.setPen(QPen(color, 3))
        self.setBrush(fill)
        self.setZValue(REGION_BASE_Z)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)

    def set_bounds(self, bounds: QRectF) -> None:
        self._bounds = QRectF(bounds)

    def set_scene_rect(self, scene_rect: QRectF) -> None:
        self.setRect(0, 0, max(2.0, scene_rect.width()), max(2.0, scene_rect.height()))
        self.setPos(scene_rect.topLeft())

    def hit_test_scene(self, scene_pos: QPointF) -> str:
        return self._hit_test(self.mapFromScene(scene_pos))

    def cursor_for_scene(self, scene_pos: QPointF):
        return self._cursor_for_hit(self.hit_test_scene(scene_pos))

    def scene_area(self) -> float:
        rect = self.mapRectToScene(self.rect()).intersected(self._bounds)
        return rect.width() * rect.height()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        self._paint_delete_button(painter)

    def hoverMoveEvent(self, event):
        self.setCursor(self._cursor_for_hit(self._hit_test(event.pos())))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        hit = self._hit_test(event.pos())
        if hit == "delete":
            self._on_deleted(self.name)
            event.accept()
            return
        self.setSelected(True)
        self._drag_mode = hit
        self._press_scene_pos = event.scenePos()
        self._press_scene_rect = self.mapRectToScene(self.rect()).intersected(self._bounds)
        self.setCursor(self._cursor_for_hit(hit))
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._press_scene_pos
        self.set_scene_rect(self._rect_for_drag(self._drag_mode, delta))
        self._notify_changed()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_mode is not None:
            self._drag_mode = None
            self._notify_changed()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def reset_interaction(self) -> None:
        self._drag_mode = None
        self.setCursor(Qt.SizeAllCursor)

    def _notify_changed(self) -> None:
        self._on_changed(self.name, self.mapRectToScene(self.rect()).intersected(self._bounds))

    def _rect_for_drag(self, mode: str, delta: QPointF) -> QRectF:
        rect = QRectF(self._press_scene_rect)
        min_size = self._min_scene_size()
        if mode == "move":
            rect.translate(delta)
            if rect.left() < self._bounds.left():
                rect.moveLeft(self._bounds.left())
            if rect.top() < self._bounds.top():
                rect.moveTop(self._bounds.top())
            if rect.right() > self._bounds.right():
                rect.moveRight(self._bounds.right())
            if rect.bottom() > self._bounds.bottom():
                rect.moveBottom(self._bounds.bottom())
            return rect.intersected(self._bounds)
        if "left" in mode:
            rect.setLeft(clamp_float(rect.left() + delta.x(), self._bounds.left(), rect.right() - min_size))
        if "right" in mode:
            rect.setRight(clamp_float(rect.right() + delta.x(), rect.left() + min_size, self._bounds.right()))
        if "top" in mode:
            rect.setTop(clamp_float(rect.top() + delta.y(), self._bounds.top(), rect.bottom() - min_size))
        if "bottom" in mode:
            rect.setBottom(clamp_float(rect.bottom() + delta.y(), rect.top() + min_size, self._bounds.bottom()))
        return rect.normalized().intersected(self._bounds)

    def _hit_test(self, point: QPointF) -> str:
        if self._delete_button_rect().contains(point):
            return "delete"
        rect = self.rect()
        margin = self._edge_margin()
        near_left = abs(point.x() - rect.left()) <= margin
        near_right = abs(point.x() - rect.right()) <= margin
        near_top = abs(point.y() - rect.top()) <= margin
        near_bottom = abs(point.y() - rect.bottom()) <= margin
        if near_left and near_top:
            return "top-left"
        if near_right and near_top:
            return "top-right"
        if near_left and near_bottom:
            return "bottom-left"
        if near_right and near_bottom:
            return "bottom-right"
        if near_left:
            return "left"
        if near_right:
            return "right"
        if near_top:
            return "top"
        if near_bottom:
            return "bottom"
        return "move"

    def _cursor_for_hit(self, hit: str):
        return {
            "delete": Qt.PointingHandCursor,
            "move": Qt.SizeAllCursor,
            "left": Qt.SizeHorCursor,
            "right": Qt.SizeHorCursor,
            "top": Qt.SizeVerCursor,
            "bottom": Qt.SizeVerCursor,
            "top-left": Qt.SizeFDiagCursor,
            "bottom-right": Qt.SizeFDiagCursor,
            "top-right": Qt.SizeBDiagCursor,
            "bottom-left": Qt.SizeBDiagCursor,
        }.get(hit, Qt.ArrowCursor)

    def _paint_delete_button(self, painter: QPainter) -> None:
        rect = self._delete_button_rect()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(_dependency_theme_color(theme.BACKGROUND, 220), max(1.0, 2.0 / self._view_scale())))
        painter.setBrush(_dependency_theme_color(theme.NUMBER_ICON, 178))
        painter.drawEllipse(rect)
        pad = rect.width() * 0.32
        painter.drawLine(rect.left() + pad, rect.top() + pad, rect.right() - pad, rect.bottom() - pad)
        painter.drawLine(rect.right() - pad, rect.top() + pad, rect.left() + pad, rect.bottom() - pad)
        painter.restore()

    def _delete_button_rect(self) -> QRectF:
        size = 18.0 / self._view_scale()
        rect = self.rect()
        inset = 3.0 / self._view_scale()
        return QRectF(rect.right() - size - inset, rect.top() + inset, size, size)

    def _edge_margin(self) -> float:
        return max(4.0, 9.0 / self._view_scale())

    def _min_scene_size(self) -> float:
        return max(8.0, 18.0 / self._view_scale())

    def _view_scale(self) -> float:
        views = self.scene().views() if self.scene() is not None else []
        if not views:
            return 1.0
        scale = views[0].transform().m11()
        return scale if scale > 0 else 1.0


def event_pos(event) -> QPoint:
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def clamp_point(point: QPointF, bounds: QRectF) -> QPointF:
    return QPointF(
        min(max(point.x(), bounds.left()), bounds.right()), min(max(point.y(), bounds.top()), bounds.bottom())
    )


def hit_priority(hit: str) -> int:
    if hit == "delete":
        return 0
    if hit == "move":
        return 2
    return 1


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


REGION_BASE_Z = 5.0
