"""Display selectable preview videos, debounce seeking, and own capture cleanup."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.shared.business.media_access_contracts import MediaAccessPort
from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet as _dependency_theme_stylesheet


@dataclass(frozen=True)
class MediaPreviewSource:
    path: Path
    title: str
    details: str
    view_name: str


class MediaPreviewDialog(QDialog):
    _SEEK_DEBOUNCE_MS = 40
    _READ_AHEAD_FRAMES = 12
    _FRAME_CACHE_BYTES = 96 * 1024 * 1024

    def __init__(
        self,
        path: Path,
        parent: QWidget | None = None,
        *,
        subtitle: str | None = None,
        review_sources: tuple[MediaPreviewSource, ...] | None = None,
        initial_source_index: int = 0,
        media_access: MediaAccessPort,
    ):
        super().__init__(parent)
        self.media_access = media_access
        initial_path = path.expanduser().resolve()
        self._review_sources = review_sources or (
            MediaPreviewSource(initial_path, initial_path.name, subtitle or "", ""),
        )
        if not self._review_sources:
            raise ValueError("No videos are available for preview.")
        self._source_index = max(0, min(initial_source_index, len(self._review_sources) - 1))
        self._path = initial_path
        self._capture = None
        self._frame_count = 1
        self._fps = 0.0
        self._source_pixmap = QPixmap()
        self._frame_cache: OrderedDict[int, QImage] = OrderedDict()
        self._frame_cache_bytes = 0
        self._capture_next_frame_index = 0
        self._pending_frame_index: int | None = None
        self._buffer_next_frame_index: int | None = None
        self._buffer_frames_remaining = 0
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(self._SEEK_DEBOUNCE_MS)
        self._seek_timer.timeout.connect(self._load_pending_frame)
        self._buffer_timer = QTimer(self)
        self._buffer_timer.setSingleShot(True)
        self._buffer_timer.setInterval(1)
        self._buffer_timer.timeout.connect(self._buffer_next_frame)
        self.setWindowTitle("Video preview")
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        self.title_label = QLabel()
        self.title_label.setObjectName("LargeVideoPreviewTitle")
        self.title_label.setWordWrap(True)
        root.addWidget(self.title_label)
        source_row = QHBoxLayout()
        source_row.setSpacing(6)
        self.previous_video_button = QToolButton()
        self.previous_video_button.setObjectName("VideoPreviewNavigationButton")
        self.previous_video_button.setText("←")
        self.previous_video_button.setToolTip("Previous preview video")
        source_row.addWidget(self.previous_video_button)
        self.source_selector = QComboBox()
        self.source_selector.setObjectName("VideoPreviewSourceSelector")
        self.source_selector.setToolTip("Switch the video shown in this preview window.")
        for source in self._review_sources:
            self.source_selector.addItem(source.title)
        source_row.addWidget(self.source_selector, 1)
        self.next_video_button = QToolButton()
        self.next_video_button.setObjectName("VideoPreviewNavigationButton")
        self.next_video_button.setText("→")
        self.next_video_button.setToolTip("Next preview video")
        source_row.addWidget(self.next_video_button)
        self.view_label = QLabel()
        self.view_label.setObjectName("VideoPreviewView")
        source_row.addWidget(self.view_label)
        root.addLayout(source_row)
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("LargeVideoPreviewSubtitle")
        self.subtitle_label.setWordWrap(True)
        root.addWidget(self.subtitle_label)
        self.preview = QLabel("Loading preview…")
        self.preview.setObjectName("LargeVideoPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(680, 380)
        root.addWidget(self.preview, 1)
        slider_row = QHBoxLayout()
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setObjectName("VideoPreviewSlider")
        self.frame_slider.setRange(0, self._frame_count - 1)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(max(1, self._frame_count // 20))
        self.frame_label = QLabel()
        self.frame_label.setObjectName("VideoPreviewFrameLabel")
        self.frame_label.setMinimumWidth(150)
        self.frame_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider_row.addWidget(self.frame_slider, 1)
        slider_row.addWidget(self.frame_label)
        root.addLayout(slider_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.frame_slider.valueChanged.connect(self._queue_frame)
        self.frame_slider.sliderPressed.connect(self._pause_buffering)
        self.frame_slider.sliderReleased.connect(self._flush_pending_frame)
        self.source_selector.currentIndexChanged.connect(self._select_review_source)
        self.previous_video_button.clicked.connect(
            lambda _checked=False: self._select_review_source(self._source_index - 1)
        )
        self.next_video_button.clicked.connect(
            lambda _checked=False: self._select_review_source(self._source_index + 1)
        )
        self.setStyleSheet(
            _dependency_theme_stylesheet(
                "\n                QLabel#LargeVideoPreviewTitle {\n                    color: {theme.TEXT};\n                    font-size: 14px;\n                    font-weight: 650;\n                }\n                QLabel#LargeVideoPreviewSubtitle {\n                    color: {theme.CONNECTOR};\n                    font-size: 11px;\n                }\n                QLabel#VideoPreviewView {\n                    background: {theme.PANEL};\n                    border: 1px solid {theme.BORDER};\n                    border-radius: 2px;\n                    color: {theme.TEXT};\n                    font-size: 11px;\n                    font-weight: 650;\n                    padding: 3px 6px;\n                }\n                QComboBox#VideoPreviewSourceSelector {\n                    min-width: 260px;\n                }\n                QToolButton#VideoPreviewNavigationButton {\n                    min-width: 28px;\n                    min-height: 26px;\n                    font-size: 16px;\n                    font-weight: 700;\n                }\n                QLabel#LargeVideoPreview {\n                    background: {theme.CANVAS};\n                    border: 1px solid {theme.BORDER};\n                    color: {theme.CANVAS_TEXT};\n                }\n                QLabel#VideoPreviewFrameLabel {\n                    color: {theme.CONNECTOR};\n                    font-size: 11px;\n                }\n                "
            )
        )
        self._select_review_source(self._source_index)

    def _select_review_source(self, index: int) -> None:
        self._seek_timer.stop()
        self._buffer_timer.stop()
        self._pending_frame_index = None
        self._buffer_next_frame_index = None
        self._buffer_frames_remaining = 0
        self._clear_frame_cache()
        index = max(0, min(index, len(self._review_sources) - 1))
        source = self._review_sources[index]
        capture = self.media_access.open_video(source.path)
        if self._capture is not None:
            self._capture.close()
        self._capture = capture
        self._capture_next_frame_index = 0
        self._source_index = index
        self._path = source.path
        frame_count_value = capture.info.frame_count
        fps_value = capture.info.fps
        self._frame_count = max(1, int(frame_count_value)) if frame_count_value > 0 else 1
        self._fps = float(fps_value) if fps_value > 0 else 0.0
        self.setWindowTitle(f"Video preview — {source.title}")
        self.title_label.setText(source.title)
        self.subtitle_label.setText(source.details)
        self.subtitle_label.setVisible(bool(source.details))
        self.view_label.setText(f"View: {source.view_name}")
        self.view_label.setVisible(bool(source.view_name))
        self.previous_video_button.setEnabled(index > 0)
        self.next_video_button.setEnabled(index < len(self._review_sources) - 1)
        source_blocker = QSignalBlocker(self.source_selector)
        self.source_selector.setCurrentIndex(index)
        del source_blocker
        slider_blocker = QSignalBlocker(self.frame_slider)
        self.frame_slider.setRange(0, self._frame_count - 1)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(max(1, self._frame_count // 20))
        self.frame_slider.setValue(0)
        del slider_blocker
        self._load_frame(0)

    def _queue_frame(self, frame_index: int) -> None:
        frame_index = max(0, min(int(frame_index), self._frame_count - 1))
        self._pending_frame_index = frame_index
        self._pause_buffering()
        if frame_index in self._frame_cache:
            self._seek_timer.stop()
            self._load_pending_frame()
            return
        self._seek_timer.start(self._SEEK_DEBOUNCE_MS if self.frame_slider.isSliderDown() else 0)

    def _flush_pending_frame(self) -> None:
        self._seek_timer.stop()
        self._load_pending_frame()

    def _load_pending_frame(self) -> None:
        if self._pending_frame_index is None:
            return
        frame_index = self._pending_frame_index
        self._pending_frame_index = None
        self._load_frame(frame_index)

    def _load_frame(self, frame_index: int) -> None:
        if self._capture is None:
            return
        cached = self._frame_cache.get(frame_index)
        if cached is not None:
            self._frame_cache.move_to_end(frame_index)
            self._show_frame(frame_index, cached)
            self._start_buffering(frame_index + 1)
            return
        frame = self._capture.read_frame(frame_index)
        self._capture_next_frame_index = frame_index + 1
        if frame is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Could not read this frame")
            return
        image = self._frame_image(frame)
        self._cache_frame(frame_index, image)
        self._show_frame(frame_index, image)
        self._start_buffering(frame_index + 1)

    @staticmethod
    def _frame_image(frame) -> QImage:
        rgb = frame
        (height, width, channels) = rgb.shape
        return QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()

    def _show_frame(self, frame_index: int, image: QImage) -> None:
        self._source_pixmap = QPixmap.fromImage(image)
        self._render_frame()
        seconds = frame_index / self._fps if self._fps > 0 else 0.0
        self.frame_label.setText(f"{frame_index + 1:,} / {self._frame_count:,}   {seconds:.2f} s")

    def _cache_frame(self, frame_index: int, image: QImage) -> None:
        image_bytes = int(image.sizeInBytes())
        previous = self._frame_cache.pop(frame_index, None)
        if previous is not None:
            self._frame_cache_bytes -= int(previous.sizeInBytes())
        if image_bytes > self._FRAME_CACHE_BYTES:
            return
        self._frame_cache[frame_index] = image
        self._frame_cache_bytes += image_bytes
        while self._frame_cache_bytes > self._FRAME_CACHE_BYTES and self._frame_cache:
            (_old_index, old_image) = self._frame_cache.popitem(last=False)
            self._frame_cache_bytes -= int(old_image.sizeInBytes())

    def _clear_frame_cache(self) -> None:
        self._frame_cache.clear()
        self._frame_cache_bytes = 0

    def _pause_buffering(self) -> None:
        self._buffer_timer.stop()
        self._buffer_next_frame_index = None
        self._buffer_frames_remaining = 0

    def _start_buffering(self, frame_index: int) -> None:
        if self.frame_slider.isSliderDown() or frame_index >= self._frame_count:
            return
        self._buffer_next_frame_index = frame_index
        self._buffer_frames_remaining = min(self._READ_AHEAD_FRAMES, self._frame_count - frame_index)
        if self._buffer_frames_remaining:
            self._buffer_timer.start()

    def _buffer_next_frame(self) -> None:
        frame_index = self._buffer_next_frame_index
        if (
            self._capture is None
            or frame_index is None
            or self._pending_frame_index is not None
            or self.frame_slider.isSliderDown()
            or (self._capture_next_frame_index != frame_index)
            or (self._buffer_frames_remaining <= 0)
        ):
            self._pause_buffering()
            return
        frame = self._capture.read_next()
        if frame is None:
            self._pause_buffering()
            return
        self._capture_next_frame_index = frame_index + 1
        self._cache_frame(frame_index, self._frame_image(frame))
        self._buffer_next_frame_index = frame_index + 1
        self._buffer_frames_remaining -= 1
        if self._buffer_frames_remaining:
            self._buffer_timer.start()

    def _render_frame(self) -> None:
        if self._source_pixmap.isNull():
            return
        self.preview.setText("")
        self.preview.setPixmap(
            self._source_pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_frame()

    def closeEvent(self, event) -> None:
        self._seek_timer.stop()
        self._buffer_timer.stop()
        self._clear_frame_cache()
        if self._capture is not None:
            self._capture.close()
            self._capture = None
        super().closeEvent(event)

    def done(self, result):
        self._seek_timer.stop()
        self._buffer_timer.stop()
        self._clear_frame_cache()
        if self._capture is not None:
            self._capture.close()
            self._capture = None
        super().done(result)
