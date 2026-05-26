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
    QSlider,
)

from dlc_gait_assembly.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.gui.video_editor.preview import RegionPreviewView
from dlc_gait_assembly.gui.video_editor.settings_panel import OperationSettingsPanel
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
        self.crop_tool_button.setChecked(True)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.crop_tool_button)
        self.tool_group.addButton(self.invert_tool_button)
        tool_row.addWidget(self.crop_tool_button)
        tool_row.addWidget(self.invert_tool_button)
        tool_row.addStretch(1)
        operations_layout.addLayout(tool_row)
        right_layout.addWidget(operations_bar)

        right_layout.addWidget(self.preview, 1)

        timeline_row = QHBoxLayout()
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(180)
        self.timeline = QSlider(Qt.Horizontal)
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
        self.process_button.clicked.connect(self._process_all_videos)
        self.timeline.valueChanged.connect(self._timeline_changed)
        self.preview.operation_enabled_requested.connect(self._enable_operation_from_preview)

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

        self._add_video_paths(video_paths)

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
            self.video_list.takeItem(self.video_list.row(item))
        if self.video_list.count() == 0:
            self._release_capture()
            self.preview.set_frame(None)
            self.preview_title.setText("Select a video from the uploaded list.")
            self.timeline.setRange(0, 0)
            self.time_label.setText("00:00.000 / 00:00.000")
        self._update_process_state()

    def _clear_videos(self) -> None:
        self.video_list.clear()
        self._release_capture()
        self.preview.set_frame(None)
        self.preview_title.setText("Select a video from the uploaded list.")
        self.timeline.setRange(0, 0)
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
        )
        if not options.has_work():
            QMessageBox.information(self, "No operation selected", "Draw a Crop or Upside-Down region before processing.")
            return

        if not ffmpeg_available():
            QMessageBox.critical(self, "ffmpeg is missing", "Install the conda environment first, or run: conda install -c conda-forge ffmpeg")
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

        self._processing_thread = VideoProcessingThread(videos, session_dir, options, self)
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
