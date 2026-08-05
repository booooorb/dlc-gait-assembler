"""Reusable automated-pipeline media preview widgets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QPainter, QPen, QPixmap
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
        self.frame_slider.valueChanged.connect(self._load_frame)
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
        index = max(0, min(index, len(self._review_sources) - 1))
        source = self._review_sources[index]
        capture = cv2.VideoCapture(str(source.path))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Could not open video: {source.path.name}")
        if self._capture is not None:
            self._capture.release()
        self._capture = capture
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

    def _load_frame(self, frame_index: int) -> None:
        if self._capture is None:
            return
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, frame = self._capture.read()
        if not success or frame is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Could not read this frame")
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._render_frame()
        seconds = frame_index / self._fps if self._fps > 0 else 0.0
        self.frame_label.setText(
            f"{frame_index + 1:,} / {self._frame_count:,}   {seconds:.2f} s"
        )

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
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        super().closeEvent(event)


class DoubleClickLabel(QLabel):
    double_clicked = Signal()

    def sizeHint(self) -> QSize:
        # QLabel normally adopts its pixmap's dimensions as its size hint. The
        # stickplot is scalable, so loading a 640x240 result must not resize the
        # pipeline workspace around it.
        return QSize(240, 78)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()


class PipelineImagePreviewDialog(QDialog):
    def __init__(self, title: str, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap = pixmap
        self.setWindowTitle(title)
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("LargeVideoPreview")
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
                QLabel#LargeVideoPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                }
                """
            )
        )
        self._render_preview()

    def _render_preview(self) -> None:
        self.preview.setPixmap(
            self._source_pixmap.scaled(
                self.preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_preview()


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


def pixmap_from_image_file(path: Path, width: int, height: int) -> QPixmap | None:
    try:
        if path.suffix.casefold() == ".svg":
            data = qt_safe_svg_bytes(path.read_bytes())
            pixmap = QPixmap()
            if not pixmap.loadFromData(data, "SVG"):
                return None
        else:
            pixmap = QPixmap(str(path))
    except OSError:
        return None
    if pixmap.isNull():
        return None
    return pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def demo_stickplot_pixmap(width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("white"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    margin = max(18, width // 28)
    baseline = height - margin * 2
    painter.setPen(QPen(QColor("#b9b2a8"), max(1, width // 600)))
    painter.drawLine(margin, baseline, width - margin, baseline)
    painter.setPen(QPen(QColor(theme.PRIMARY), max(2, width // 300)))
    pose_count = 6
    spacing = (width - margin * 2) / pose_count
    scale = max(0.7, min(width / 900, height / 420))
    for pose in range(pose_count):
        x = int(margin + spacing * (pose + 0.5))
        phase = (pose - 2.5) / 2.5
        hip = (x, int(baseline - 115 * scale))
        knee = (int(x + phase * 24 * scale), int(baseline - 70 * scale))
        ankle = (int(x - phase * 30 * scale), int(baseline - 24 * scale))
        toe = (int(ankle[0] + 25 * scale), baseline)
        crest = (int(x - 8 * scale), int(baseline - 155 * scale))
        shoulder = (int(x + 12 * scale), int(baseline - 195 * scale))
        joints = (shoulder, crest, hip, knee, ankle, toe)
        for start, end in zip(joints, joints[1:], strict=False):
            painter.drawLine(start[0], start[1], end[0], end[1])
        radius = max(2, int(4 * scale))
        for joint_x, joint_y in joints:
            painter.drawEllipse(joint_x - radius, joint_y - radius, radius * 2, radius * 2)
    painter.setPen(QColor("#5f5a54"))
    painter.drawText(margin, margin, "Demo stickplot preview — double-click for large view")
    painter.end()
    return pixmap


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
