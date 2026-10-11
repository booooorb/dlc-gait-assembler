"""Manage event-frame navigation and decoded previews for each Ladder camera."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QSlider, QVBoxLayout


class LadderVideoReview:
    """LadderVideoReview operates on its explicitly supplied LadderAnalysisWidget view."""

    def __init__(self, view):
        self.view = view

    def _release_video(self, view: str) -> None:
        attribute = "_right_video_capture" if view == "right" else "_video_capture"
        capture = getattr(self.view, attribute)
        if capture is not None:
            capture.close()
            setattr(self.view, attribute, None)
        self.view.state.video_frame_counts[view] = 0

    def _show_video_frame(self, frame_number: int) -> None:
        view = self.view.state.active_preview_view
        self.view.frame_label.setText(f"{view.title()} view · frame {frame_number}")
        capture = self.view._right_video_capture if view == "right" else self.view._video_capture
        if capture is None:
            self.view.video_preview.setText(
                f"No {view}-view video loaded. The event still remains available for CSV review."
            )
            return
        try:
            frame = capture.read_frame(frame_number)
            if frame is None:
                return
            rgb = frame
            image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
            preview_size = self.view.video_preview.contentsRect().size()
            pixmap = QPixmap.fromImage(image).scaled(
                preview_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.view.video_preview.setPixmap(pixmap)
        except Exception:
            return


def build_ladder_video(self, review_layout):
    preview_box = QGroupBox("Optional video review")
    preview_layout = QVBoxLayout(preview_box)
    self.video_preview = QLabel("Choose the corresponding video to review detected events.")
    self.video_preview.setObjectName("VideoPreview")
    self.video_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.video_preview.setMinimumHeight(260)
    self.video_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
    self.video_preview.setWordWrap(True)
    self.frame_slider = QSlider(Qt.Orientation.Horizontal)
    self.frame_slider.setRange(0, 0)
    self.frame_label = QLabel("Frame —")
    preview_layout.addWidget(self.video_preview, 1)
    preview_layout.addWidget(self.frame_slider)
    preview_layout.addWidget(self.frame_label)
    review_layout.addWidget(preview_box, 2)
