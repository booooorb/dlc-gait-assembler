from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from dlc_gait_assembly.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.domain.regions import NormalizedRect
from dlc_gait_assembly.gui import theme

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None


_REGION_BASE_Z = 5.0
_REGION_ACTIVE_Z = 7.0
_MAX_ENHANCEMENT_ZOOM = 32.0


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
        self.setZValue(_REGION_BASE_Z)
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
            rect.setLeft(_clamp_float(rect.left() + delta.x(), self._bounds.left(), rect.right() - min_size))
        if "right" in mode:
            rect.setRight(_clamp_float(rect.right() + delta.x(), rect.left() + min_size, self._bounds.right()))
        if "top" in mode:
            rect.setTop(_clamp_float(rect.top() + delta.y(), self._bounds.top(), rect.bottom() - min_size))
        if "bottom" in mode:
            rect.setBottom(_clamp_float(rect.bottom() + delta.y(), rect.top() + min_size, self._bounds.bottom()))

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
        painter.setPen(QPen(theme.color(theme.BACKGROUND, 220), max(1.0, 2.0 / self._view_scale())))
        painter.setBrush(theme.color(theme.NUMBER_ICON, 178))
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


class RegionPreviewView(QGraphicsView):
    regions_changed = Signal(object, object)
    operation_enabled_requested = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self._image_item = QGraphicsPixmapItem()
        self._image_item.setZValue(0)
        self._scene.addItem(self._image_item)

        self._source_image: QImage | None = None
        self._image_bounds = QRectF()
        self._crop_norm: NormalizedRect | None = None
        self._invert_norms: dict[int, NormalizedRect] = {}
        self._next_invert_id = 1
        self._mode = "crop"
        self._drag_start: QPointF | None = None
        self._drag_target: str | int | None = None
        self._crop_item: RegionRectItem | None = None
        self._invert_items: dict[int, RegionRectItem] = {}
        self._shade_items: list[QGraphicsRectItem] = []
        self._enhancements = EnhancementSettings()
        self._enhancement_zoom = 1.0
        self._fit_pending = False

    def set_frame(self, image: QImage | None) -> None:
        self._source_image = image.copy() if image is not None else None
        if self._source_image is None or self._source_image.isNull():
            self._image_bounds = QRectF()
            self._image_item.setPixmap(QPixmap())
            self._remove_region_items()
            self._emit_regions()
            return

        self._image_bounds = QRectF(0, 0, self._source_image.width(), self._source_image.height())
        self._scene.setSceneRect(self._image_bounds)
        self._render()
        self.reset_enhancement_zoom()
        self._emit_regions()

    def set_mode(self, mode: str) -> None:
        if mode not in {"crop", "invert", "enhancements", "trim"}:
            raise ValueError(f"Unknown preview mode: {mode}")
        self._mode = mode
        if mode != "enhancements":
            self.reset_enhancement_zoom()
        self._render()

    def enhancement_settings(self) -> EnhancementSettings:
        return self._enhancements

    def set_enhancements(self, settings: EnhancementSettings) -> None:
        if settings == self._enhancements:
            return
        self._enhancements = settings
        self._render()

    def reset_enhancements(self) -> None:
        self._enhancements = EnhancementSettings()
        self._render()

    def reset_enhancement_zoom(self) -> None:
        self._enhancement_zoom = 1.0
        if not self._image_bounds.isNull():
            self._schedule_fit_to_view()

    def reactivate(self) -> None:
        self._drag_start = None
        self._drag_target = None
        for item in self._region_items():
            item.reset_interaction()

        if self._image_bounds.isNull():
            return

        self._scene.setSceneRect(self._image_bounds)
        self._render()
        if not (self._mode == "enhancements" and self._enhancement_zoom > 1.001):
            self._schedule_fit_to_view()
        self.viewport().update()

    def create_default_region(self, mode: str | None = None) -> None:
        if self._image_bounds.isNull():
            return

        target_mode = mode or self._mode
        if target_mode not in {"crop", "invert"}:
            raise ValueError(f"Unknown preview mode: {target_mode}")

        rect = self._default_region_rect(target_mode)
        normalized = self._scene_rect_to_normalized(rect)
        selected_item: RegionRectItem | None = None

        if target_mode == "crop":
            if self._crop_norm is not None and self._crop_norm.is_usable():
                return
            self._crop_norm = normalized
        else:
            region_id = self._next_invert_id
            self._next_invert_id += 1
            self._invert_norms[region_id] = normalized

        self._render()
        if target_mode == "crop":
            selected_item = self._crop_item
        else:
            selected_item = self._invert_items.get(region_id)

        if selected_item is not None:
            self._scene.clearSelection()
            selected_item.setSelected(True)
        self._emit_regions()

    def delete_region(self, name: str) -> None:
        if name == "crop":
            self._crop_norm = None
        elif name.startswith("invert:"):
            self._invert_norms.pop(int(name.split(":", 1)[1]), None)
        else:
            raise ValueError(f"Unknown operation: {name}")

        self._render()
        self._emit_regions()

    def crop_region(self) -> NormalizedRect | None:
        return self._crop_norm

    def invert_regions(self) -> list[NormalizedRect]:
        return list(self._invert_norms.values())

    def invert_region(self) -> NormalizedRect | None:
        regions = self.invert_regions()
        return regions[0] if regions else None

    def region_snapshots(self) -> dict:
        if self._image_bounds.isNull():
            return {"width": 0, "height": 0, "crop": None, "inverts": []}

        crop = None
        if self._crop_norm is not None and self._crop_norm.is_usable():
            crop = self._normalized_to_pixel_edges(self._crop_norm)

        inverts = []
        for region_id, region in self._invert_norms.items():
            if region.is_usable():
                inverts.append({"id": region_id, **self._normalized_to_pixel_edges(region)})

        return {
            "width": int(round(self._image_bounds.width())),
            "height": int(round(self._image_bounds.height())),
            "crop": crop,
            "inverts": inverts,
        }

    def set_crop_pixel_edges(self, left: int, top: int, right: int, bottom: int) -> None:
        if self._image_bounds.isNull():
            return
        self._crop_norm = self._pixel_edges_to_normalized(left, top, right, bottom)
        self._render()
        self._emit_regions()

    def set_invert_pixel_edges(self, region_id: int, left: int, top: int, right: int, bottom: int) -> None:
        if self._image_bounds.isNull():
            return
        self._invert_norms[region_id] = self._pixel_edges_to_normalized(left, top, right, bottom)
        self._next_invert_id = max(self._next_invert_id, region_id + 1)
        self._render()
        self._emit_regions()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (
            not self._image_bounds.isNull()
            and not (self._mode == "enhancements" and self._enhancement_zoom > 1.001)
        ):
            self._schedule_fit_to_view()

    def _schedule_fit_to_view(self) -> None:
        if self._fit_pending:
            return
        self._fit_pending = True
        QTimer.singleShot(0, self._fit_to_view)

    def _fit_to_view(self) -> None:
        self._fit_pending = False
        if self._image_bounds.isNull() or (self._mode == "enhancements" and self._enhancement_zoom > 1.001):
            return
        self.resetTransform()
        self.fitInView(self._image_bounds, Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        pos = _event_pos(event)
        scene_pos = self.mapToScene(pos)
        if self._mode != "enhancements" or self._image_bounds.isNull() or not self._image_bounds.contains(scene_pos):
            super().wheelEvent(event)
            return

        direction = event.angleDelta().y()
        if direction == 0:
            event.accept()
            return

        factor = 1.25 if direction > 0 else 0.8
        self._zoom_at(pos, factor)
        event.accept()

    def mousePressEvent(self, event):
        pos = _event_pos(event)
        scene_pos = self.mapToScene(pos)

        if self._mode == "enhancements":
            super().mousePressEvent(event)
            return

        if event.button() == Qt.LeftButton and self._image_bounds.contains(scene_pos):
            if self._mode == "trim":
                super().mousePressEvent(event)
                return

            clicked_region = self._region_item_for_press(pos, scene_pos)
            if clicked_region is not None:
                self._raise_region_item(clicked_region)
                super().mousePressEvent(event)
                return

            self.operation_enabled_requested.emit(self._mode, True)
            self._drag_start = _clamp_point(scene_pos, self._image_bounds)
            if self._mode == "crop":
                self._drag_target = "crop"
            else:
                self._drag_target = self._next_invert_id
                self._next_invert_id += 1
            self._update_region_from_drag(self._drag_start, self._drag_start)
            event.accept()
            return

        super().mousePressEvent(event)

    def _zoom_at(self, view_pos: QPoint, factor: float) -> None:
        if self._image_bounds.isNull():
            return

        if factor > 1.0:
            factor = min(factor, _MAX_ENHANCEMENT_ZOOM / self._enhancement_zoom)
        else:
            factor = max(factor, 1.0 / self._enhancement_zoom)

        if abs(factor - 1.0) < 0.001:
            return

        scene_pos = self.mapToScene(view_pos)
        self.scale(factor, factor)
        self._enhancement_zoom *= factor
        if self._enhancement_zoom <= 1.001:
            self.reset_enhancement_zoom()
        else:
            self.centerOn(scene_pos)

    def _region_item_for_press(self, view_pos: QPoint, scene_pos: QPointF) -> RegionRectItem | None:
        candidate = self._best_region_hit(view_pos, scene_pos)
        return candidate[2] if candidate is not None else None

    def _cursor_for_hover(self, view_pos: QPoint, scene_pos: QPointF):
        candidate = self._best_region_hit(view_pos, scene_pos)
        if candidate is None:
            return Qt.ArrowCursor
        return candidate[2].cursor_for_scene(scene_pos)

    def _best_region_hit(self, view_pos: QPoint, scene_pos: QPointF) -> tuple[int, float, RegionRectItem] | None:
        candidates = []
        for order, item in enumerate(self.items(view_pos)):
            if not isinstance(item, RegionRectItem):
                continue

            hit = item.hit_test_scene(scene_pos)
            candidates.append((_hit_priority(hit), item.scene_area(), order, item))

        if not candidates:
            return None

        candidates.sort(key=lambda candidate: (candidate[0], candidate[1], candidate[2]))
        priority, area, _order, item = candidates[0]
        return priority, area, item

    def _raise_region_item(self, selected_item: RegionRectItem) -> None:
        for item in self._region_items():
            item.setZValue(_REGION_ACTIVE_Z if item is selected_item else _REGION_BASE_Z)

    def _region_items(self) -> list[RegionRectItem]:
        return [item for item in [self._crop_item, *self._invert_items.values()] if item is not None]

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            current = _clamp_point(self.mapToScene(_event_pos(event)), self._image_bounds)
            self._update_region_from_drag(self._drag_start, current)
            event.accept()
            return

        pos = _event_pos(event)
        cursor = self._cursor_for_hover(pos, self.mapToScene(pos))
        super().mouseMoveEvent(event)
        self.viewport().setCursor(Qt.CrossCursor if self._mode == "enhancements" else cursor)

    def mouseReleaseEvent(self, event):
        if self._drag_start is not None:
            current = _clamp_point(self.mapToScene(_event_pos(event)), self._image_bounds)
            self._update_region_from_drag(self._drag_start, current)
            self._drag_start = None
            self._drag_target = None
            self._emit_regions()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _update_region_from_drag(self, start: QPointF, current: QPointF) -> None:
        rect = QRectF(start, current).normalized().intersected(self._image_bounds)
        if rect.width() < 2 or rect.height() < 2:
            return

        normalized = self._scene_rect_to_normalized(rect)
        if self._drag_target == "crop":
            self._crop_norm = normalized
        elif isinstance(self._drag_target, int):
            self._invert_norms[self._drag_target] = normalized

        self._render()
        self._emit_regions()

    def _default_region_rect(self, mode: str) -> QRectF:
        bounds = self._image_bounds
        scale = 0.62 if mode == "crop" else 0.26
        width = min(bounds.width(), max(24.0, bounds.width() * scale))
        height = min(bounds.height(), max(24.0, bounds.height() * scale))

        offset_step = min(bounds.width(), bounds.height()) * 0.05
        offset = 0.0
        if mode == "invert":
            offset = offset_step * (len(self._invert_norms) % 6)

        left = bounds.center().x() - width / 2 + offset
        top = bounds.center().y() - height / 2 + offset
        left = _clamp_float(left, bounds.left(), bounds.right() - width)
        top = _clamp_float(top, bounds.top(), bounds.bottom() - height)
        return QRectF(left, top, width, height).intersected(bounds)

    def _on_item_changed(self, name: str, scene_rect: QRectF) -> None:
        normalized = self._scene_rect_to_normalized(scene_rect)
        if name == "crop":
            self._crop_norm = normalized
            self._update_crop_shade()
        elif name.startswith("invert:"):
            self._invert_norms[int(name.split(":", 1)[1])] = normalized
            self._refresh_pixmap()
        self._emit_regions()

    def _render(self) -> None:
        self._refresh_pixmap()
        self._sync_region_items()
        self._update_crop_shade()
        self._set_annotation_visibility(self._mode != "enhancements")

    def _refresh_pixmap(self) -> None:
        if self._source_image is None or self._source_image.isNull():
            self._image_item.setPixmap(QPixmap())
            return

        display = self._source_image.copy()
        for region_norm in self._invert_norms.values():
            if not region_norm.is_usable():
                continue
            rect = self._normalized_to_scene_rect(region_norm).toAlignedRect().intersected(display.rect())
            if rect.width() > 1 and rect.height() > 1:
                region = display.copy(rect).mirrored(False, True)
                painter = QPainter(display)
                painter.drawImage(rect.topLeft(), region)
                painter.end()

        display = self._apply_enhancements(display)
        self._image_item.setPixmap(QPixmap.fromImage(display))

    def _apply_enhancements(self, image: QImage) -> QImage:
        if not self._enhancements.is_enabled() or np is None:
            return image

        array = _qimage_to_rgb_array(image)
        if array is None:
            return image

        settings = self._enhancements
        frame = array.astype("float32") / 255.0

        frame *= 2.0 ** settings.exposure
        frame += settings.black_level

        input_black = min(settings.input_black, settings.input_white - 0.01)
        input_white = max(settings.input_white, input_black + 0.01)
        frame = (frame - input_black) / (input_white - input_black)
        output_black = min(settings.output_black, settings.output_white - 0.01)
        output_white = max(settings.output_white, output_black + 0.01)
        frame = output_black + frame * (output_white - output_black)

        frame += settings.brightness
        frame = (frame - 0.5) * settings.contrast + 0.5

        if abs(settings.tone_scale - 1.0) > 0.001:
            gamma = 1.0 / max(0.05, settings.tone_scale)
            frame = np.power(np.clip(frame, 0.0, 1.0), gamma)

        frame = np.clip(frame, 0.0, 1.0)

        if cv2 is not None and settings.sharpening > 0.001:
            blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
            frame = np.clip(frame + (frame - blurred) * settings.sharpening, 0.0, 1.0)

        if cv2 is not None and settings.cas > 0.001:
            blurred = cv2.GaussianBlur(frame, (0, 0), 0.65)
            detail = frame - blurred
            adaptive_weight = 1.0 - np.abs(frame * 2.0 - 1.0)
            frame = np.clip(frame + detail * adaptive_weight * settings.cas * 1.8, 0.0, 1.0)

        output = np.ascontiguousarray((frame * 255.0).round().astype("uint8"))
        height, width, _channels = output.shape
        return QImage(output.data, width, height, width * 3, QImage.Format_RGB888).copy()

    def _sync_region_items(self) -> None:
        self._crop_item = self._sync_one_item(
            self._crop_item,
            "crop",
            theme.color(theme.BACKGROUND, 210),
            self._crop_norm,
            fill_alpha=0,
        )

        for region_id in list(self._invert_items):
            if region_id not in self._invert_norms or not self._invert_norms[region_id].is_usable():
                self._scene.removeItem(self._invert_items.pop(region_id))

        for region_id, region in self._invert_norms.items():
            if not region.is_usable() or self._image_bounds.isNull():
                continue
            item = self._invert_items.get(region_id)
            if item is None:
                item = RegionRectItem(
                    f"invert:{region_id}",
                    QColor(theme.TOOL_2),
                    self._image_bounds,
                    self._on_item_changed,
                    self.delete_region,
                )
                self._scene.addItem(item)
                self._invert_items[region_id] = item
            item.set_bounds(self._image_bounds)
            item.set_scene_rect(self._normalized_to_scene_rect(region))

    def _set_annotation_visibility(self, visible: bool) -> None:
        for item in self._region_items():
            item.setVisible(visible)
        for item in self._shade_items:
            item.setVisible(visible)

    def _sync_one_item(
        self,
        item: RegionRectItem | None,
        name: str,
        color: QColor,
        region: NormalizedRect | None,
        fill_alpha: int = 36,
    ) -> RegionRectItem | None:
        if region is None or not region.is_usable() or self._image_bounds.isNull():
            if item is not None:
                self._scene.removeItem(item)
            return None

        if item is None:
            item = RegionRectItem(name, color, self._image_bounds, self._on_item_changed, self.delete_region, fill_alpha)
            self._scene.addItem(item)

        item.set_bounds(self._image_bounds)
        item.set_scene_rect(self._normalized_to_scene_rect(region))
        return item

    def _update_crop_shade(self) -> None:
        for item in self._shade_items:
            self._scene.removeItem(item)
        self._shade_items.clear()

        if self._crop_norm is None or not self._crop_norm.is_usable():
            return

        crop = self._normalized_to_scene_rect(self._crop_norm).intersected(self._image_bounds)
        bounds = self._image_bounds
        shade_rects = [
            QRectF(bounds.left(), bounds.top(), bounds.width(), crop.top() - bounds.top()),
            QRectF(bounds.left(), crop.bottom(), bounds.width(), bounds.bottom() - crop.bottom()),
            QRectF(bounds.left(), crop.top(), crop.left() - bounds.left(), crop.height()),
            QRectF(crop.right(), crop.top(), bounds.right() - crop.right(), crop.height()),
        ]
        brush = theme.color(theme.TEXT, 82)

        for rect in shade_rects:
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            item = QGraphicsRectItem(rect)
            item.setPen(QPen(Qt.NoPen))
            item.setBrush(brush)
            item.setZValue(2)
            item.setAcceptedMouseButtons(Qt.NoButton)
            self._scene.addItem(item)
            self._shade_items.append(item)

    def _remove_region_items(self) -> None:
        for item in [self._crop_item, *self._invert_items.values(), *self._shade_items]:
            if item is not None:
                self._scene.removeItem(item)
        self._crop_item = None
        self._invert_items.clear()
        self._shade_items.clear()

    def _scene_rect_to_normalized(self, rect: QRectF) -> NormalizedRect:
        bounds = self._image_bounds
        rect = rect.normalized().intersected(bounds)
        return NormalizedRect(
            x=rect.left() / bounds.width(),
            y=rect.top() / bounds.height(),
            width=rect.width() / bounds.width(),
            height=rect.height() / bounds.height(),
        ).clamped()

    def _normalized_to_scene_rect(self, rect: NormalizedRect) -> QRectF:
        rect = rect.clamped()
        bounds = self._image_bounds
        return QRectF(
            bounds.left() + rect.x * bounds.width(),
            bounds.top() + rect.y * bounds.height(),
            rect.width * bounds.width(),
            rect.height * bounds.height(),
        )

    def _normalized_to_pixel_edges(self, rect: NormalizedRect) -> dict[str, int]:
        scene_rect = self._normalized_to_scene_rect(rect)
        width = int(round(self._image_bounds.width()))
        height = int(round(self._image_bounds.height()))
        left = _clamp_int(int(round(scene_rect.left())), 0, max(0, width - 2))
        top = _clamp_int(int(round(scene_rect.top())), 0, max(0, height - 2))
        right = _clamp_int(int(round(scene_rect.right())), left + 2, width)
        bottom = _clamp_int(int(round(scene_rect.bottom())), top + 2, height)
        return {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": right - left,
            "height": bottom - top,
        }

    def _pixel_edges_to_normalized(self, left: int, top: int, right: int, bottom: int) -> NormalizedRect:
        width = int(round(self._image_bounds.width()))
        height = int(round(self._image_bounds.height()))
        left = _clamp_int(left, 0, max(0, width - 2))
        top = _clamp_int(top, 0, max(0, height - 2))
        right = _clamp_int(right, left + 2, width)
        bottom = _clamp_int(bottom, top + 2, height)
        return NormalizedRect(
            x=left / width,
            y=top / height,
            width=(right - left) / width,
            height=(bottom - top) / height,
        ).clamped()

    def _emit_regions(self) -> None:
        self.regions_changed.emit(self._crop_norm, self.invert_regions())


def _event_pos(event) -> QPoint:
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def _clamp_point(point: QPointF, bounds: QRectF) -> QPointF:
    return QPointF(
        min(max(point.x(), bounds.left()), bounds.right()),
        min(max(point.y(), bounds.top()), bounds.bottom()),
    )


def _hit_priority(hit: str) -> int:
    if hit == "delete":
        return 0
    if hit == "move":
        return 2
    return 1


def _qimage_to_rgb_array(image: QImage):
    if np is None:
        return None

    converted = image.convertToFormat(QImage.Format_RGB888)
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    buffer = converted.constBits()
    array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, bytes_per_line))
    return array[:, : width * 3].reshape((height, width, 3)).copy()


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
