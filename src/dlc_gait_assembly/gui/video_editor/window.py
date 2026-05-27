from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.domain.trimming import TrimRange
from dlc_gait_assembly.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.gui.video_editor.preview import RegionPreviewView
from dlc_gait_assembly.gui.video_editor.settings_panel import OperationSettingsPanel
from dlc_gait_assembly.gui.video_editor.timeline import TrimTimelineSlider
from dlc_gait_assembly.gui.video_editor.workers import VideoProcessingThread
from dlc_gait_assembly.services.ffmpeg import ProcessingOptions, ffmpeg_available
from dlc_gait_assembly.services.project_paths import find_project_root, make_session_output_dir
from dlc_gait_assembly.services.video_io import is_supported_video

try:
    import cv2
except ImportError:
    cv2 = None


class VideoEditorWidget(QWidget):
    def __init__(self):
        super().__init__()

        self._capture = None
        self._current_video: Path | None = None
        self._duration_ms = 0
        self._loading_slider = False
        self._processing_thread: VideoProcessingThread | None = None
        self._processing_errors: list[str] = []
        self._project_root = find_project_root(__file__)
        self._trim_ranges_by_video: dict[str, list[TrimRange]] = {}
        self._active_trim_range_by_video: dict[str, int] = {}

        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._update_process_state()

    def can_close(self, parent=None) -> bool:
        if self._processing_thread is not None and self._processing_thread.isRunning():
            QMessageBox.information(
                parent or self,
                "Processing is still running",
                "Wait for the current video processing batch to finish before closing the window.",
            )
            return False

        return True

    def release_resources(self) -> None:
        self._release_capture()

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)
        self.preview = RegionPreviewView()

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(12)

        title = QLabel("Video Processing Window")
        title.setObjectName("TitleLabel")
        left_layout.addWidget(title)

        videos_box = QGroupBox("Uploaded videos")
        videos_layout = QVBoxLayout(videos_box)
        videos_layout.setSpacing(8)
        button_row = QHBoxLayout()
        self.add_videos_button = QPushButton("Add Files")
        self.add_folder_button = QPushButton("Add Folder")
        self.remove_videos_button = QPushButton("Remove")
        self.clear_videos_button = QPushButton("Clear")
        button_row.addWidget(self.add_videos_button)
        button_row.addWidget(self.add_folder_button)
        button_row.addWidget(self.remove_videos_button)
        button_row.addWidget(self.clear_videos_button)
        videos_layout.addLayout(button_row)
        self.video_list = QListWidget()
        self.video_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.video_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.video_list.setTextElideMode(Qt.ElideNone)
        self.video_list.setUniformItemSizes(True)
        self.video_list.setAlternatingRowColors(True)
        self.video_list.setSpacing(0)
        list_font = self.video_list.font()
        list_font.setPointSize(9)
        self.video_list.setFont(list_font)
        videos_layout.addWidget(self.video_list, 1)
        left_layout.addWidget(videos_box, 4)

        self.settings_panel = OperationSettingsPanel(self.preview)
        left_layout.addWidget(self.settings_panel, 3)

        self.process_button = QPushButton("Process All Uploaded Videos")
        self.process_button.setObjectName("PrimaryButton")
        left_layout.addWidget(self.process_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("")
        left_layout.addWidget(self.progress)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        self.preview_title = QLabel("Select a video from the uploaded list.")
        self.preview_title.setObjectName("PreviewTitle")
        right_layout.addWidget(self.preview_title)

        operations_bar = QFrame()
        operations_bar.setObjectName("OperationsBar")
        operations_layout = QVBoxLayout(operations_bar)
        operations_layout.setContentsMargins(10, 8, 10, 8)
        operations_layout.setSpacing(8)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(8)
        tool_row.addWidget(QLabel("Operations"))
        self.crop_tool_button = _make_tool_button("Crop", "#475569")
        self.invert_tool_button = _make_tool_button("Upside-Down", "#c026d3")
        self.enhancements_tool_button = _make_tool_button("Enhancements", "#0891b2")
        self.trim_tool_button = _make_tool_button("Trim", "#f97316")
        self.crop_tool_button.setChecked(True)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.crop_tool_button)
        self.tool_group.addButton(self.invert_tool_button)
        self.tool_group.addButton(self.enhancements_tool_button)
        self.tool_group.addButton(self.trim_tool_button)
        tool_row.addWidget(self.crop_tool_button)
        tool_row.addWidget(self.invert_tool_button)
        tool_row.addWidget(self.enhancements_tool_button)
        tool_row.addWidget(self.trim_tool_button)
        tool_row.addStretch(1)
        operations_layout.addLayout(tool_row)
        right_layout.addWidget(operations_bar)

        right_layout.addWidget(self.preview, 1)

        timeline_row = QHBoxLayout()
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(180)
        self.timeline = TrimTimelineSlider()
        self.timeline.setRange(0, 0)
        timeline_row.addWidget(self.time_label)
        timeline_row.addWidget(self.timeline, 1)
        right_layout.addLayout(timeline_row)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([390, 890])

    def _connect_signals(self) -> None:
        self.add_videos_button.clicked.connect(self._add_videos)
        self.add_folder_button.clicked.connect(self._add_video_folder)
        self.remove_videos_button.clicked.connect(self._remove_selected_videos)
        self.clear_videos_button.clicked.connect(self._clear_videos)
        self.video_list.currentItemChanged.connect(self._load_selected_video)
        self.crop_tool_button.clicked.connect(lambda: self._set_active_tool("crop"))
        self.invert_tool_button.clicked.connect(lambda: self._set_active_tool("invert"))
        self.enhancements_tool_button.clicked.connect(lambda: self._set_active_tool("enhancements"))
        self.trim_tool_button.clicked.connect(lambda: self._set_active_tool("trim"))
        self.process_button.clicked.connect(self._process_all_videos)
        self.timeline.valueChanged.connect(self._timeline_changed)
        self.timeline.trim_active_changed.connect(self._on_trim_active_changed)
        self.timeline.trim_range_changed.connect(self._on_trim_range_changed)
        self.preview.operation_enabled_requested.connect(self._enable_operation_from_preview)
        self.settings_panel.trim_active_range_changed.connect(self._on_trim_active_changed)
        self.settings_panel.trim_range_changed.connect(self._on_trim_range_changed)
        self.settings_panel.trim_range_added.connect(self._add_trim_range)
        self.settings_panel.trim_range_deleted.connect(self._delete_trim_range)
        self.settings_panel.trim_ranges_reset.connect(self._reset_current_video_trim)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f7f8fa;
                color: #111827;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #d8dee8;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px 8px 8px 8px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #374151;
                font-weight: 600;
            }
            QPushButton {
                border: 1px solid #c9d2df;
                border-radius: 5px;
                padding: 7px 10px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #edf7f7;
                border-color: #8ccfcf;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background: #eef1f5;
            }
            QPushButton#PrimaryButton {
                background: #047c7c;
                border-color: #047c7c;
                color: white;
                font-weight: 700;
                padding: 10px;
            }
            QPushButton#PrimaryButton:hover {
                background: #036b6b;
            }
            QPushButton#TinyResetButton {
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
            }
            QFrame#OperationsBar {
                border: 1px solid #cfd7e3;
                border-radius: 6px;
                background: #ffffff;
            }
            QToolButton {
                border: 1px solid #c9d2df;
                border-radius: 5px;
                padding: 7px 10px;
                background: #ffffff;
                font-weight: 600;
            }
            QToolButton:checked {
                background: #eef2f7;
                border-color: #64748b;
            }
            QLabel#TitleLabel {
                font-size: 19px;
                font-weight: 800;
            }
            QLabel#PreviewTitle {
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#SettingsPlaceholder {
                color: #64748b;
                font-size: 12px;
            }
            QFrame#RegionSettings {
                border: 1px solid #d8dee8;
                border-radius: 5px;
                background: #ffffff;
            }
            QLabel#RegionTitle {
                font-weight: 700;
                font-size: 12px;
            }
            QLabel#DimensionLabel {
                color: #64748b;
                font-size: 11px;
            }
            QSpinBox {
                border: 1px solid #cfd7e3;
                border-radius: 4px;
                background: #ffffff;
                padding: 2px 4px;
                font-size: 11px;
            }
            QFrame#EnhancementSettings {
                border: 1px solid #d8dee8;
                border-radius: 5px;
                background: #ffffff;
            }
            QSlider#EnhancementSlider::groove:horizontal {
                height: 5px;
                border-radius: 2px;
                background: #dbe3ee;
            }
            QSlider#EnhancementSlider::handle:horizontal {
                width: 12px;
                margin: -5px 0;
                border-radius: 6px;
                background: #0891b2;
            }
            QListWidget {
                border: 1px solid #cfd7e3;
                border-radius: 5px;
                background: white;
                alternate-background-color: #f8fafc;
                selection-background-color: #c7eeee;
                selection-color: #0f172a;
                font-size: 9px;
            }
            QListWidget::item {
                padding: 1px 3px;
            }
            QGraphicsView {
                border: 1px solid #cfd7e3;
                border-radius: 6px;
                background: #111827;
            }
            QProgressBar {
                border: 1px solid #cfd7e3;
                border-radius: 5px;
                background: white;
                height: 16px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #00a6a6;
                border-radius: 4px;
            }
            """
        )

    def _add_videos(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add video files",
            str(self._project_root),
            f"Video files ({extensions});;All files (*)",
        )
        if not filenames:
            return

        self._add_video_paths(Path(filename) for filename in filenames)

    def _add_video_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Add a folder of videos", str(self._project_root))
        if not directory:
            return

        folder = Path(directory).expanduser().resolve()
        video_paths = [path for path in sorted(folder.rglob("*")) if path.is_file() and is_supported_video(path)]
        if not video_paths:
            QMessageBox.information(self, "No videos found", "That folder does not contain any supported video files.")
            return

        existing = {self.video_list.item(index).data(Qt.UserRole) for index in range(self.video_list.count())}
        new_paths = [path for path in video_paths if str(path) not in existing]
        if not new_paths:
            QMessageBox.information(self, "No new videos", "All supported videos in that folder are already uploaded.")
            return

        duplicate_count = len(video_paths) - len(new_paths)
        details = f"Folder:\n{folder}"
        if duplicate_count:
            details += f"\n\n{duplicate_count} supported video(s) are already in the uploaded list."

        if not self._confirm_action(
            "Add folder of videos?",
            f"Add {len(new_paths)} video(s) from this folder?",
            details,
        ):
            return

        self._add_video_paths(new_paths)

    def _add_video_paths(self, paths) -> None:
        existing = {self.video_list.item(index).data(Qt.UserRole) for index in range(self.video_list.count())}
        added = 0
        skipped = 0

        for candidate in paths:
            path = Path(candidate).expanduser().resolve()
            if not is_supported_video(path):
                skipped += 1
                continue
            if str(path) in existing:
                continue

            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.UserRole, str(path))
            self.video_list.addItem(item)
            existing.add(str(path))
            added += 1

        if added and self.video_list.currentRow() < 0:
            self.video_list.setCurrentRow(0)

        if skipped:
            QMessageBox.information(self, "Unsupported files skipped", f"Skipped {skipped} unsupported file(s).")

        self._update_process_state()

    def _remove_selected_videos(self) -> None:
        for item in self.video_list.selectedItems():
            path_key = item.data(Qt.UserRole)
            self._trim_ranges_by_video.pop(path_key, None)
            self._active_trim_range_by_video.pop(path_key, None)
            self.video_list.takeItem(self.video_list.row(item))
        if self.video_list.count() == 0:
            self._release_capture()
            self.preview.set_frame(None)
            self.preview_title.setText("Select a video from the uploaded list.")
            self.timeline.setRange(0, 0)
            self._refresh_trim_context()
            self.time_label.setText("00:00.000 / 00:00.000")
        self._update_process_state()

    def _clear_videos(self) -> None:
        if self.video_list.count() > 0 and not self._confirm_action(
            "Clear uploaded videos?",
            f"Remove all {self.video_list.count()} uploaded video(s) from the list?",
            "This does not delete files from your computer.",
        ):
            return

        self.video_list.clear()
        self._trim_ranges_by_video.clear()
        self._active_trim_range_by_video.clear()
        self._release_capture()
        self.preview.set_frame(None)
        self.preview_title.setText("Select a video from the uploaded list.")
        self.timeline.setRange(0, 0)
        self._refresh_trim_context()
        self.time_label.setText("00:00.000 / 00:00.000")
        self._update_process_state()

    def _load_selected_video(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        if cv2 is None:
            QMessageBox.critical(self, "OpenCV is missing", "Install the conda environment first: conda env create -f GAIT_ASSEMBLER.yaml")
            return

        path = Path(current.data(Qt.UserRole))
        self._release_capture()
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            QMessageBox.warning(self, "Could not open video", str(path))
            return

        requested_ms = self.timeline.value()
        self._capture = capture
        self._current_video = path
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._duration_ms = int((frame_count / fps) * 1000) if fps > 0 and frame_count > 0 else 0
        self.preview_title.setText(path.name)
        self.timeline.setRange(0, max(0, self._duration_ms))
        self.timeline.setSingleStep(100)
        self.timeline.setPageStep(1000)
        target_ms = min(requested_ms, self._duration_ms)
        self._set_timeline_value(target_ms)
        self._load_frame_at(target_ms)
        self._refresh_trim_context()

    def _timeline_changed(self, value: int) -> None:
        if self._loading_slider:
            return
        self._load_frame_at(value)

    def _load_frame_at(self, ms: int) -> None:
        if self._capture is None or cv2 is None:
            return

        self._capture.set(cv2.CAP_PROP_POS_MSEC, float(ms))
        ok, frame = self._capture.read()
        if not ok:
            frame_count = int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frame_count > 0:
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
                ok, frame = self._capture.read()
        if not ok:
            self.progress.setFormat("Could not read frame")
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        self.preview.set_frame(image)
        self.time_label.setText(f"{_format_ms(ms)} / {_format_ms(self._duration_ms)}")

    def _set_timeline_value(self, value: int) -> None:
        self._loading_slider = True
        self.timeline.setValue(value)
        self._loading_slider = False

    def _refresh_trim_context(self) -> None:
        if self._current_video is None or self._duration_ms <= 0:
            self.timeline.set_trim_ranges(0, [])
            self.settings_panel.set_trim_context(None, 0, [], 0)
            return

        key = str(self._current_video)
        ranges = self._display_trim_ranges(key)
        active_index = self._active_trim_range_by_video.get(key, 0)
        active_index = min(active_index, max(0, len(ranges) - 1))
        self.timeline.set_trim_ranges(self._duration_ms, ranges, active_index)
        self.settings_panel.set_trim_context(self._current_video.name, self._duration_ms, ranges, active_index)

    def _display_trim_ranges(self, key: str) -> list[TrimRange]:
        ranges = self._trim_ranges_by_video.get(key)
        if ranges:
            return list(ranges)
        if self._duration_ms > 0:
            return [TrimRange(0, self._duration_ms)]
        return []

    def _enable_operation_from_preview(self, name: str, enabled: bool) -> None:
        if not enabled:
            return
        if name == "crop":
            self.crop_tool_button.setChecked(True)
            self._set_active_tool("crop")
        elif name == "invert":
            self.invert_tool_button.setChecked(True)
            self._set_active_tool("invert")

    def _set_active_tool(self, name: str) -> None:
        self.preview.set_mode(name)
        self.settings_panel.set_active_tool(name)
        self.timeline.set_trim_editing_enabled(name == "trim")
        self._refresh_trim_context()

    def _on_trim_active_changed(self, index: int) -> None:
        if self._current_video is None:
            return
        key = str(self._current_video)
        self._active_trim_range_by_video[key] = index
        self._refresh_trim_context()

    def _on_trim_range_changed(self, index: int, start_ms: int, end_ms: int) -> None:
        if self._current_video is None or self._duration_ms <= 0:
            return

        key = str(self._current_video)
        ranges = self._display_trim_ranges(key)
        if not ranges:
            return

        index = min(max(0, index), len(ranges) - 1)
        ranges[index] = TrimRange(start_ms, end_ms).clamped(self._duration_ms)
        self._set_current_trim_ranges(ranges, index)

    def _add_trim_range(self) -> None:
        if self._current_video is None or self._duration_ms <= 0:
            return

        key = str(self._current_video)
        ranges = list(self._trim_ranges_by_video.get(key, []))
        span = max(250, min(5000, self._duration_ms // 4 or self._duration_ms))
        start = min(self.timeline.value(), max(0, self._duration_ms - span))
        end = min(self._duration_ms, start + span)
        ranges.append(TrimRange(start, end))
        self._set_current_trim_ranges(ranges, len(ranges) - 1)

    def _delete_trim_range(self, index: int) -> None:
        if self._current_video is None:
            return

        key = str(self._current_video)
        ranges = list(self._trim_ranges_by_video.get(key, []))
        if not ranges:
            self._reset_current_video_trim()
            return

        if 0 <= index < len(ranges):
            ranges.pop(index)
        self._set_current_trim_ranges(ranges, max(0, min(index, len(ranges) - 1)))

    def _reset_current_video_trim(self) -> None:
        if self._current_video is None:
            return

        key = str(self._current_video)
        self._trim_ranges_by_video.pop(key, None)
        self._active_trim_range_by_video.pop(key, None)
        self._refresh_trim_context()

    def _set_current_trim_ranges(self, ranges: list[TrimRange], active_index: int) -> None:
        if self._current_video is None:
            return

        key = str(self._current_video)
        normalized = [trim.clamped(self._duration_ms) for trim in ranges]
        normalized = [trim for trim in normalized if trim.is_usable()]
        active_trim = normalized[active_index] if 0 <= active_index < len(normalized) else None
        normalized = sorted(normalized, key=lambda trim: (trim.start_ms, trim.end_ms))
        if not normalized or self._is_default_trim(normalized):
            self._trim_ranges_by_video.pop(key, None)
            self._active_trim_range_by_video.pop(key, None)
        else:
            self._trim_ranges_by_video[key] = normalized
            if active_trim in normalized:
                self._active_trim_range_by_video[key] = normalized.index(active_trim)
            else:
                self._active_trim_range_by_video[key] = max(0, min(active_index, len(normalized) - 1))
        self._refresh_trim_context()

    def _is_default_trim(self, ranges: list[TrimRange]) -> bool:
        return len(ranges) == 1 and ranges[0].start_ms == 0 and ranges[0].end_ms == self._duration_ms

    def _process_all_videos(self) -> None:
        videos = self._video_paths()
        if not videos:
            QMessageBox.information(self, "No videos", "Add one or more videos before processing.")
            return

        options = ProcessingOptions(
            crop_enabled=self.preview.crop_region() is not None,
            crop_rect=self.preview.crop_region(),
            invert_enabled=bool(self.preview.invert_regions()),
            invert_rects=tuple(self.preview.invert_regions()),
            enhancements=self.preview.enhancement_settings(),
        )
        trim_ranges_by_path = self._trim_ranges_for_processing(videos)
        if not options.has_work() and not trim_ranges_by_path:
            QMessageBox.information(
                self,
                "No operation selected",
                "Draw a Crop or Upside-Down region, adjust an Enhancement, or set a Trim range before processing.",
            )
            return

        if not ffmpeg_available():
            QMessageBox.critical(self, "ffmpeg is missing", "Install the conda environment first, or run: conda install -c conda-forge ffmpeg")
            return

        if not self._confirm_action(
            "Process all uploaded videos?",
            f"Process {len(videos)} uploaded video(s)?",
            "Crop, upside-down, and enhancement settings apply to every video. Trim ranges apply only to the videos where you set them. You will choose the output location next.",
        ):
            return

        output_root = QFileDialog.getExistingDirectory(
            self,
            "Choose Where to Create the Output Folder",
            str(self._default_output_root()),
        )
        if not output_root:
            return

        output_root = Path(output_root).expanduser()
        try:
            session_dir = make_session_output_dir(output_root)
        except Exception as exc:
            QMessageBox.critical(self, "Output error", str(exc))
            return

        self.progress.setRange(0, len(videos))
        self.progress.setValue(0)
        self.progress.setFormat("%v / %m")
        self._processing_errors = []
        self._set_processing_enabled(False)

        self._processing_thread = VideoProcessingThread(videos, session_dir, options, trim_ranges_by_path, self)
        self._processing_thread.file_started.connect(self._on_file_started)
        self._processing_thread.file_finished.connect(self._on_file_finished)
        self._processing_thread.file_failed.connect(self._on_file_failed)
        self._processing_thread.completed.connect(self._on_processing_completed)
        self._processing_thread.start()

    def _on_file_started(self, index: int, total: int, name: str) -> None:
        self.progress.setFormat(f"{index} / {total}")

    def _on_file_finished(self, input_path: str, output_path: str) -> None:
        self.progress.setValue(self.progress.value() + 1)

    def _on_file_failed(self, input_path: str, message: str) -> None:
        self.progress.setValue(self.progress.value() + 1)
        self._processing_errors.append(f"{Path(input_path).name}: {message}")

    def _on_processing_completed(self, session_dir: str) -> None:
        self.progress.setFormat("Done")
        self._set_processing_enabled(True)
        if self._processing_thread is not None:
            self._processing_thread.deleteLater()
            self._processing_thread = None
        if self._processing_errors:
            QMessageBox.warning(
                self,
                "Processing finished with errors",
                f"Output folder:\n{session_dir}\n\nFailed files:\n" + "\n".join(self._processing_errors[:8]),
            )
        else:
            QMessageBox.information(self, "Processing complete", f"Output folder:\n{session_dir}")

    def _video_paths(self) -> list[Path]:
        return [Path(self.video_list.item(index).data(Qt.UserRole)) for index in range(self.video_list.count())]

    def _trim_ranges_for_processing(self, videos: list[Path]) -> dict[str, tuple[TrimRange, ...]]:
        ranges_by_path = {}
        for path in videos:
            ranges = self._trim_ranges_by_video.get(str(path))
            if ranges:
                ranges_by_path[str(path)] = tuple(sorted(ranges, key=lambda trim: (trim.start_ms, trim.end_ms)))
        return ranges_by_path

    def _confirm_action(self, title: str, text: str, details: str = "") -> bool:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Question)
        message.setWindowTitle(title)
        message.setText(text)
        if details:
            message.setInformativeText(details)
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        message.setDefaultButton(QMessageBox.StandardButton.No)
        return message.exec() == QMessageBox.StandardButton.Yes

    def _update_process_state(self) -> None:
        self.process_button.setEnabled(self.video_list.count() > 0)

    def _set_processing_enabled(self, enabled: bool) -> None:
        self.add_videos_button.setEnabled(enabled)
        self.add_folder_button.setEnabled(enabled)
        self.remove_videos_button.setEnabled(enabled)
        self.clear_videos_button.setEnabled(enabled)
        self.process_button.setEnabled(enabled and self.video_list.count() > 0)
        self.crop_tool_button.setEnabled(enabled)
        self.invert_tool_button.setEnabled(enabled)
        self.enhancements_tool_button.setEnabled(enabled)
        self.trim_tool_button.setEnabled(enabled)

    def _default_output_root(self) -> Path:
        output_root = self._project_root / "outputs" / "videos"
        output_root.mkdir(parents=True, exist_ok=True)
        return output_root

    def _release_capture(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._current_video = None


def _make_tool_button(text: str, color: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setIcon(_dot_icon(color))
    button.setIconSize(QSize(12, 12))
    button.setCheckable(True)
    button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    return button


def _dot_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pixmap)


def _format_ms(ms: int) -> str:
    total_seconds, milliseconds = divmod(max(0, int(ms)), 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


VideoProcessingWindow = VideoEditorWidget
