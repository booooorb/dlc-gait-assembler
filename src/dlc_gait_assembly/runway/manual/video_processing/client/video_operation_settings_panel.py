"""Compose crop, enhancement, flip, and trim panels for the selected video operation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange
from dlc_gait_assembly.runway.manual.video_processing.client.video_crop_controls import VideoCropControls
from dlc_gait_assembly.runway.manual.video_processing.client.video_enhancement_controls import VideoEnhancementControls
from dlc_gait_assembly.runway.manual.video_processing.client.video_flip_assignment import VideoFlipAssignment
from dlc_gait_assembly.runway.manual.video_processing.client.video_region_canvas import RegionPreviewView
from dlc_gait_assembly.runway.manual.video_processing.client.video_trim_controls import VideoTrimSettings


class VideoOperationSettingsPanel(QGroupBox):
    video_preview_requested = Signal(str)
    trim_active_range_changed = Signal(int)
    trim_range_changed = Signal(int, int, int)
    trim_range_added = Signal()
    trim_range_deleted = Signal(int)
    trim_ranges_reset = Signal()

    def __init__(self, preview: RegionPreviewView, parent=None):
        super().__init__("Operation settings", parent)
        self.enhancements = VideoEnhancementControls(self)
        self.trims = VideoTrimSettings(self)
        self.flips = VideoFlipAssignment(self)
        self.crops = VideoCropControls(self)
        self._preview = preview
        self._building = False
        self._controls: dict[tuple[str, int | None], dict] = {}
        self._enhancement_controls: dict[str, dict] = {}
        self._keys: list[tuple[str, int | None]] = []
        self._image_size = (0, 0)
        self._active_tool = "crop"
        self._trim_video_name: str | None = None
        self._trim_duration_ms = 0
        self._trim_ranges: list[TrimRange] = []
        self._active_trim_index = 0
        self._video_paths: list[str] = []
        self._choosing_horizontal_region_id: int | None = None
        self._choice_selected_paths: set[str] = set()
        self._choice_apply_to_all_regions = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("OperationSettingsScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._content.setObjectName("OperationSettingsContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)
        self._preview.regions_changed.connect(lambda *_: self.refresh())
        self.refresh()

    def set_active_tool(self, tool: str) -> None:
        if tool not in {"crop", "enhancements", "trim"} or tool == self._active_tool:
            return
        self._active_tool = tool
        self._choosing_horizontal_region_id = None
        self._keys = []
        self.refresh()

    def set_video_paths(self, video_paths) -> None:
        self._video_paths = [normalize_path(path) for path in video_paths]
        if self._choosing_horizontal_region_id is not None:
            self._choice_selected_paths.intersection_update(self._video_paths)
            self.flips._rebuild_horizontal_video_selector()
            return
        if self._active_tool == "crop":
            self.refresh()

    def set_trim_context(
        self, video_name: str | None, duration_ms: int, ranges: list[TrimRange], active_index: int = 0
    ) -> None:
        normalized_duration = max(0, int(duration_ms))
        normalized_ranges = list(ranges)
        if (
            self._active_tool == "trim"
            and self._trim_video_name == video_name
            and (self._trim_duration_ms == normalized_duration)
            and (self._trim_ranges == normalized_ranges)
            and (self._active_trim_index == active_index)
        ):
            return
        self._trim_video_name = video_name
        self._trim_duration_ms = normalized_duration
        self._trim_ranges = normalized_ranges
        self._active_trim_index = active_index
        if self._active_tool == "trim":
            self.trims._rebuild_trim_settings()

    def refresh(self) -> None:
        if self._choosing_horizontal_region_id is not None:
            return
        if self._active_tool == "enhancements":
            self.enhancements._rebuild_enhancement_settings()
            return
        if self._active_tool == "trim":
            self.trims._rebuild_trim_settings()
            return
        snapshot = self._preview.region_snapshots()
        image_size = (snapshot["width"], snapshot["height"])
        regions = self.crops._settings_regions(snapshot)
        keys = [(region["kind"], region["id"]) for region in regions]
        if keys == self._keys and image_size == self._image_size and keys:
            self.crops._update_controls(regions)
            return
        self._building = True
        self._keys = keys
        self._image_size = image_size
        self._controls = {}
        self._enhancement_controls = {}
        self._clear_layout()
        if snapshot["width"] <= 0 or snapshot["height"] <= 0:
            self._add_placeholder("No preview loaded.")
        elif not regions:
            self._add_placeholder(self.crops._empty_state_text())
        else:
            for region in regions:
                self.crops._add_region_settings(
                    region["kind"],
                    region["id"],
                    region["title"],
                    region["edges"],
                    snapshot["width"],
                    snapshot["height"],
                )
        if self.crops._can_create_region(snapshot):
            self.crops._add_create_region_button()
        self._content_layout.addStretch(1)
        self._building = False

    def _clear_layout(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_child_layout(child_layout)

    def _clear_child_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_child_layout(child_layout)

    def _add_placeholder(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("SettingsPlaceholder")
        label.setWordWrap(True)
        self._content_layout.addWidget(label)


def normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())
