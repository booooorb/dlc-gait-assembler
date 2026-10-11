"""Manage calibration zoom, selection, reference-stick drawing, and editing interactions."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QPushButton

from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick
from dlc_gait_assembly.runway.manual.calibration.client.calibration_stick_item import (
    CalibrationStickItem,
    DeleteTarget,
    clamp_point,
    event_pos,
    point_distance,
    stick_key,
    to_calibration_point,
    to_qpoint,
)

MAX_ZOOM = 32.0
MIN_ZOOM = 0.25
CREATE_LINE_DRAG_DISTANCE = 16


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
            and (int(round(self._image_bounds.height())) == image.height())
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
        self._sticks = {stick_key(stick.axis, stick.view_index): stick for stick in sticks}
        self._location_failure_markers = {
            key: markers for (key, markers) in self._location_failure_markers.items() if key in self._sticks
        }
        self._sync_items()
        self.sticks_changed.emit()

    def set_location_failure_markers(self, markers_by_stick: dict[str, set[int]] | dict[str, tuple[int, ...]]) -> None:
        self._location_failure_markers = {
            key: set(markers) for (key, markers) in markers_by_stick.items() if key in self._sticks
        }
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
        if self._zoom <= 1.001 and (not self._image_bounds.isNull()):
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
        if new_zoom < MIN_ZOOM:
            factor = MIN_ZOOM / self._zoom
            new_zoom = MIN_ZOOM
        elif new_zoom > MAX_ZOOM:
            factor = MAX_ZOOM / self._zoom
            new_zoom = MAX_ZOOM
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
        pos = event_pos(event)
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
            self._drag_start = clamp_point(scene_pos, self._image_bounds)
            self._drag_start_view_pos = QPoint(pos)
            self._drag_axis = self._mode
            self._draft_key = None
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None and self._drag_axis is not None:
            current = clamp_point(self.mapToScene(event_pos(event)), self._image_bounds)
            if self._draft_key is None:
                if self._drag_start_view_pos is None:
                    return
                if (
                    point_distance(QPointF(self._drag_start_view_pos), QPointF(event_pos(event)))
                    < CREATE_LINE_DRAG_DISTANCE
                ):
                    event.accept()
                    return
                view_index = self._next_view_index(self._drag_axis)
                self._draft_key = stick_key(self._drag_axis, view_index)
                self._set_stick(
                    CalibrationStick(
                        self._drag_axis,
                        view_index,
                        to_calibration_point(self._drag_start),
                        to_calibration_point(current),
                    )
                )
            else:
                stick = self._sticks[self._draft_key]
                self._set_stick(
                    CalibrationStick(
                        stick.axis, stick.view_index, stick.start, to_calibration_point(current), stick.marker_positions
                    )
                )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.RightButton and self._right_delete_target is not None:
            pos = event_pos(event)
            target = self._right_delete_target
            press_pos = self._right_press_view_pos
            self._right_delete_target = None
            self._right_press_view_pos = None
            if press_pos is None or point_distance(QPointF(press_pos), QPointF(pos)) <= 6.0:
                self._apply_delete_target(target)
            event.accept()
            return
        if self._drag_start is not None:
            if self._draft_key is not None and self._draft_key in self._sticks:
                stick = self._sticks[self._draft_key]
                if point_distance(to_qpoint(stick.start), to_qpoint(stick.end)) < 4.0:
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
        key = stick_key(stick.axis, stick.view_index)
        clamped = CalibrationStick(
            stick.axis,
            stick.view_index,
            to_calibration_point(clamp_point(to_qpoint(stick.start), self._image_bounds)),
            to_calibration_point(clamp_point(to_qpoint(stick.end), self._image_bounds)),
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
            (distance, position) = item.distance_and_position_for_scene_point(scene_pos)
            if position <= 0.02 or position >= 0.98:
                continue
            if candidate is None or distance < candidate[0]:
                candidate = (distance, position, item)
        if candidate is None:
            return False
        (distance, position, item) = candidate
        if distance > item.hit_radius() * 1.8:
            return False
        stick = item.stick()
        positions = list(stick.marker_positions)
        if any(abs(existing - position) < 0.018 for existing in positions):
            return False
        positions.append(position)
        self._set_stick(
            CalibrationStick(stick.axis, stick.view_index, stick.start, stick.end, tuple(sorted(positions)))
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
        self._set_stick(CalibrationStick(stick.axis, stick.view_index, stick.start, stick.end, tuple(markers)))

    def _apply_delete_target(self, target: DeleteTarget) -> None:
        (key, detail) = target
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
            (distance, _position) = item.distance_and_position_for_scene_point(scene_pos)
            if distance <= item.creation_guard_radius():
                return True
        return False
