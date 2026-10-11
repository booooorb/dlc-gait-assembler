"""Add, select, remove, and numerically edit trim ranges for each video."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QSpinBox

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange
from dlc_gait_assembly.shared.client.display_time_formatting import format_milliseconds
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class VideoTrimSettings:
    """VideoTrimSettings operates on its explicitly supplied VideoOperationSettingsPanel view."""

    def __init__(self, view):
        self.view = view

    def _rebuild_trim_settings(self) -> None:
        self.view._building = True
        self.view._keys = [("trim", None)]
        self.view._controls = {}
        self.view._enhancement_controls = {}
        self.view._clear_layout()
        if self.view._trim_video_name is None or self.view._trim_duration_ms <= 0:
            self.view._add_placeholder("No video selected.")
            self.view._content_layout.addStretch(1)
            self.view._building = False
            return
        header = QLabel(self.view._trim_video_name)
        header.setObjectName("RegionTitle")
        self.view._content_layout.addWidget(header)
        ranges = self.view._trim_ranges or [TrimRange(0, self.view._trim_duration_ms)]
        for index, trim_range in enumerate(ranges):
            self._add_trim_range_settings(index, trim_range, index == self.view._active_trim_index)
        add_button = QPushButton("Add trim range")
        add_button.setObjectName("CreateTrimRangeButton")
        set_tooltip(add_button, "Add another trim range for the selected video.")
        add_button.clicked.connect(lambda _checked=False: self.view.trim_range_added.emit())
        self.view._content_layout.addWidget(add_button)
        reset_button = QPushButton("Reset video trim")
        reset_button.setObjectName("ResetButton")
        set_tooltip(reset_button, "Reset the selected video to one full-length trim range.")
        reset_button.clicked.connect(lambda _checked=False: self.view.trim_ranges_reset.emit())
        self.view._content_layout.addWidget(reset_button)
        self.view._content_layout.addStretch(1)
        self.view._building = False

    def _add_trim_range_settings(self, index: int, trim_range: TrimRange, active: bool) -> None:
        frame = QFrame()
        frame.setObjectName("RegionSettings")
        layout = QGridLayout(frame)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)
        layout.setColumnStretch(1, 1)
        title = QLabel(f"Range {index + 1}")
        title.setObjectName("RegionTitle")
        title.setStyleSheet(f"color: {theme.NUMBER_ICON};" if active else "")
        duration = QLabel(f"{format_milliseconds(trim_range.start_ms)} - {format_milliseconds(trim_range.end_ms)}")
        duration.setObjectName("DimensionLabel")
        duration.setWordWrap(True)
        layout.addWidget(title, 0, 0)
        layout.addWidget(duration, 0, 1, Qt.AlignRight)
        start_spin = self._make_trim_spinbox(trim_range.start_ms)
        end_spin = self._make_trim_spinbox(trim_range.end_ms)
        set_tooltip(start_spin, "Start time for this trim range, in milliseconds.")
        set_tooltip(end_spin, "End time for this trim range, in milliseconds.")
        start_spin.valueChanged.connect(lambda _value, idx=index: self._apply_trim_spins(idx, start_spin, end_spin))
        end_spin.valueChanged.connect(lambda _value, idx=index: self._apply_trim_spins(idx, start_spin, end_spin))
        start_spin.editingFinished.connect(lambda idx=index: self.view.trim_active_range_changed.emit(idx))
        end_spin.editingFinished.connect(lambda idx=index: self.view.trim_active_range_changed.emit(idx))
        layout.addWidget(QLabel("Start"), 1, 0)
        layout.addWidget(start_spin, 1, 1)
        layout.addWidget(QLabel("End"), 2, 0)
        layout.addWidget(end_spin, 2, 1)
        delete_button = QPushButton("Delete")
        delete_button.setObjectName("DeleteButton")
        set_tooltip(delete_button, f"Delete trim range {index + 1}.")
        delete_button.clicked.connect(lambda _checked=False, idx=index: self.view.trim_range_deleted.emit(idx))
        layout.addWidget(delete_button, 3, 0, 1, 2)
        self.view._content_layout.addWidget(frame)

    def _make_trim_spinbox(self, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, self.view._trim_duration_ms)
        spin.setKeyboardTracking(False)
        spin.setValue(value)
        spin.setMaximumWidth(78)
        return spin

    def _apply_trim_spins(self, index: int, start_spin: QSpinBox, end_spin: QSpinBox) -> None:
        if self.view._building:
            return
        start = min(start_spin.value(), max(0, end_spin.value() - 1))
        end = max(end_spin.value(), start + 1)
        end = min(end, self.view._trim_duration_ms)
        self.view.trim_range_changed.emit(index, start, end)


class VideoTrimControls:
    """VideoTrimControls operates on its explicitly supplied VideoEditorWidget view."""

    def __init__(self, view):
        self.view = view

    def _refresh_trim_context(self) -> None:
        if self.view.state.current_video is None or self.view.state.duration_ms <= 0:
            self.view.timeline.set_trim_ranges(0, [])
            self.view.settings_panel.set_trim_context(None, 0, [], 0)
            return
        key = str(self.view.state.current_video)
        ranges = self._display_trim_ranges(key)
        active_index = self.view.state.active_trim_range_by_video.get(key, 0)
        active_index = min(active_index, max(0, len(ranges) - 1))
        self.view.timeline.set_trim_ranges(self.view.state.duration_ms, ranges, active_index)
        self.view.settings_panel.set_trim_context(
            self.view.state.current_video.name, self.view.state.duration_ms, ranges, active_index
        )

    def _display_trim_ranges(self, key: str) -> list[TrimRange]:
        ranges = self.view.state.trim_ranges_by_video.get(key)
        if ranges:
            return list(ranges)
        if self.view.state.duration_ms > 0:
            return [TrimRange(0, self.view.state.duration_ms)]
        return []

    def _on_trim_active_changed(self, index: int) -> None:
        if self.view.state.current_video is None:
            return
        key = str(self.view.state.current_video)
        self.view.state.active_trim_range_by_video[key] = index
        self._refresh_trim_context()

    def _on_trim_range_changed(self, index: int, start_ms: int, end_ms: int) -> None:
        if self.view.state.current_video is None or self.view.state.duration_ms <= 0:
            return
        key = str(self.view.state.current_video)
        ranges = self._display_trim_ranges(key)
        if not ranges:
            return
        index = min(max(0, index), len(ranges) - 1)
        ranges[index] = TrimRange(start_ms, end_ms).clamped(self.view.state.duration_ms)
        immediate_refresh = self.view.sender() is not self.view.timeline
        self._set_current_trim_ranges(ranges, index, refresh=immediate_refresh)
        if not immediate_refresh:
            self._schedule_trim_context_refresh()

    def _add_trim_range(self) -> None:
        if self.view.state.current_video is None or self.view.state.duration_ms <= 0:
            return
        key = str(self.view.state.current_video)
        ranges = list(self.view.state.trim_ranges_by_video.get(key, []))
        span = max(250, min(5000, self.view.state.duration_ms // 4 or self.view.state.duration_ms))
        start = min(self.view.timeline.value(), max(0, self.view.state.duration_ms - span))
        end = min(self.view.state.duration_ms, start + span)
        ranges.append(TrimRange(start, end))
        self._set_current_trim_ranges(ranges, len(ranges) - 1)

    def _delete_trim_range(self, index: int) -> None:
        if self.view.state.current_video is None:
            return
        key = str(self.view.state.current_video)
        ranges = list(self.view.state.trim_ranges_by_video.get(key, []))
        if not ranges:
            self._reset_current_video_trim()
            return
        if 0 <= index < len(ranges):
            ranges.pop(index)
        self._set_current_trim_ranges(ranges, max(0, min(index, len(ranges) - 1)))

    def _reset_current_video_trim(self) -> None:
        if self.view.state.current_video is None:
            return
        key = str(self.view.state.current_video)
        self.view.state.trim_ranges_by_video.pop(key, None)
        self.view.state.active_trim_range_by_video.pop(key, None)
        self._refresh_trim_context()

    def _set_current_trim_ranges(self, ranges: list[TrimRange], active_index: int, refresh: bool = True) -> None:
        if self.view.state.current_video is None:
            return
        key = str(self.view.state.current_video)
        normalized = [trim.clamped(self.view.state.duration_ms) for trim in ranges]
        normalized = [trim for trim in normalized if trim.is_usable()]
        active_trim = normalized[active_index] if 0 <= active_index < len(normalized) else None
        normalized = sorted(normalized, key=lambda trim: (trim.start_ms, trim.end_ms))
        if not normalized or self._is_default_trim(normalized):
            self.view.state.trim_ranges_by_video.pop(key, None)
            self.view.state.active_trim_range_by_video.pop(key, None)
        else:
            self.view.state.trim_ranges_by_video[key] = normalized
            if active_trim in normalized:
                self.view.state.active_trim_range_by_video[key] = normalized.index(active_trim)
            else:
                self.view.state.active_trim_range_by_video[key] = max(0, min(active_index, len(normalized) - 1))
        if refresh:
            self._refresh_trim_context()

    def _schedule_trim_context_refresh(self) -> None:
        if not self.view._trim_context_refresh_timer.isActive():
            self.view._trim_context_refresh_timer.start()

    def _is_default_trim(self, ranges: list[TrimRange]) -> bool:
        return len(ranges) == 1 and ranges[0].start_ms == 0 and (ranges[0].end_ms == self.view.state.duration_ms)

    def _trim_ranges_for_processing(self, videos: list[Path]) -> dict[str, tuple[TrimRange, ...]]:
        ranges_by_path = {}
        for path in videos:
            ranges = self.view.state.trim_ranges_by_video.get(str(path))
            if ranges:
                ranges_by_path[str(path)] = tuple(sorted(ranges, key=lambda trim: (trim.start_ms, trim.end_ms)))
        return ranges_by_path

    def _trim_ranges_for_manifest(self) -> dict[str, tuple[TrimRange, ...]]:
        ranges_by_video: dict[str, tuple[TrimRange, ...]] = {}
        for path_key, ranges in self.view.state.trim_ranges_by_video.items():
            trims = tuple(sorted(ranges, key=lambda trim: (trim.start_ms, trim.end_ms)))
            if not trims:
                continue
            path = Path(path_key)
            ranges_by_video[str(path)] = trims
            ranges_by_video.setdefault(path.name, trims)
        return ranges_by_video

    def _apply_imported_trim_ranges(self, trim_ranges_by_video: dict[str, tuple[TrimRange, ...]]) -> None:
        self.view.state.trim_ranges_by_video.clear()
        self.view.state.active_trim_range_by_video.clear()
        videos = self.view.sources._video_paths()
        for video in videos:
            keys = (str(video.expanduser().resolve()), str(video), video.name)
            for key in keys:
                ranges = trim_ranges_by_video.get(key)
                if ranges:
                    self.view.state.trim_ranges_by_video[str(video)] = list(ranges)
                    break
        if len(videos) == 1 and (not self.view.state.trim_ranges_by_video) and (len(trim_ranges_by_video) == 1):
            ranges = next(iter(trim_ranges_by_video.values()))
            if ranges:
                self.view.state.trim_ranges_by_video[str(videos[0])] = list(ranges)
