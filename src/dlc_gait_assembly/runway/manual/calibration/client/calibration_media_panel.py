"""Present selected images and videos with frame-seeking controls."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from dlc_gait_assembly.shared.business.media_access_contracts import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from dlc_gait_assembly.shared.client.display_time_formatting import format_milliseconds
from dlc_gait_assembly.shared.client.qt_frame_conversion import rgb_array_to_qimage
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class CalibrationMediaPanel:
    """CalibrationMediaPanel operates on its explicitly supplied ManualCalibrationWidget view."""

    def __init__(self, view):
        self.view = view

    def _open_media(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))
        (filenames, _) = QFileDialog.getOpenFileNames(
            self.view,
            "Add calibration images or videos",
            str(self.view._project_root),
            f"Image and video files ({extensions});;All files (*)",
        )
        if not filenames:
            return
        self._add_media_paths(Path(filename) for filename in filenames)

    def _add_media_paths(self, paths: Iterable[str | Path]) -> None:
        unsupported: list[str] = []
        first_added_row: int | None = None
        for candidate in paths:
            path = Path(candidate).expanduser().resolve()
            if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                unsupported.append(path.name)
                continue
            if self._media_item_for_path(path) is not None:
                continue
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.UserRole, str(path))
            self.view.media_list.addItem(item)
            if first_added_row is None:
                first_added_row = self.view.media_list.count() - 1
        if unsupported:
            QMessageBox.warning(self.view, "Unsupported files", "Skipped unsupported files:\n" + "\n".join(unsupported))
        if first_added_row is not None and self.view.media_list.currentItem() is None:
            self.view.media_list.setCurrentRow(first_added_row)
        self._update_media_summary()

    def _media_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        self.view.controller._save_media_state(previous)
        if current is None:
            self._release_capture()
            self.view.state.current_media = None
            self.view.state.duration_ms = 0
            self.view.timeline.setRange(0, 0)
            self.view.timeline.setEnabled(False)
            self.view.time_label.setText("00:00.000 / 00:00.000")
            self.view.preview_title.setText("Open a calibration image or video.")
            self.view.preview.set_frame(None)
            self._update_media_summary()
            return
        self._load_media(Path(current.data(Qt.UserRole)))

    def _load_media(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            self._load_image(path)
        elif suffix in VIDEO_EXTENSIONS:
            self._load_video(path)
        else:
            QMessageBox.warning(self.view, "Unsupported file", "Choose a supported image or video file.")

    def _remove_selected_media(self) -> None:
        selected_items = self.view.media_list.selectedItems()
        if not selected_items:
            return
        current = self.view.media_list.currentItem()
        current_path_key = current.data(Qt.UserRole) if current is not None else None
        self.view.controller._save_media_state(current)
        selected_path_keys = {item.data(Qt.UserRole) for item in selected_items}
        first_removed_row = min(self.view.media_list.row(item) for item in selected_items)
        blocker = QSignalBlocker(self.view.media_list)
        for item in sorted(selected_items, key=self.view.media_list.row, reverse=True):
            path_key = item.data(Qt.UserRole)
            self.view.state.calibration_sticks_by_media.pop(path_key, None)
            self.view.state.timeline_ms_by_media.pop(path_key, None)
            self.view.media_list.takeItem(self.view.media_list.row(item))
        if self.view.media_list.count() == 0:
            del blocker
            self._release_capture()
            self.view.state.current_media = None
            self.view.state.duration_ms = 0
            self.view.timeline.setRange(0, 0)
            self.view.timeline.setEnabled(False)
            self.view.time_label.setText("00:00.000 / 00:00.000")
            self.view.preview_title.setText("Open a calibration image or video.")
            self.view.preview.set_frame(None)
        else:
            target_item = None
            if current_path_key is not None and current_path_key not in selected_path_keys:
                target_item = self._media_item_for_path(Path(current_path_key))
            if target_item is not None:
                self.view.media_list.setCurrentItem(target_item)
            else:
                self.view.media_list.setCurrentRow(min(first_removed_row, self.view.media_list.count() - 1))
            new_current = self.view.media_list.currentItem()
            del blocker
            if new_current is not None and new_current.data(Qt.UserRole) != current_path_key:
                self._load_media(Path(new_current.data(Qt.UserRole)))
        self.view.controller._update_calibration_results()
        self._update_media_summary()

    def _load_image(self, path: Path) -> None:
        self._release_capture()
        try:
            image = rgb_array_to_qimage(self.view.media_access.read_image(path))
        except OSError as exc:
            QMessageBox.warning(self.view, "Could not open image", str(exc))
            return
        self.view.state.loading_media = True
        try:
            self.view.state.current_media = path
            self.view.state.duration_ms = 0
            self.view.timeline.setRange(0, 0)
            self.view.timeline.setEnabled(False)
            self.view.time_label.setText("Image")
            self.view.preview_title.setText(path.name)
            self.view.preview.set_frame(image)
            self.view.preview.set_calibration_sticks(self.view.state.calibration_sticks_by_media.get(str(path), ()))
        finally:
            self.view.state.loading_media = False
        self.view.controller._save_media_state()
        self.view.controller._update_calibration_results()
        self._update_media_summary()

    def _load_video(self, path: Path) -> None:
        self._release_capture()
        try:
            capture = self.view.media_access.open_video(path)
        except OSError as exc:
            QMessageBox.warning(self.view, "Could not open video", str(exc))
            return
        self.view.state.loading_media = True
        try:
            self.view._capture = capture
            self.view.state.current_media = path
            self.view.state.fps = capture.info.fps
            self.view.state.frame_count = capture.info.frame_count
            self.view.state.duration_ms = (
                int(self.view.state.frame_count / self.view.state.fps * 1000)
                if self.view.state.fps > 0 and self.view.state.frame_count > 0
                else 0
            )
            self.view.timeline.setRange(0, max(0, self.view.state.duration_ms))
            self.view.timeline.setSingleStep(100)
            self.view.timeline.setPageStep(1000)
            self.view.timeline.setEnabled(self.view.state.duration_ms > 0)
            self.view.preview_title.setText(path.name)
            saved_ms = min(self.view.state.timeline_ms_by_media.get(str(path), 0), max(0, self.view.state.duration_ms))
            self._set_timeline_value(saved_ms)
            self._load_frame_at(saved_ms)
            self.view.preview.set_calibration_sticks(self.view.state.calibration_sticks_by_media.get(str(path), ()))
        finally:
            self.view.state.loading_media = False
        self.view.controller._save_media_state()
        self.view.controller._update_calibration_results()
        self._update_media_summary()

    def _timeline_changed(self, value: int) -> None:
        if self.view.state.loading_slider:
            return
        if self.view.state.current_media is not None:
            self.view.state.timeline_ms_by_media[str(self.view.state.current_media)] = value
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
            QMessageBox.warning(self.view, "Could not read frame", "Try a different timestamp or file.")
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
        self.view.state.pending_frame_ms = None
        if self.view._capture is not None:
            self.view._capture.close()
            self.view._capture = None
        self.view.state.fps = 0.0
        self.view.state.frame_count = 0

    def _media_item_for_path(self, path: Path) -> QListWidgetItem | None:
        path_key = str(path)
        for index in range(self.view.media_list.count()):
            item = self.view.media_list.item(index)
            if item.data(Qt.UserRole) == path_key:
                return item
        return None

    def _update_media_summary(self) -> None:
        count = self.view.media_list.count()
        if count == 0:
            self.view.media_label.setText("No calibration images or videos loaded.")
            return
        selected = self.view.media_list.currentItem()
        current = f"\nCurrent: {selected.toolTip()}" if selected is not None else ""
        stick_count = len(self.view.controller._all_calibration_sticks())
        self.view.media_label.setText(
            f"{count} calibration file(s) loaded. {stick_count} calibration stick(s) saved.{current}"
        )


def build_calibration_media(self, left_layout):
    media_box = QGroupBox("Calibration frame")
    media_box.setMaximumHeight(245)
    media_layout = QVBoxLayout(media_box)
    media_layout.setSpacing(8)
    media_buttons = QHBoxLayout()
    media_buttons.setSpacing(8)
    self.open_media_button = QPushButton("Add")
    self.open_media_button.setObjectName("OpenMediaButton")
    set_tooltip(self.open_media_button, "Add calibration images or videos.", "Ctrl+O")
    self.remove_media_button = QPushButton("Remove")
    self.remove_media_button.setObjectName("RemoveButton")
    set_tooltip(self.remove_media_button, "Remove selected calibration files.", "Ctrl+Backspace")
    self.clear_calibration_button = QPushButton("Clear")
    self.clear_calibration_button.setObjectName("ClearButton")
    set_tooltip(self.clear_calibration_button, "Clear calibration markers for the current file.", "Ctrl+L")
    media_buttons.addWidget(self.open_media_button, 1)
    media_buttons.addWidget(self.remove_media_button, 1)
    media_buttons.addWidget(self.clear_calibration_button, 1)
    media_layout.addLayout(media_buttons)
    self.media_list = QListWidget()
    self.media_list.setSelectionMode(QListWidget.ExtendedSelection)
    self.media_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    self.media_list.setTextElideMode(Qt.ElideNone)
    self.media_list.setUniformItemSizes(True)
    self.media_list.setAlternatingRowColors(False)
    list_font = self.media_list.font()
    list_font.setPointSize(9)
    self.media_list.setFont(list_font)
    media_layout.addWidget(self.media_list, 1)
    self.media_label = QLabel("No calibration images or videos loaded.")
    self.media_label.setWordWrap(True)
    self.media_label.setObjectName("MutedLabel")
    media_layout.addWidget(self.media_label)
    left_layout.addWidget(media_box)
