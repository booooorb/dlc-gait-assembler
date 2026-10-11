"""Request and present video frames while hovering over queued inputs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QListWidgetItem, QMessageBox

from dlc_gait_assembly.shared.client.media_preview_dialog import MediaPreviewDialog


class AutomaticVideoHoverPreview:
    """AutomaticVideoHoverPreview operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _start_hover_preview(self, item: QListWidgetItem) -> None:
        self._release_hover_capture()
        path = Path(str(item.data(Qt.UserRole)))
        self._show_hover_card(item, path)
        self.view.video_hover_preview.setPixmap(QPixmap())
        try:
            capture = self.view.media_access.open_video(path)
        except OSError:
            self.view.video_hover_preview.setText("Could not play preview")
            return
        self.view._hover_capture = capture
        self.view._hover_preview_path = path
        fps = float(capture.info.fps)
        width = int(capture.info.width)
        height = int(capture.info.height)
        frame_count = int(capture.info.frame_count)
        duration = frame_count / fps if fps > 0 else 0
        details = []
        if width > 0 and height > 0:
            details.append(f"{width}×{height}")
        if fps > 0:
            fps_text = f"{fps:.2f}".rstrip("0").rstrip(".")
            details.append(f"{fps_text} fps")
        if duration > 0:
            details.append(f"{duration:.1f} s")
        details.append(self._format_file_size(self.view.media_access.file_size(path)))
        self.view.video_hover_details.setText("  •  ".join(details))
        interval = round(1000 / fps) if fps > 0 else 83
        self.view._hover_preview_timer.start(max(33, min(150, interval)))
        self._advance_hover_preview()

    def _advance_hover_preview(self) -> None:
        capture = self.view._hover_capture
        if capture is None:
            return
        frame = capture.read_next()
        if frame is None:
            frame = capture.read_frame(0)
        if frame is None:
            self._release_hover_capture()
            self.view.video_hover_preview.setPixmap(QPixmap())
            self.view.video_hover_preview.setText("Could not play preview")
            return
        self._render_hover_preview_frame(frame)

    def _stop_hover_preview(self) -> None:
        self._release_hover_capture()
        self.view.video_hover_card.hide()

    def _release_hover_capture(self) -> None:
        self.view._hover_preview_timer.stop()
        if self.view._hover_capture is not None:
            self.view._hover_capture.close()
        self.view._hover_capture = None
        self.view._hover_preview_path = None

    def _show_hover_card(self, item: QListWidgetItem, path: Path) -> None:
        display_name = path.name if len(path.name) <= 36 else f"{path.stem[:29]}…{path.suffix}"
        self.view.video_hover_name.setText(display_name)
        self.view.video_hover_name.setToolTip(str(path))
        self.view.video_hover_details.setText("Double-click for expanded preview")
        viewport = self.view.video_list.viewport()
        item_rect = self.view.video_list.visualItemRect(item)
        margin = 8
        x = max(margin, viewport.width() - self.view.video_hover_card.width() - margin)
        y = item_rect.bottom() + 5
        if y + self.view.video_hover_card.height() > viewport.height() - margin:
            y = item_rect.top() - self.view.video_hover_card.height() - 5
        y = max(margin, y)
        self.view.video_hover_card.move(x, y)
        self.view.video_hover_card.raise_()
        self.view.video_hover_card.show()

    @staticmethod
    def _format_file_size(size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def _render_hover_preview_frame(self, frame) -> None:
        rgb = frame
        (height, width, channels) = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.view.video_hover_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.view.video_hover_preview.setText("")
        self.view.video_hover_preview.setPixmap(pixmap)

    def _open_large_video_preview(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.view.video_list.currentItem()
        if item is None:
            return
        path = Path(str(item.data(Qt.UserRole)))
        try:
            dialog = MediaPreviewDialog(path, self.view, media_access=self.view.media_access)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.view, "Could not preview video", str(exc))
            return
        if self.view._large_preview_dialog is not None:
            self.view._large_preview_dialog.close()
        self.view._large_preview_dialog = dialog
        dialog.finished.connect(lambda _result, closed_dialog=dialog: self._large_preview_closed(closed_dialog))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _large_preview_closed(self, dialog: MediaPreviewDialog) -> None:
        if self.view._large_preview_dialog is dialog:
            self.view._large_preview_dialog = None
