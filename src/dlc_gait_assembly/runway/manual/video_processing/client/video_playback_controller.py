"""Coordinate video selection, frame seeking, debounced requests, and preview updates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox

from dlc_gait_assembly.shared.client.display_time_formatting import format_milliseconds
from dlc_gait_assembly.shared.client.qt_frame_conversion import rgb_array_to_qimage


class VideoPlaybackController:
    """VideoPlaybackController operates on its explicitly supplied VideoEditorWidget view."""

    def __init__(self, view):
        self.view = view

    def _load_selected_video(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        path = Path(current.data(Qt.UserRole))
        self._release_capture()
        try:
            capture = self.view.media_access.open_video(path)
        except OSError as exc:
            QMessageBox.warning(self.view, "Could not open video", str(exc))
            return
        requested_ms = self.view.timeline.value()
        self.view._capture = capture
        self.view.state.current_video = path
        self.view.preview.set_current_video_path(path)
        self.view.state.fps = capture.info.fps
        self.view.state.frame_count = capture.info.frame_count
        self.view.state.duration_ms = (
            int(self.view.state.frame_count / self.view.state.fps * 1000)
            if self.view.state.fps > 0 and self.view.state.frame_count > 0
            else 0
        )
        self.view.preview_title.setText(path.name)
        self.view.timeline.setRange(0, max(0, self.view.state.duration_ms))
        self.view.timeline.setSingleStep(100)
        self.view.timeline.setPageStep(1000)
        target_ms = min(requested_ms, self.view.state.duration_ms)
        self._set_timeline_value(target_ms)
        self._load_frame_at(target_ms)
        self.view.trims._refresh_trim_context()

    def _timeline_changed(self, value: int) -> None:
        if self.view.state.loading_slider:
            return
        self._queue_frame_at(value)

    def _queue_frame_at(self, ms: int) -> None:
        self.view.state.pending_frame_ms = int(ms)
        if self.view.timeline.isSliderDown():
            if not self.view._frame_load_timer.isActive():
                self.view._frame_load_timer.start()
            return
        self._flush_pending_frame()

    def _flush_pending_frame(self) -> None:
        self.view._frame_load_timer.stop()
        self._load_pending_frame()

    def _load_pending_frame(self) -> None:
        if self.view.state.pending_frame_ms is None:
            return
        ms = self.view.state.pending_frame_ms
        self.view.state.pending_frame_ms = None
        self._load_frame_at(ms)

    def _load_frame_at(self, ms: int) -> None:
        if self.view._capture is None:
            return
        frame = self.view._capture.read_timestamp(ms)
        if frame is None:
            self.view.progress.setFormat("Could not read frame")
            return
        self.view.preview.set_frame(rgb_array_to_qimage(frame))
        self.view.time_label.setText(f"{format_milliseconds(ms)} / {format_milliseconds(self.view.state.duration_ms)}")

    def _set_timeline_value(self, value: int) -> None:
        self.view.state.loading_slider = True
        self.view.timeline.setValue(value)
        self.view.state.loading_slider = False

    def _release_capture(self) -> None:
        if hasattr(self.view, "_frame_load_timer"):
            self.view._frame_load_timer.stop()
        if hasattr(self.view, "_trim_context_refresh_timer"):
            self.view._trim_context_refresh_timer.stop()
        self.view.state.pending_frame_ms = None
        if self.view._capture is not None:
            self.view._capture.close()
            self.view._capture = None
        self.view.state.current_video = None
        if hasattr(self.view, "preview"):
            self.view.preview.set_current_video_path(None)
        self.view.state.fps = 0.0
        self.view.state.frame_count = 0
