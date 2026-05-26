from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from dlc_gait_assembly.domain.regions import NormalizedRect


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
        self.setZValue(5)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)

    def set_scene_rect(self, scene_rect: QRectF) -> None:
        self.setRect(0, 0, max(2.0, scene_rect.width()), max(2.0, scene_rect.height()))
        self.setPos(scene_rect.topLeft())

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
        painter.setPen(QPen(QColor(255, 255, 255, 220), max(1.0, 2.0 / self._view_scale())))
        painter.setBrush(QColor(214, 39, 40, 178))
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
        self.setMinimumSize(640, 420)

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
        self.fitInView(self._image_bounds, Qt.KeepAspectRatio)
        self._emit_regions()

    def set_mode(self, mode: str) -> None:
        if mode not in {"crop", "invert"}:
            raise ValueError(f"Unknown preview mode: {mode}")
        self._mode = mode

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
        if not self._image_bounds.isNull():
            self.fitInView(self._image_bounds, Qt.KeepAspectRatio)

    def mousePressEvent(self, event):
        pos = _event_pos(event)
        scene_pos = self.mapToScene(pos)
        clicked_item = self.itemAt(pos)

        if event.button() == Qt.LeftButton and self._image_bounds.contains(scene_pos):
            if isinstance(clicked_item, RegionRectItem):
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

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            current = _clamp_point(self.mapToScene(_event_pos(event)), self._image_bounds)
            self._update_region_from_drag(self._drag_start, current)
            event.accept()
            return

        super().mouseMoveEvent(event)

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

        self._image_item.setPixmap(QPixmap.fromImage(display))

    def _sync_region_items(self) -> None:
        self._crop_item = self._sync_one_item(
            self._crop_item,
            "crop",
            QColor(255, 255, 255, 210),
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
                    QColor("#c026d3"),
                    self._image_bounds,
                    self._on_item_changed,
                    self.delete_region,
                )
                self._scene.addItem(item)
                self._invert_items[region_id] = item
            item.set_scene_rect(self._normalized_to_scene_rect(region))

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
        brush = QColor(0, 0, 0, 82)

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


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
