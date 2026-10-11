"""Display and edit the automatic run's selected input-video queue."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPainter
from PySide6.QtWidgets import QFileDialog, QListWidget, QListWidgetItem, QPushButton

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class AutomaticVideoQueue:
    """AutomaticVideoQueue operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_videos(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        (paths, _) = QFileDialog.getOpenFileNames(
            self.view,
            "Add videos for automated processing",
            str(Path.home()),
            f"Video files ({extensions});;All files (*)",
        )
        self._add_video_paths([Path(path) for path in paths])

    def _add_video_paths(self, paths: object) -> None:
        added = 0
        skipped = 0
        known_paths = {str(path) for path in self.view._video_paths}
        for raw_path in paths if isinstance(paths, (list, tuple)) else ():
            path = Path(raw_path).expanduser().resolve()
            key = str(path)
            if (
                not self.view.media_access.is_file(path)
                or path.suffix.lower() not in VIDEO_EXTENSIONS
                or key in known_paths
            ):
                skipped += 1
                continue
            self.view._video_paths.append(path)
            known_paths.add(key)
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, key)
            item.setToolTip(key)
            self.view.video_list.addItem(item)
            added += 1
        self._update_video_count()
        if added and self.view.video_list.currentRow() < 0:
            self.view.video_list.setCurrentRow(0)
        if added:
            self.view.run_log._append_console(f"[Videos] Added {added} video(s); {len(self.view._video_paths)} queued.")
        if skipped:
            self.view.run_log._append_console(f"[Videos] Skipped {skipped} unsupported or duplicate item(s).")

    def _remove_selected_videos(self) -> None:
        selected = self.view.video_list.selectedItems()
        if not selected:
            return
        self.view.hover._stop_hover_preview()
        removed_paths = {str(item.data(Qt.UserRole)) for item in selected}
        for item in selected:
            self.view.video_list.takeItem(self.view.video_list.row(item))
        self.view._video_paths = [path for path in self.view._video_paths if str(path) not in removed_paths]
        self._update_video_count()
        self.view.run_log._append_console(f"[Videos] Removed {len(removed_paths)} video(s).")

    def _clear_videos(self) -> None:
        if not self.view._video_paths:
            return
        self.view.hover._release_hover_capture()
        count = len(self.view._video_paths)
        self.view._video_paths.clear()
        self.view.video_list.clear()
        self.view.video_hover_card.hide()
        self._update_video_count()
        self.view.run_log._append_console(f"[Videos] Cleared {count} video(s).")

    def _update_video_count(self) -> None:
        count = len(self.view._video_paths)
        self.view.video_count_label.setText(f"{count} video" if count == 1 else f"{count} videos")
        self._sync_video_actions()
        self.view.video_list.viewport().update()

    def _sync_video_actions(self) -> None:
        has_videos = bool(self.view._video_paths)
        self.view.video_list.set_empty_action_visible(not has_videos)
        self.view.remove_videos_button.setEnabled(bool(self.view.video_list.selectedItems()))
        self.view.clear_videos_button.setEnabled(has_videos)


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
            "Add one or more source videos to the queue. Supported video files can also be dragged into this area; adding a video does not modify it."
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
            bounds.adjusted(24, action_bottom + 16, -24, -24), Qt.AlignHCenter | Qt.AlignTop, "Drop videos here"
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
            if path.suffix.lower() in VIDEO_EXTENSIONS:
                paths.append(path)
        return paths
