"""Present source videos and their processing status."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.manual.video_processing.client.video_operation_settings_panel import (
    VideoOperationSettingsPanel,
)
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar


class VideoSourceList:
    """VideoSourceList operates on its explicitly supplied VideoEditorWidget view."""

    def __init__(self, view):
        self.view = view

    def _add_videos(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        (filenames, _) = QFileDialog.getOpenFileNames(
            self.view, "Add video files", str(self.view._project_root), f"Video files ({extensions});;All files (*)"
        )
        if not filenames:
            return
        self._add_video_paths(Path(filename) for filename in filenames)

    def _add_video_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self.view, "Add a folder of videos", str(self.view._project_root))
        if not directory:
            return
        folder = Path(directory).expanduser().resolve()
        video_paths = [
            path
            for path in self.view.media_access.files_in_directory(folder)
            if path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not video_paths:
            QMessageBox.information(
                self.view, "No videos found", "That folder does not contain any supported video files."
            )
            return
        existing = {self.view.video_list.item(index).data(Qt.UserRole) for index in range(self.view.video_list.count())}
        new_paths = [path for path in video_paths if str(path) not in existing]
        if not new_paths:
            QMessageBox.information(
                self.view, "No new videos", "All supported videos in that folder are already uploaded."
            )
            return
        duplicate_count = len(video_paths) - len(new_paths)
        details = f"Folder:\n{folder}"
        if duplicate_count:
            details += f"\n\n{duplicate_count} supported video(s) are already in the uploaded list."
        if not self.view.controller._confirm_action(
            "Add folder of videos?", f"Add {len(new_paths)} video(s) from this folder?", details
        ):
            return
        self._add_video_paths(new_paths)

    def _add_video_paths(self, paths) -> None:
        existing = {self.view.video_list.item(index).data(Qt.UserRole) for index in range(self.view.video_list.count())}
        added = 0
        skipped = 0
        self.view.video_list.setUpdatesEnabled(False)
        try:
            for candidate in paths:
                path = Path(candidate).expanduser().resolve()
                if path.suffix.lower() not in VIDEO_EXTENSIONS:
                    skipped += 1
                    continue
                if str(path) in existing:
                    continue
                item = QListWidgetItem(path.name)
                item.setToolTip(str(path))
                item.setData(Qt.UserRole, str(path))
                self.view.video_list.addItem(item)
                existing.add(str(path))
                added += 1
        finally:
            self.view.video_list.setUpdatesEnabled(True)
        if added and self.view.video_list.currentRow() < 0:
            self.view.video_list.setCurrentRow(0)
        if skipped:
            QMessageBox.information(self.view, "Unsupported files skipped", f"Skipped {skipped} unsupported file(s).")
        self._refresh_video_paths_context()
        self.view.controller._update_process_state()

    def _remove_selected_videos(self) -> None:
        self.view.video_list.setUpdatesEnabled(False)
        try:
            for item in self.view.video_list.selectedItems():
                path_key = item.data(Qt.UserRole)
                self.view.state.trim_ranges_by_video.pop(path_key, None)
                self.view.state.active_trim_range_by_video.pop(path_key, None)
                self.view.video_list.takeItem(self.view.video_list.row(item))
        finally:
            self.view.video_list.setUpdatesEnabled(True)
        if self.view.video_list.count() == 0:
            self.view.playback._release_capture()
            self.view.preview.set_frame(None)
            self.view.preview_title.setText("Select a video from the uploaded list.")
            self.view.timeline.setRange(0, 0)
            self.view.trims._refresh_trim_context()
            self.view.time_label.setText("00:00.000 / 00:00.000")
        self._refresh_video_paths_context()
        self.view.controller._update_process_state()

    def _clear_videos(self) -> None:
        if self.view.video_list.count() > 0 and (
            not self.view.controller._confirm_action(
                "Clear uploaded videos?",
                f"Remove all {self.view.video_list.count()} uploaded video(s) from the list?",
                "This does not delete files from your computer.",
            )
        ):
            return
        self.view.video_list.clear()
        self.view.state.trim_ranges_by_video.clear()
        self.view.state.active_trim_range_by_video.clear()
        self.view.playback._release_capture()
        self.view.preview.set_frame(None)
        self.view.preview_title.setText("Select a video from the uploaded list.")
        self.view.timeline.setRange(0, 0)
        self.view.trims._refresh_trim_context()
        self.view.time_label.setText("00:00.000 / 00:00.000")
        self._refresh_video_paths_context()
        self.view.controller._update_process_state()

    def _video_paths(self) -> list[Path]:
        return [
            Path(self.view.video_list.item(index).data(Qt.UserRole)) for index in range(self.view.video_list.count())
        ]

    def _select_video_by_path(self, path_text: str) -> None:
        for index in range(self.view.video_list.count()):
            item = self.view.video_list.item(index)
            if item.data(Qt.UserRole) == path_text:
                if self.view.video_list.currentRow() == index:
                    if self.view.state.current_video is None or str(self.view.state.current_video) != path_text:
                        self.view.playback._load_selected_video(item)
                else:
                    self.view.video_list.setCurrentRow(index)
                return

    def _refresh_video_paths_context(self) -> None:
        videos = self._video_paths()
        self.view.preview.set_available_video_paths(videos)
        self.view.settings_panel.set_video_paths(videos)


def build_video_sources(self, left_layout):
    videos_box = QGroupBox("Uploaded videos")
    videos_box.setMinimumHeight(190)
    videos_layout = QVBoxLayout(videos_box)
    videos_layout.setSpacing(8)
    button_row = QHBoxLayout()
    self.add_videos_button = QPushButton("Add files")
    self.add_videos_button.setObjectName("AddFilesButton")
    set_tooltip(self.add_videos_button, "Add video files to the processing list.", "Ctrl+O")
    self.add_folder_button = QPushButton("Add folder")
    self.add_folder_button.setObjectName("AddFolderButton")
    set_tooltip(self.add_folder_button, "Add every supported video in a folder.", "Ctrl+Shift+O")
    self.remove_videos_button = QPushButton("Remove")
    self.remove_videos_button.setObjectName("RemoveButton")
    set_tooltip(self.remove_videos_button, "Remove selected videos from the list.", "Ctrl+Backspace")
    self.clear_videos_button = QPushButton("Clear")
    self.clear_videos_button.setObjectName("ClearButton")
    set_tooltip(self.clear_videos_button, "Clear the uploaded video list.", "Ctrl+L")
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
    self.video_list.setAlternatingRowColors(False)
    self.video_list.setSpacing(0)
    list_font = self.video_list.font()
    list_font.setPointSize(9)
    self.video_list.setFont(list_font)
    videos_layout.addWidget(self.video_list, 1)
    left_layout.addWidget(videos_box, 4)
    self.settings_panel = VideoOperationSettingsPanel(self.preview)
    left_layout.addWidget(self.settings_panel, 6)
    manifest_row = QHBoxLayout()
    self.import_video_manifest_button = QPushButton("Upload settings manifest")
    self.import_video_manifest_button.setObjectName("ImportVideoManifestButton")
    set_tooltip(
        self.import_video_manifest_button,
        "Apply crop, enhancement, inversion, and matching trim settings from a video settings manifest.",
    )
    self.export_video_manifest_button = QPushButton("Export settings manifest")
    self.export_video_manifest_button.setObjectName("ExportVideoManifestButton")
    set_tooltip(
        self.export_video_manifest_button, "Export the current video settings without processing source videos."
    )
    manifest_row.addWidget(self.import_video_manifest_button)
    manifest_row.addWidget(self.export_video_manifest_button)
    left_layout.addLayout(manifest_row)
    self.process_button = QPushButton("Process files")
    self.process_button.setObjectName("PrimaryButton")
    set_tooltip(self.process_button, "Process the uploaded videos with the selected operations.", "Ctrl+R")
    left_layout.addWidget(self.process_button)
    self.progress = DynamicProgressBar(accent_role="tool_2")
    self.progress.setRange(0, 1)
    self.progress.setValue(0)
    self.progress.setFormat("")
    left_layout.addWidget(self.progress)
