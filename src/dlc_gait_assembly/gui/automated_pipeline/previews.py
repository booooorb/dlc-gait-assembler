"""Reusable automated-pipeline media preview widgets."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.svg import qt_safe_svg_bytes
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS

try:
    import cv2
except ImportError:
    cv2 = None


@dataclass(frozen=True)
class ReviewVideoSource:
    path: Path
    title: str
    details: str
    view_name: str

class AutomationVideoPreviewDialog(QDialog):
    _SEEK_DEBOUNCE_MS = 40
    _READ_AHEAD_FRAMES = 12
    _FRAME_CACHE_BYTES = 96 * 1024 * 1024

    def __init__(
        self,
        path: Path,
        parent: QWidget | None = None,
        *,
        subtitle: str | None = None,
        review_sources: tuple[ReviewVideoSource, ...] | None = None,
        initial_source_index: int = 0,
    ):
        if cv2 is None:
            raise OSError("OpenCV is not available for video preview.")
        super().__init__(parent)
        initial_path = path.expanduser().resolve()
        self._review_sources = review_sources or (
            ReviewVideoSource(initial_path, initial_path.name, subtitle or "", ""),
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
            theme.stylesheet(
                """
                QLabel#LargeVideoPreviewTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                }
                QLabel#LargeVideoPreviewSubtitle {
                    color: {theme.CONNECTOR};
                    font-size: 11px;
                }
                QLabel#VideoPreviewView {
                    background: {theme.PANEL};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 650;
                    padding: 3px 6px;
                }
                QComboBox#VideoPreviewSourceSelector {
                    min-width: 260px;
                }
                QToolButton#VideoPreviewNavigationButton {
                    min-width: 28px;
                    min-height: 26px;
                    font-size: 16px;
                    font-weight: 700;
                }
                QLabel#LargeVideoPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                }
                QLabel#VideoPreviewFrameLabel {
                    color: {theme.CONNECTOR};
                    font-size: 11px;
                }
                """
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
        capture = cv2.VideoCapture(str(source.path))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Could not open video: {source.path.name}")
        if self._capture is not None:
            self._capture.release()
        self._capture = capture
        self._capture_next_frame_index = 0
        self._source_index = index
        self._path = source.path
        frame_count_value = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps_value = capture.get(cv2.CAP_PROP_FPS)
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
        self._seek_timer.start(
            self._SEEK_DEBOUNCE_MS if self.frame_slider.isSliderDown() else 0
        )

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
        if self._capture_next_frame_index != frame_index:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            self._capture_next_frame_index = frame_index
        success, frame = self._capture.read()
        self._capture_next_frame_index = frame_index + 1
        if not success or frame is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Could not read this frame")
            return
        image = self._frame_image(frame)
        self._cache_frame(frame_index, image)
        self._show_frame(frame_index, image)
        self._start_buffering(frame_index + 1)

    @staticmethod
    def _frame_image(frame) -> QImage:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        return QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format_RGB888,
        ).copy()

    def _show_frame(self, frame_index: int, image: QImage) -> None:
        self._source_pixmap = QPixmap.fromImage(image)
        self._render_frame()
        seconds = frame_index / self._fps if self._fps > 0 else 0.0
        self.frame_label.setText(
            f"{frame_index + 1:,} / {self._frame_count:,}   {seconds:.2f} s"
        )

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
            _old_index, old_image = self._frame_cache.popitem(last=False)
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
        self._buffer_frames_remaining = min(
            self._READ_AHEAD_FRAMES,
            self._frame_count - frame_index,
        )
        if self._buffer_frames_remaining:
            self._buffer_timer.start()

    def _buffer_next_frame(self) -> None:
        frame_index = self._buffer_next_frame_index
        if (
            self._capture is None
            or frame_index is None
            or self._pending_frame_index is not None
            or self.frame_slider.isSliderDown()
            or self._capture_next_frame_index != frame_index
            or self._buffer_frames_remaining <= 0
        ):
            self._pause_buffering()
            return
        success, frame = self._capture.read()
        if not success or frame is None:
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
            self._source_pixmap.scaled(
                self.preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_frame()

    def closeEvent(self, event) -> None:
        self._seek_timer.stop()
        self._buffer_timer.stop()
        self._clear_frame_cache()
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        super().closeEvent(event)


class AspectRatioImageLabel(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self._source_svg_data: bytes | None = None

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._source_svg_data = None
        self._source_pixmap = pixmap
        self._render_pixmap()

    def load_image_path(self, path: Path) -> bool:
        path = Path(path)
        if path.suffix.casefold() == ".svg":
            try:
                svg_data = qt_safe_svg_bytes(path.read_bytes())
            except OSError:
                return False
            renderer = QSvgRenderer(QByteArray(svg_data))
            if not renderer.isValid():
                return False
            renderer.setAspectRatioMode(Qt.KeepAspectRatio)
            self._source_svg_data = svg_data
            self._source_pixmap = QPixmap()
        else:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                return False
            self._source_svg_data = None
            self._source_pixmap = pixmap
        self._render_pixmap()
        return True

    def _render_pixmap(self) -> None:
        target = self.contentsRect().size()
        if target.isEmpty():
            return
        if self._source_svg_data is not None:
            rendered = render_svg_pixmap(
                self._source_svg_data,
                target,
                device_pixel_ratio=max(1.0, self.devicePixelRatioF()),
            )
            QLabel.setPixmap(self, rendered)
            return
        if self._source_pixmap.isNull():
            QLabel.setPixmap(self, QPixmap())
            return
        QLabel.setPixmap(
            self,
            self._source_pixmap.scaled(
                target,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            ),
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_pixmap()


def render_svg_pixmap(
    svg_data: bytes,
    target_size: QSize,
    *,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    """Render SVG at the requested logical size and display pixel ratio."""

    ratio = max(1.0, float(device_pixel_ratio))
    physical_size = QSize(
        max(1, round(target_size.width() * ratio)),
        max(1, round(target_size.height() * ratio)),
    )
    pixmap = QPixmap(physical_size)
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(qt_safe_svg_bytes(svg_data)))
    renderer.setAspectRatioMode(Qt.KeepAspectRatio)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(
        painter,
        QRectF(0, 0, physical_size.width(), physical_size.height()),
    )
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class DoubleClickLabel(AspectRatioImageLabel):
    clicked = Signal()
    double_clicked = Signal()

    def sizeHint(self) -> QSize:
        # QLabel normally adopts its pixmap's dimensions as its size hint. The
        # stickplot is scalable, so loading a 640x240 result must not resize the
        # pipeline workspace around it.
        return QSize(240, 78)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()


class PipelineImagePreviewDialog(QDialog):
    def __init__(
        self,
        title: str,
        image_path: Path,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        self.preview = AspectRatioImageLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("LargeImagePreview")
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            theme.stylesheet(
                """
                QLabel#LargeVideoPreviewTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                }
                QLabel#LargeImagePreview {
                    background: white;
                    border: 1px solid {theme.BORDER};
                }
                """
            )
        )
        self.image_loaded = self.preview.load_image_path(image_path)
        if not self.image_loaded:
            self.preview.setText("Could not render this generated image.")


class PipelineTextPreviewDialog(QDialog):
    def __init__(self, title: str, details: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        preview = QLabel(details)
        preview.setObjectName("LargeVideoPreview")
        preview.setAlignment(Qt.AlignCenter)
        preview.setWordWrap(True)
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            theme.stylesheet(
                """
                QLabel#LargeVideoPreviewTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                }
                QLabel#LargeVideoPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                    padding: 24px;
                }
                """
            )
        )


class VideoDropList(QListWidget):
    paths_dropped = Signal(object)
    pointer_left = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setMouseTracking(True)
        self.setProperty("dropActive", False)
        self.add_videos_button = QPushButton("Add videos", self.viewport())
        self.add_videos_button.setObjectName("AddVideosButton")
        self.add_videos_button.setIcon(interface_icon("document", theme.PRIMARY_TEXT))
        self.add_videos_button.setIconSize(QSize(16, 16))
        self.add_videos_button.setToolTip(
            "Add one or more source videos to the queue. Supported video files can also "
            "be dragged into this area; adding a video does not modify it."
        )
        self._position_empty_action()

    def set_empty_action_visible(self, visible: bool) -> None:
        self.add_videos_button.setVisible(visible)
        if visible:
            self.add_videos_button.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_empty_action()

    def _position_empty_action(self) -> None:
        hint = self.add_videos_button.sizeHint()
        width = max(126, hint.width())
        height = max(38, hint.height())
        x = max(8, (self.viewport().width() - width) // 2)
        y = max(20, self.viewport().height() // 2 - 70)
        self.add_videos_button.setGeometry(x, y, width, height)

    def leaveEvent(self, event) -> None:
        self.pointer_left.emit()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        if self.itemAt(event.position().toPoint()) is None:
            self.pointer_left.emit()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._video_paths(event.mimeData().urls()):
            self._set_drop_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._video_paths(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drop_active(False)
        paths = self._video_paths(event.mimeData().urls())
        if not paths:
            event.ignore()
            return
        self.paths_dropped.emit(paths)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)
        super().dragLeaveEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = self.viewport().rect()
        action_bottom = self.add_videos_button.geometry().bottom()

        title_font = painter.font()
        title_font.setPointSizeF(14.0)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            bounds.adjusted(24, action_bottom + 16, -24, -24),
            Qt.AlignHCenter | Qt.AlignTop,
            "Drop videos here",
        )

        helper_font = painter.font()
        helper_font.setPointSizeF(11.0)
        helper_font.setBold(False)
        painter.setFont(helper_font)
        painter.setPen(QColor(theme.CONNECTOR))
        painter.drawText(
            bounds.adjusted(44, action_bottom + 43, -44, -20),
            Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
            "or drag files anywhere into this area",
        )

    def _set_drop_active(self, active: bool) -> None:
        if self.property("dropActive") is bool(active):
            return
        self.setProperty("dropActive", bool(active))
        self.style().unpolish(self)
        self.style().polish(self)
        self.viewport().update()

    @staticmethod
    def _video_paths(urls) -> list[Path]:
        paths = []
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile()).expanduser().resolve()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                paths.append(path)
        return paths
