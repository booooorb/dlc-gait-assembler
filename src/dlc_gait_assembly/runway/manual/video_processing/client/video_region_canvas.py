"""Display decoded frames, crop shading, inversion overlays, and canvas coordinates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import CropRegion, NormalizedRect
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_operations import RegionEditorState
from dlc_gait_assembly.runway.manual.video_processing.client.video_inversion_controls import VideoInversionControls
from dlc_gait_assembly.runway.manual.video_processing.client.video_preview_effects import VideoPreviewEffects
from dlc_gait_assembly.runway.manual.video_processing.client.video_region_item import (
    REGION_BASE_Z,
    RegionRectItem,
    clamp_float,
    clamp_int,
    clamp_point,
    event_pos,
    hit_priority,
)
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import color as _dependency_theme_color

try:
    import cv2
except ImportError:
    cv2 = None
try:
    import numpy as np
except ImportError:
    np = None
REGION_ACTIVE_Z = 7.0
MAX_ENHANCEMENT_ZOOM = 32.0


class RegionPreviewView(QGraphicsView):
    regions_changed = Signal(object, object)
    operation_enabled_requested = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.effects = VideoPreviewEffects(self)
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
        self._region_state = RegionEditorState()
        self._crop_norms = self._region_state.crop_norms
        self._crop_names = self._region_state.crop_names
        self._crop_flip_horizontal = self._region_state.crop_flip_horizontal
        self._crop_flip_vertical = self._region_state.crop_flip_vertical
        self._crop_flip_horizontal_video_paths = self._region_state.crop_flip_horizontal_video_paths
        self._invert_norms = self._region_state.invert_norms
        self._mode = "crop"
        self._drag_start: QPointF | None = None
        self._drag_target: str | int | None = None
        self._crop_items: dict[int, RegionRectItem] = {}
        self._invert_items: dict[int, RegionRectItem] = {}
        self.inversions = VideoInversionControls(self)
        self._shade_items: list[QGraphicsPathItem] = []
        self._enhancements = EnhancementSettings()
        self._enhancement_zoom = 1.0
        self._fit_pending = False

    @property
    def _default_crop_flip_horizontal(self) -> bool:
        return self._region_state.default_crop_flip_horizontal

    @_default_crop_flip_horizontal.setter
    def _default_crop_flip_horizontal(self, value: bool) -> None:
        self._region_state.default_crop_flip_horizontal = value

    @property
    def _default_crop_flip_horizontal_video_paths(self) -> frozenset[str] | None:
        return self._region_state.default_crop_flip_horizontal_video_paths

    @_default_crop_flip_horizontal_video_paths.setter
    def _default_crop_flip_horizontal_video_paths(self, value: frozenset[str] | None) -> None:
        self._region_state.default_crop_flip_horizontal_video_paths = value

    @property
    def _next_crop_id(self) -> int:
        return self._region_state.next_crop_id

    @_next_crop_id.setter
    def _next_crop_id(self, value: int) -> None:
        self._region_state.next_crop_id = value

    @property
    def _next_invert_id(self) -> int:
        return self._region_state.next_invert_id

    @_next_invert_id.setter
    def _next_invert_id(self, value: int) -> None:
        self._region_state.next_invert_id = value

    @property
    def _current_video_path(self) -> str | None:
        return self._region_state.current_video_path

    @_current_video_path.setter
    def _current_video_path(self, value: str | None) -> None:
        self._region_state.current_video_path = value

    def set_frame(self, image: QImage | None) -> None:
        self._source_image = image.copy() if image is not None else None
        if self._source_image is None or self._source_image.isNull():
            self._image_bounds = QRectF()
            self._image_item.setPixmap(QPixmap())
            self._remove_region_items()
            self._emit_regions()
            return
        same_size = (
            not self._image_bounds.isNull()
            and int(round(self._image_bounds.width())) == self._source_image.width()
            and (int(round(self._image_bounds.height())) == self._source_image.height())
        )
        self._image_bounds = QRectF(0, 0, self._source_image.width(), self._source_image.height())
        if not same_size:
            self._scene.setSceneRect(self._image_bounds)
        self._render()
        if same_size:
            if not (self._mode == "enhancements" and self._enhancement_zoom > 1.001):
                self._schedule_fit_to_view()
        else:
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
            region_id = self._next_crop_id
            self._next_crop_id += 1
            self._crop_norms[region_id] = normalized
            self._crop_names[region_id] = self._default_crop_name(region_id)
            self._initialize_crop_region_settings(region_id)
        else:
            region_id = self._next_invert_id
            self._next_invert_id += 1
            self._invert_norms[region_id] = normalized
        if target_mode == "crop":
            self._refresh_region_annotations()
        else:
            self._render()
        if target_mode == "crop":
            selected_item = self._crop_items.get(region_id)
        else:
            selected_item = self._invert_items.get(region_id)
        if selected_item is not None:
            self._scene.clearSelection()
            selected_item.setSelected(True)
        self._emit_regions()

    def delete_region(self, name: str) -> None:
        if name.startswith("crop:"):
            region_id = int(name.split(":", 1)[1])
            self._crop_norms.pop(region_id, None)
            self._crop_names.pop(region_id, None)
            self._crop_flip_horizontal.pop(region_id, None)
            self._crop_flip_vertical.pop(region_id, None)
            self._crop_flip_horizontal_video_paths.pop(region_id, None)
        elif name.startswith("invert:"):
            self._invert_norms.pop(int(name.split(":", 1)[1]), None)
        else:
            raise ValueError(f"Unknown operation: {name}")
        if name.startswith("crop:"):
            self._refresh_region_annotations()
        else:
            self._render()
        self._emit_regions()

    def crop_region(self) -> NormalizedRect | None:
        regions = self.crop_regions()
        return regions[0].rect if regions else None

    def crop_regions(self) -> tuple[CropRegion, ...]:
        regions = []
        for index, (region_id, rect) in enumerate(sorted(self._crop_norms.items()), start=1):
            if rect.is_usable():
                regions.append(
                    CropRegion(
                        self._crop_names.get(region_id, f"Region {index}"),
                        rect,
                        flip_horizontal=self._crop_flip_horizontal.get(region_id, False),
                        flip_vertical=self._crop_flip_vertical.get(region_id, False),
                        flip_horizontal_video_paths=self._crop_flip_horizontal_video_paths.get(region_id),
                    )
                )
        return tuple(regions)

    def set_crop_regions(self, regions: tuple[CropRegion, ...]) -> None:
        self._region_state.clear_crops()
        for region in regions:
            if not region.rect.is_usable():
                continue
            region_id = self._next_crop_id
            self._next_crop_id += 1
            self._crop_norms[region_id] = region.rect.clamped()
            self._crop_names[region_id] = region.name.strip() or self._default_crop_name(region_id)
            self._crop_flip_horizontal[region_id] = bool(region.flip_horizontal)
            self._crop_flip_vertical[region_id] = bool(region.flip_vertical)
            self._crop_flip_horizontal_video_paths[region_id] = (
                None
                if region.flip_horizontal_video_paths is None
                else frozenset(normalize_path(path) for path in region.flip_horizontal_video_paths)
            )
        self._render()
        self._emit_regions()

    def invert_regions(self) -> list[NormalizedRect]:
        return self.inversions.invert_regions()

    def set_invert_regions(self, regions: tuple[NormalizedRect, ...]) -> None:
        return self.inversions.set_invert_regions(regions)

    def invert_region(self) -> NormalizedRect | None:
        return self.inversions.invert_region()

    def region_snapshots(self) -> dict:
        if self._image_bounds.isNull():
            return {"width": 0, "height": 0, "crop": None, "crops": [], "inverts": []}
        crops = []
        for index, (region_id, region) in enumerate(sorted(self._crop_norms.items()), start=1):
            if region.is_usable():
                crops.append(
                    {
                        "id": region_id,
                        "name": self._crop_names.get(region_id, f"Region {index}"),
                        "flip_horizontal": self._crop_flip_horizontal.get(region_id, False),
                        "flip_vertical": self._crop_flip_vertical.get(region_id, False),
                        "flip_horizontal_video_paths": self._crop_flip_horizontal_video_paths.get(region_id),
                        **self._normalized_to_pixel_edges(region),
                    }
                )
        crop = crops[0] if crops else None
        inverts = []
        for region_id, region in self._invert_norms.items():
            if region.is_usable():
                inverts.append({"id": region_id, **self._normalized_to_pixel_edges(region)})
        return {
            "width": int(round(self._image_bounds.width())),
            "height": int(round(self._image_bounds.height())),
            "crop": crop,
            "crops": crops,
            "inverts": inverts,
        }

    def set_crop_pixel_edges(self, left: int, top: int, right: int, bottom: int, region_id: int | None = None) -> None:
        if self._image_bounds.isNull():
            return
        if region_id is None:
            region_id = next(iter(sorted(self._crop_norms)), self._next_crop_id)
        normalized = self._pixel_edges_to_normalized(left, top, right, bottom)
        self._crop_norms[region_id] = normalized
        self._crop_names.setdefault(region_id, self._default_crop_name(region_id))
        self._initialize_crop_region_settings(region_id)
        self._next_crop_id = max(self._next_crop_id, region_id + 1)
        self._refresh_region_annotations()
        self._refresh_pixmap()
        self._emit_regions()

    def set_crop_region_name(self, region_id: int, name: str) -> None:
        if region_id not in self._crop_norms:
            return
        self._crop_names[region_id] = name.strip() or self._default_crop_name(region_id)
        self._emit_regions()

    def set_crop_region_flip_horizontal(self, region_id: int, enabled: bool) -> None:
        if region_id not in self._crop_norms:
            return
        self._crop_flip_horizontal[region_id] = bool(enabled)
        self._crop_flip_horizontal_video_paths.setdefault(region_id, None)
        self._refresh_pixmap()
        self._emit_regions()

    def set_crop_region_flip_vertical(self, region_id: int, enabled: bool) -> None:
        if region_id not in self._crop_norms:
            return
        self._crop_flip_vertical[region_id] = bool(enabled)
        self._refresh_pixmap()
        self._emit_regions()

    def set_crop_region_horizontal_flip_video_paths(self, region_id: int, video_paths: frozenset[str] | None) -> None:
        if region_id not in self._crop_norms:
            return
        self._crop_flip_horizontal_video_paths[region_id] = (
            None if video_paths is None else frozenset(normalize_path(path) for path in video_paths)
        )
        self._refresh_pixmap()
        self._emit_regions()

    def set_crop_region_horizontal_flip_selection(self, region_id: int, video_paths: frozenset[str] | None) -> None:
        if region_id not in self._crop_norms:
            return
        self._apply_crop_horizontal_flip_selection((region_id,), video_paths, apply_to_new_regions=False)

    def apply_crop_horizontal_flip_selection_to_all_regions(
        self, video_paths: frozenset[str] | None, apply_to_new_regions: bool = False
    ) -> None:
        self._apply_crop_horizontal_flip_selection(
            tuple(self._crop_norms), video_paths, apply_to_new_regions=apply_to_new_regions
        )

    def crop_region_horizontal_flip_video_paths(self, region_id: int) -> frozenset[str] | None:
        return self._crop_flip_horizontal_video_paths.get(region_id)

    def set_available_video_paths(self, video_paths: list[str | Path]) -> None:
        valid_paths = frozenset(normalize_path(path) for path in video_paths)
        changed = False
        for region_id, selected_paths in list(self._crop_flip_horizontal_video_paths.items()):
            if selected_paths is None:
                continue
            pruned_paths = frozenset(path for path in selected_paths if path in valid_paths)
            if pruned_paths != selected_paths:
                self._crop_flip_horizontal_video_paths[region_id] = pruned_paths
                if self._crop_flip_horizontal.get(region_id, False) and (not pruned_paths):
                    self._crop_flip_horizontal[region_id] = False
                changed = True
        if self._default_crop_flip_horizontal_video_paths is not None:
            pruned_default = frozenset(
                path for path in self._default_crop_flip_horizontal_video_paths if path in valid_paths
            )
            if pruned_default != self._default_crop_flip_horizontal_video_paths:
                self._default_crop_flip_horizontal_video_paths = pruned_default
                if self._default_crop_flip_horizontal and (not pruned_default):
                    self._default_crop_flip_horizontal = False
        if changed:
            self._refresh_pixmap()
            self._emit_regions()

    def set_current_video_path(self, video_path: str | Path | None) -> None:
        normalized = normalize_path(video_path) if video_path is not None else None
        if normalized == self._current_video_path:
            return
        self._current_video_path = normalized
        self._refresh_pixmap()

    def set_invert_pixel_edges(self, region_id: int, left: int, top: int, right: int, bottom: int) -> None:
        return self.inversions.set_invert_pixel_edges(region_id, left, top, right, bottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._image_bounds.isNull() and (not (self._mode == "enhancements" and self._enhancement_zoom > 1.001)):
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
        pos = event_pos(event)
        scene_pos = self.mapToScene(pos)
        if self._mode != "enhancements" or self._image_bounds.isNull() or (not self._image_bounds.contains(scene_pos)):
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
        pos = event_pos(event)
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
            self._drag_start = clamp_point(scene_pos, self._image_bounds)
            if self._mode == "crop":
                region_id = self._next_crop_id
                self._next_crop_id += 1
                self._crop_names[region_id] = self._default_crop_name(region_id)
                self._initialize_crop_region_settings(region_id)
                self._drag_target = f"crop:{region_id}"
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
            factor = min(factor, MAX_ENHANCEMENT_ZOOM / self._enhancement_zoom)
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
            candidates.append((hit_priority(hit), item.scene_area(), order, item))
        if not candidates:
            return None
        candidates.sort(key=lambda candidate: (candidate[0], candidate[1], candidate[2]))
        (priority, area, _order, item) = candidates[0]
        return (priority, area, item)

    def _raise_region_item(self, selected_item: RegionRectItem) -> None:
        for item in self._region_items():
            item.setZValue(REGION_ACTIVE_Z if item is selected_item else REGION_BASE_Z)

    def _region_items(self) -> list[RegionRectItem]:
        return [*self._crop_items.values(), *self._invert_items.values()]

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            current = clamp_point(self.mapToScene(event_pos(event)), self._image_bounds)
            self._update_region_from_drag(self._drag_start, current)
            event.accept()
            return
        pos = event_pos(event)
        cursor = self._cursor_for_hover(pos, self.mapToScene(pos))
        super().mouseMoveEvent(event)
        self.viewport().setCursor(Qt.CrossCursor if self._mode == "enhancements" else cursor)

    def mouseReleaseEvent(self, event):
        if self._drag_start is not None:
            current = clamp_point(self.mapToScene(event_pos(event)), self._image_bounds)
            self._update_region_from_drag(self._drag_start, current)
            if isinstance(self._drag_target, str) and self._drag_target.startswith("crop:"):
                region_id = int(self._drag_target.split(":", 1)[1])
                if region_id not in self._crop_norms:
                    self._crop_names.pop(region_id, None)
                    self._crop_flip_horizontal.pop(region_id, None)
                    self._crop_flip_vertical.pop(region_id, None)
                    self._crop_flip_horizontal_video_paths.pop(region_id, None)
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
        if isinstance(self._drag_target, str) and self._drag_target.startswith("crop:"):
            region_id = int(self._drag_target.split(":", 1)[1])
            self._crop_norms[region_id] = normalized
            self._refresh_region_annotations()
            if self._crop_region_needs_pixmap_refresh(region_id):
                self._refresh_pixmap()
        elif isinstance(self._drag_target, int):
            self._invert_norms[self._drag_target] = normalized
            self._render()
        self._emit_regions()

    def _default_region_rect(self, mode: str) -> QRectF:
        bounds = self._image_bounds
        scale = 0.42 if mode == "crop" else 0.26
        width = min(bounds.width(), max(24.0, bounds.width() * scale))
        height = min(bounds.height(), max(24.0, bounds.height() * scale))
        offset_step = min(bounds.width(), bounds.height()) * 0.05
        existing_count = len(self._crop_norms) if mode == "crop" else len(self._invert_norms)
        for attempt in range(36):
            offset = offset_step * ((existing_count + attempt) % 6)
            column = (existing_count + attempt) % 3
            row = (existing_count + attempt) // 3 % 3
            left = bounds.left() + (bounds.width() - width) * (column / 2.0) + offset
            top = bounds.top() + (bounds.height() - height) * (row / 2.0) + offset
            left = clamp_float(left, bounds.left(), bounds.right() - width)
            top = clamp_float(top, bounds.top(), bounds.bottom() - height)
            rect = QRectF(left, top, width, height).intersected(bounds)
            return rect
        left = bounds.center().x() - width / 2
        top = bounds.center().y() - height / 2
        return QRectF(left, top, width, height).intersected(bounds)

    def _on_item_changed(self, name: str, scene_rect: QRectF) -> None:
        normalized = self._scene_rect_to_normalized(scene_rect)
        if name.startswith("crop:"):
            region_id = int(name.split(":", 1)[1])
            self._crop_norms[region_id] = normalized
            self._refresh_region_annotations()
            if self._crop_region_needs_pixmap_refresh(region_id):
                self._refresh_pixmap()
        elif name.startswith("invert:"):
            self._invert_norms[int(name.split(":", 1)[1])] = normalized
            self._refresh_pixmap()
        self._emit_regions()

    def _render(self) -> None:
        self._refresh_pixmap()
        self._refresh_region_annotations()

    def _refresh_region_annotations(self) -> None:
        self._sync_region_items()
        self._update_crop_shade()
        self._set_annotation_visibility(self._mode != "enhancements")

    def _refresh_pixmap(self) -> None:
        if self._source_image is None or self._source_image.isNull():
            self._image_item.setPixmap(QPixmap())
            return
        display = self._source_image.copy()
        for region_id, region_norm in self._crop_norms.items():
            if not region_norm.is_usable():
                continue
            mirror_horizontal = self._crop_horizontal_flip_applies(region_id)
            mirror_vertical = self._crop_flip_vertical.get(region_id, False)
            if not mirror_horizontal and (not mirror_vertical):
                continue
            rect = self._normalized_to_scene_rect(region_norm).toAlignedRect().intersected(display.rect())
            if rect.width() > 1 and rect.height() > 1:
                region = display.copy(rect).mirrored(mirror_horizontal, mirror_vertical)
                painter = QPainter(display)
                painter.drawImage(rect.topLeft(), region)
                painter.end()
        for region_norm in self._invert_norms.values():
            if not region_norm.is_usable():
                continue
            rect = self._normalized_to_scene_rect(region_norm).toAlignedRect().intersected(display.rect())
            if rect.width() > 1 and rect.height() > 1:
                region = display.copy(rect).mirrored(False, True)
                painter = QPainter(display)
                painter.drawImage(rect.topLeft(), region)
                painter.end()
        display = self.effects._apply_enhancements(display)
        self._image_item.setPixmap(QPixmap.fromImage(display))

    def _sync_region_items(self) -> None:
        for region_id in list(self._crop_items):
            if region_id not in self._crop_norms or not self._crop_norms[region_id].is_usable():
                self._scene.removeItem(self._crop_items.pop(region_id))
        for region_id, region in self._crop_norms.items():
            if not region.is_usable() or self._image_bounds.isNull():
                continue
            item = self._crop_items.get(region_id)
            if item is None:
                item = RegionRectItem(
                    f"crop:{region_id}",
                    _dependency_theme_color(theme.TEXT, 230),
                    self._image_bounds,
                    self._on_item_changed,
                    self.delete_region,
                    fill_alpha=0,
                )
                self._scene.addItem(item)
                self._crop_items[region_id] = item
            item.set_bounds(self._image_bounds)
            item.set_scene_rect(self._normalized_to_scene_rect(region))
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

    def _update_crop_shade(self) -> None:
        for item in self._shade_items:
            self._scene.removeItem(item)
        self._shade_items.clear()
        usable_crops = [region for region in self._crop_norms.values() if region.is_usable()]
        if not usable_crops or self._image_bounds.isNull():
            return
        bounds_path = QPainterPath()
        bounds_path.addRect(self._image_bounds)
        crop_path = QPainterPath()
        crop_path.setFillRule(Qt.WindingFill)
        for region in usable_crops:
            crop_path.addRect(self._normalized_to_scene_rect(region).intersected(self._image_bounds))
        shade_path = bounds_path.subtracted(crop_path)
        item = QGraphicsPathItem(shade_path)
        item.setPen(QPen(Qt.NoPen))
        item.setBrush(QColor(0, 0, 0, 112))
        item.setZValue(2)
        item.setAcceptedMouseButtons(Qt.NoButton)
        self._scene.addItem(item)
        self._shade_items.append(item)

    def _remove_region_items(self) -> None:
        for item in [*self._crop_items.values(), *self._invert_items.values(), *self._shade_items]:
            if item is not None:
                self._scene.removeItem(item)
        self._crop_items.clear()
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
        left = clamp_int(int(round(scene_rect.left())), 0, max(0, width - 2))
        top = clamp_int(int(round(scene_rect.top())), 0, max(0, height - 2))
        right = clamp_int(int(round(scene_rect.right())), left + 2, width)
        bottom = clamp_int(int(round(scene_rect.bottom())), top + 2, height)
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
        left = clamp_int(left, 0, max(0, width - 2))
        top = clamp_int(top, 0, max(0, height - 2))
        right = clamp_int(right, left + 2, width)
        bottom = clamp_int(bottom, top + 2, height)
        return NormalizedRect(
            x=left / width, y=top / height, width=(right - left) / width, height=(bottom - top) / height
        ).clamped()

    def _emit_regions(self) -> None:
        self.regions_changed.emit(self.crop_region(), self.invert_regions())

    def _crop_horizontal_flip_applies(self, region_id: int) -> bool:
        if not self._crop_flip_horizontal.get(region_id, False):
            return False
        selected_paths = self._crop_flip_horizontal_video_paths.get(region_id)
        return selected_paths is None or self._current_video_path in selected_paths

    def _crop_region_needs_pixmap_refresh(self, region_id: int) -> bool:
        return self._crop_horizontal_flip_applies(region_id) or self._crop_flip_vertical.get(region_id, False)

    def _initialize_crop_region_settings(self, region_id: int) -> None:
        self._crop_flip_horizontal.setdefault(region_id, self._default_crop_flip_horizontal)
        self._crop_flip_vertical.setdefault(region_id, False)
        self._crop_flip_horizontal_video_paths.setdefault(region_id, self._default_crop_flip_horizontal_video_paths)

    def _apply_crop_horizontal_flip_selection(
        self, region_ids, video_paths: frozenset[str] | None, apply_to_new_regions: bool
    ) -> None:
        normalized_paths = None if video_paths is None else frozenset(normalize_path(path) for path in video_paths)
        enabled = normalized_paths is None or bool(normalized_paths)
        changed = False
        for region_id in region_ids:
            if region_id not in self._crop_norms:
                continue
            if self._crop_flip_horizontal.get(region_id, False) != enabled:
                self._crop_flip_horizontal[region_id] = enabled
                changed = True
            if self._crop_flip_horizontal_video_paths.get(region_id) != normalized_paths:
                self._crop_flip_horizontal_video_paths[region_id] = normalized_paths
                changed = True
        if apply_to_new_regions:
            if self._default_crop_flip_horizontal != enabled:
                self._default_crop_flip_horizontal = enabled
                changed = True
            if self._default_crop_flip_horizontal_video_paths != normalized_paths:
                self._default_crop_flip_horizontal_video_paths = normalized_paths
                changed = True
        if changed:
            self._refresh_pixmap()
            self._emit_regions()

    def _crop_overlaps_existing(self, candidate: NormalizedRect, exclude_id: int | None = None) -> bool:
        if self._image_bounds.isNull() or not candidate.is_usable():
            return False
        candidate_rect = self._normalized_to_scene_rect(candidate)
        for region_id, region in self._crop_norms.items():
            if region_id == exclude_id or not region.is_usable():
                continue
            intersection = candidate_rect.intersected(self._normalized_to_scene_rect(region))
            if intersection.width() > 0.5 and intersection.height() > 0.5:
                return True
        return False

    def _default_crop_name(self, region_id: int) -> str:
        return f"Region {region_id}"


def normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())
