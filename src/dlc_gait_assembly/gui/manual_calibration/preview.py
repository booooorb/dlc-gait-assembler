from __future__ import annotations

from math import hypot

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QPushButton

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.services.domain.calibration import CalibrationPoint, CalibrationStick

DeleteTarget = tuple[str, str | int]

_ACTIVE_Z = 8.0
_BASE_Z = 5.0
_MAX_ZOOM = 32.0
_MIN_ZOOM = 0.25
_CREATE_LINE_DRAG_DISTANCE = 16


class CalibrationPreviewView(QGraphicsView):
    sticks_changed = Signal()
    stick_delete_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self._image_item = QGraphicsPixmapItem()
        self._image_item.setZValue(0)
        self._scene.addItem(self._image_item)
        self._image_bounds = QRectF()
        self._mode = "x"
        self._zoom = 1.0
        self._sticks: dict[str, CalibrationStick] = {}
        self._stick_items: dict[str, CalibrationStickItem] = {}
        self._location_failure_markers: dict[str, set[int]] = {}
        self._drag_start: QPointF | None = None
        self._drag_start_view_pos: QPoint | None = None
        self._drag_axis: str | None = None
        self._draft_key: str | None = None
        self._right_delete_target: DeleteTarget | None = None
        self._right_press_view_pos: QPoint | None = None
        self._fit_pending = False
        self._reset_zoom_button = QPushButton("Reset", self.viewport())
        self._reset_zoom_button.setObjectName("PreviewResetZoomButton")
        self._reset_zoom_button.setToolTip("Reset zoom")
        self._reset_zoom_button.setFixedSize(52, 24)
        self._reset_zoom_button.clicked.connect(self.reset_zoom)
        self._reset_zoom_button.hide()

    def set_frame(self, image: QImage | None) -> None:
        if image is None or image.isNull():
            self._image_item.setPixmap(QPixmap())
            self._image_bounds = QRectF()
            self._scene.setSceneRect(QRectF())
            self._remove_stick_items()
            self._sticks.clear()
            self._location_failure_markers.clear()
            self._update_reset_zoom_button()
            self.sticks_changed.emit()
            return

        same_size = (
            not self._image_bounds.isNull()
            and int(round(self._image_bounds.width())) == image.width()
            and int(round(self._image_bounds.height())) == image.height()
        )
        self._image_bounds = QRectF(0, 0, image.width(), image.height())
        if not same_size:
            self._scene.setSceneRect(self._image_bounds)
        self._image_item.setPixmap(QPixmap.fromImage(image))
        self._image_item.setPos(0, 0)
        self._sync_items()
        if same_size:
            if self._zoom <= 1.001:
                self._schedule_fit_to_view()
        else:
            self.reset_zoom()

    def set_mode(self, mode: str) -> None:
        if mode not in {"x", "y", "cm"}:
            raise ValueError(f"Unknown calibration tool: {mode}")
        self._mode = mode
        self.setDragMode(QGraphicsView.NoDrag if mode in {"x", "y", "cm"} else QGraphicsView.ScrollHandDrag)

    def clear_calibration(self) -> None:
        self._remove_stick_items()
        self._sticks.clear()
        self._location_failure_markers.clear()
        self._drag_start = None
        self._drag_start_view_pos = None
        self._drag_axis = None
        self._draft_key = None
        self._right_delete_target = None
        self._right_press_view_pos = None
        self.sticks_changed.emit()

    def calibration_sticks(self) -> list[CalibrationStick]:
        return sorted(self._sticks.values(), key=lambda stick: (stick.view_index, stick.axis))

    def set_calibration_sticks(self, sticks: list[CalibrationStick] | tuple[CalibrationStick, ...]) -> None:
        self._remove_stick_items()
        self._sticks = {_stick_key(stick.axis, stick.view_index): stick for stick in sticks}
        self._location_failure_markers = {key: markers for key, markers in self._location_failure_markers.items() if key in self._sticks}
        self._sync_items()
        self.sticks_changed.emit()

    def set_location_failure_markers(self, markers_by_stick: dict[str, set[int]] | dict[str, tuple[int, ...]]) -> None:
        self._location_failure_markers = {key: set(markers) for key, markers in markers_by_stick.items() if key in self._sticks}
        self._sync_items()

    def delete_stick(self, key: str) -> None:
        if key not in self._sticks:
            return
        self._sticks.pop(key)
        self._location_failure_markers.pop(key, None)
        item = self._stick_items.pop(key, None)
        if item is not None:
            self._scene.removeItem(item)
        self.sticks_changed.emit()

    def reset_zoom(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        if not self._image_bounds.isNull():
            self._schedule_fit_to_view()
        self._update_reset_zoom_button()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_reset_zoom_button()
        if self._zoom <= 1.001 and not self._image_bounds.isNull():
            self._schedule_fit_to_view()

    def _schedule_fit_to_view(self) -> None:
        if self._fit_pending:
            return
        self._fit_pending = True
        QTimer.singleShot(0, self._fit_to_view)

    def _fit_to_view(self) -> None:
        self._fit_pending = False
        if self._image_bounds.isNull() or self._zoom > 1.001:
            return
        self.resetTransform()
        self.fitInView(self._image_bounds, Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        if self._image_bounds.isNull():
            super().wheelEvent(event)
            return

        direction = event.angleDelta().y()
        if direction == 0:
            return

        factor = 1.25 if direction > 0 else 0.8
        new_zoom = self._zoom * factor
        if new_zoom < _MIN_ZOOM:
            factor = _MIN_ZOOM / self._zoom
            new_zoom = _MIN_ZOOM
        elif new_zoom > _MAX_ZOOM:
            factor = _MAX_ZOOM / self._zoom
            new_zoom = _MAX_ZOOM

        self.scale(factor, factor)
        self._zoom = new_zoom
        self._update_reset_zoom_button()
        event.accept()

    def _update_reset_zoom_button(self) -> None:
        visible = not self._image_bounds.isNull() and self._zoom > 1.001
        self._reset_zoom_button.setVisible(visible)
        if visible:
            self._position_reset_zoom_button()
            self._reset_zoom_button.raise_()

    def _position_reset_zoom_button(self) -> None:
        margin = 10
        self._reset_zoom_button.move(
            max(margin, self.viewport().width() - self._reset_zoom_button.width() - margin),
            max(margin, self.viewport().height() - self._reset_zoom_button.height() - margin),
        )

    def mousePressEvent(self, event) -> None:
        pos = _event_pos(event)
        scene_pos = self.mapToScene(pos)

        if event.button() == Qt.RightButton:
            target = self._delete_target_at_view_pos(pos, scene_pos)
            if target is not None:
                self._right_delete_target = target
                self._right_press_view_pos = QPoint(pos)
                event.accept()
                return

        if event.button() == Qt.LeftButton and self._mode == "cm" and self._image_bounds.contains(scene_pos):
            if self._add_marker_at(scene_pos):
                event.accept()
                return

        if event.button() == Qt.LeftButton and self._mode in {"x", "y"} and self._image_bounds.contains(scene_pos):
            if self._stick_item_at_view_pos(pos) is not None or self._is_near_existing_stick(scene_pos):
                super().mousePressEvent(event)
                return

            self._drag_start = _clamp_point(scene_pos, self._image_bounds)
            self._drag_start_view_pos = QPoint(pos)
            self._drag_axis = self._mode
            self._draft_key = None
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None and self._drag_axis is not None:
            current = _clamp_point(self.mapToScene(_event_pos(event)), self._image_bounds)
            if self._draft_key is None:
                if self._drag_start_view_pos is None:
                    return
                if _point_distance(QPointF(self._drag_start_view_pos), QPointF(_event_pos(event))) < _CREATE_LINE_DRAG_DISTANCE:
                    event.accept()
                    return

                view_index = self._next_view_index(self._drag_axis)
                self._draft_key = _stick_key(self._drag_axis, view_index)
                self._set_stick(
                    CalibrationStick(
                        self._drag_axis,
                        view_index,
                        _to_calibration_point(self._drag_start),
                        _to_calibration_point(current),
                    )
                )
            else:
                stick = self._sticks[self._draft_key]
                self._set_stick(
                    CalibrationStick(
                        stick.axis,
                        stick.view_index,
                        stick.start,
                        _to_calibration_point(current),
                        stick.marker_positions,
                    )
                )
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.RightButton and self._right_delete_target is not None:
            pos = _event_pos(event)
            target = self._right_delete_target
            press_pos = self._right_press_view_pos
            self._right_delete_target = None
            self._right_press_view_pos = None
            if press_pos is None or _point_distance(QPointF(press_pos), QPointF(pos)) <= 6.0:
                self._apply_delete_target(target)
            event.accept()
            return

        if self._drag_start is not None:
            if self._draft_key is not None and self._draft_key in self._sticks:
                stick = self._sticks[self._draft_key]
                if _point_distance(_to_qpoint(stick.start), _to_qpoint(stick.end)) < 4.0:
                    self.delete_stick(self._draft_key)
            self._drag_start = None
            self._drag_start_view_pos = None
            self._drag_axis = None
            self._draft_key = None
            self.sticks_changed.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _set_stick(self, stick: CalibrationStick) -> None:
        if self._image_bounds.isNull():
            return
        key = _stick_key(stick.axis, stick.view_index)
        clamped = CalibrationStick(
            stick.axis,
            stick.view_index,
            _to_calibration_point(_clamp_point(_to_qpoint(stick.start), self._image_bounds)),
            _to_calibration_point(_clamp_point(_to_qpoint(stick.end), self._image_bounds)),
            tuple(sorted(position for position in stick.marker_positions if 0.0 < position < 1.0)),
        )
        self._sticks[key] = clamped
        self._sync_items()
        self.sticks_changed.emit()

    def _sync_items(self) -> None:
        for key in list(self._stick_items):
            if key not in self._sticks:
                self._scene.removeItem(self._stick_items.pop(key))

        for key, stick in self._sticks.items():
            item = self._stick_items.get(key)
            if item is None:
                item = CalibrationStickItem(stick, self._image_bounds, self._set_stick)
                self._scene.addItem(item)
                self._stick_items[key] = item
            else:
                item.set_bounds(self._image_bounds)
                item.set_stick(stick)
            item.set_location_failure_marker_indices(self._location_failure_markers.get(key, set()))

    def _remove_stick_items(self) -> None:
        for item in self._stick_items.values():
            self._scene.removeItem(item)
        self._stick_items.clear()

    def _next_view_index(self, axis: str) -> int:
        used = [stick.view_index for stick in self._sticks.values() if stick.axis == axis]
        candidate = 1
        while candidate in used:
            candidate += 1
        return candidate

    def _add_marker_at(self, scene_pos: QPointF) -> bool:
        candidate: tuple[float, float, CalibrationStickItem] | None = None
        for item in self._stick_items.values():
            distance, position = item.distance_and_position_for_scene_point(scene_pos)
            if position <= 0.02 or position >= 0.98:
                continue
            if candidate is None or distance < candidate[0]:
                candidate = (distance, position, item)

        if candidate is None:
            return False

        distance, position, item = candidate
        if distance > item.hit_radius() * 1.8:
            return False

        stick = item.stick()
        positions = list(stick.marker_positions)
        if any(abs(existing - position) < 0.018 for existing in positions):
            return False
        positions.append(position)
        self._set_stick(
            CalibrationStick(
                stick.axis,
                stick.view_index,
                stick.start,
                stick.end,
                tuple(sorted(positions)),
            )
        )
        return True

    def _delete_marker(self, key: str, marker_index: int) -> None:
        stick = self._sticks.get(key)
        if stick is None:
            return
        markers = list(stick.marker_positions)
        if not 0 <= marker_index < len(markers):
            return
        markers.pop(marker_index)
        self._set_stick(
            CalibrationStick(
                stick.axis,
                stick.view_index,
                stick.start,
                stick.end,
                tuple(markers),
            )
        )

    def _apply_delete_target(self, target: DeleteTarget) -> None:
        key, detail = target
        if isinstance(detail, int):
            self._delete_marker(key, detail)
            return

        stick = self._sticks.get(key)
        if stick is not None:
            name = stick.name
            QTimer.singleShot(0, lambda: self.stick_delete_requested.emit(key, name))

    def _delete_target_at_view_pos(self, view_pos: QPoint, scene_pos: QPointF) -> DeleteTarget | None:
        for item in self.items(view_pos):
            if not isinstance(item, CalibrationStickItem):
                continue
            target = item.delete_target_for_scene_pos(scene_pos)
            if target is not None:
                return target
        return None

    def _stick_item_at_view_pos(self, pos: QPoint) -> CalibrationStickItem | None:
        for item in self.items(pos):
            if isinstance(item, CalibrationStickItem):
                return item
        return None

    def _is_near_existing_stick(self, scene_pos: QPointF) -> bool:
        for item in self._stick_items.values():
            distance, _position = item.distance_and_position_for_scene_point(scene_pos)
            if distance <= item.creation_guard_radius():
                return True
        return False


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
        self.setZValue(_BASE_Z)
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
        start = _to_qpoint(self._stick.start)
        end = _to_qpoint(self._stick.end)
        rect = QRectF(start, end).normalized()
        margin = self.hit_radius() + 54.0 / self._view_scale()
        return rect.adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        start = _to_qpoint(self._stick.start)
        end = _to_qpoint(self._stick.end)
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

        start = _to_qpoint(self._stick.start)
        end = _to_qpoint(self._stick.end)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(color, line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(start, end)

        ordered_markers = self._marker_qpoints(include_ends=True)
        end_marker_index = len(ordered_markers) - 1
        self._paint_handle(painter, start, color, radius, scale, 0 in self._location_failure_marker_indices)
        self._paint_handle(painter, end, color, radius, scale, end_marker_index in self._location_failure_marker_indices)

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
        self.setZValue(_ACTIVE_Z)
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
            self.setZValue(_BASE_Z)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def distance_and_position_for_scene_point(self, point: QPointF) -> tuple[float, float]:
        start = _to_qpoint(self._stick.start)
        end = _to_qpoint(self._stick.end)
        return _distance_and_fraction(point, start, end)

    def delete_target_for_scene_pos(self, scene_pos: QPointF) -> DeleteTarget | None:
        hit = self._hit_test(self.mapFromScene(scene_pos))
        key = _stick_key(self._stick.axis, self._stick.view_index)
        if isinstance(hit, int):
            return key, hit
        if hit != "none":
            return key, "stick"
        return None

    def hit_radius(self) -> float:
        return max(0.35, 13.0 / self._view_scale())

    def visual_radius(self) -> float:
        return max(0.12, 4.0 / self._view_scale())

    def creation_guard_radius(self) -> float:
        return max(self.hit_radius() * 2.4, 26.0 / self._view_scale())

    def _hit_test(self, point: QPointF) -> str | int:
        for index, marker_point in enumerate(self._marker_qpoints(include_ends=False)):
            if _point_distance(point, marker_point) <= self.hit_radius() * 1.35:
                return index

        if _point_distance(point, _to_qpoint(self._stick.start)) <= self.hit_radius() * 1.45:
            return "start"
        if _point_distance(point, _to_qpoint(self._stick.end)) <= self.hit_radius() * 1.45:
            return "end"

        distance, _fraction = self.distance_and_position_for_scene_point(point)
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
        start = _to_qpoint(stick.start)
        end = _to_qpoint(stick.end)
        markers = list(stick.marker_positions)

        if mode == "start":
            start = _clamp_point(start + delta, self._bounds)
        elif mode == "end":
            end = _clamp_point(end + delta, self._bounds)
        elif mode == "move":
            moved_start = start + delta
            moved_end = end + delta
            correction = _translation_correction(moved_start, moved_end, self._bounds)
            start = moved_start + correction
            end = moved_end + correction
        elif isinstance(mode, int) and 0 <= mode < len(markers):
            target = _clamp_point(self._press_pos + delta, self._bounds)
            _distance, fraction = _distance_and_fraction(target, start, end)
            markers[mode] = max(0.01, min(0.99, fraction))

        return CalibrationStick(
            stick.axis,
            stick.view_index,
            _to_calibration_point(start),
            _to_calibration_point(end),
            tuple(sorted(markers)),
        )

    def _marker_qpoints(self, include_ends: bool) -> list[QPointF]:
        points = []
        positions = self._stick.ordered_marker_positions() if include_ends else self._stick.marker_positions
        start = _to_qpoint(self._stick.start)
        end = _to_qpoint(self._stick.end)
        for position in positions:
            points.append(_interpolate_qpoint(start, end, position))
        return points

    def _paint_label(self, painter: QPainter, color: QColor, start: QPointF, end: QPointF) -> None:
        scale = self._view_scale()
        midpoint = _interpolate_qpoint(start, end, 0.52)
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

    def _paint_handle(self, painter: QPainter, point: QPointF, color: QColor, radius: float, scale: float, failed: bool = False) -> None:
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


def _stick_key(axis: str, view_index: int) -> str:
    return f"{axis}:{view_index}"


def _event_pos(event) -> QPoint:
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def _to_qpoint(point: CalibrationPoint) -> QPointF:
    return QPointF(point.x, point.y)


def _to_calibration_point(point: QPointF) -> CalibrationPoint:
    return CalibrationPoint(point.x(), point.y())


def _clamp_point(point: QPointF, bounds: QRectF) -> QPointF:
    return QPointF(
        min(max(point.x(), bounds.left()), bounds.right()),
        min(max(point.y(), bounds.top()), bounds.bottom()),
    )


def _interpolate_qpoint(start: QPointF, end: QPointF, fraction: float) -> QPointF:
    fraction = max(0.0, min(1.0, fraction))
    return QPointF(start.x() + (end.x() - start.x()) * fraction, start.y() + (end.y() - start.y()) * fraction)


def _distance_and_fraction(point: QPointF, start: QPointF, end: QPointF) -> tuple[float, float]:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length_squared = dx * dx + dy * dy
    if length_squared <= 0.0001:
        return _point_distance(point, start), 0.0
    fraction = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    projected = _interpolate_qpoint(start, end, fraction)
    return _point_distance(point, projected), fraction


def _point_distance(first: QPointF, second: QPointF) -> float:
    return hypot(first.x() - second.x(), first.y() - second.y())


def _translation_correction(start: QPointF, end: QPointF, bounds: QRectF) -> QPointF:
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
