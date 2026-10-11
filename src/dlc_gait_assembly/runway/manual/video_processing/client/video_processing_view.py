"""Assemble source videos, the region canvas, operation controls, and export status."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import VideoSettingsSnapshot
from dlc_gait_assembly.runway.manual.video_processing.client.video_editor_controller import VideoEditorController
from dlc_gait_assembly.runway.manual.video_processing.client.video_editor_state import VideoEditorState
from dlc_gait_assembly.runway.manual.video_processing.client.video_export_worker import VideoProcessingThread
from dlc_gait_assembly.runway.manual.video_processing.client.video_playback_controller import VideoPlaybackController
from dlc_gait_assembly.runway.manual.video_processing.client.video_processing_styles import (
    VideoProcessingStyle,
    make_tool_button,
)
from dlc_gait_assembly.runway.manual.video_processing.client.video_region_canvas import RegionPreviewView
from dlc_gait_assembly.runway.manual.video_processing.client.video_source_list import (
    VideoSourceList,
    build_video_sources,
)
from dlc_gait_assembly.runway.manual.video_processing.client.video_trim_controls import VideoTrimControls
from dlc_gait_assembly.runway.manual.video_processing.client.video_trim_timeline import TrimTimelineSlider
from dlc_gait_assembly.shared.business.media_access_contracts import MediaAccessPort
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip

try:
    import cv2
except ImportError:
    cv2 = None


class VideoEditorWidget(QWidget):
    def __init__(self, *, use_cases, media_access: MediaAccessPort, workspace):
        super().__init__()
        self.workspace = workspace
        self.state = VideoEditorState()
        self.media_access = media_access
        self.use_cases = use_cases
        self.controller = VideoEditorController(self)
        self.sources = VideoSourceList(self)
        self.playback = VideoPlaybackController(self)
        self.trims = VideoTrimControls(self)
        self.styling = VideoProcessingStyle(self)
        self.setObjectName("VideoEditorWidget")
        self._capture = None
        self._frame_load_timer = QTimer(self)
        self._frame_load_timer.setSingleShot(True)
        self._frame_load_timer.setInterval(85)
        self._frame_load_timer.timeout.connect(self.playback._load_pending_frame)
        self._trim_context_refresh_timer = QTimer(self)
        self._trim_context_refresh_timer.setSingleShot(True)
        self._trim_context_refresh_timer.setInterval(85)
        self._trim_context_refresh_timer.timeout.connect(self.trims._refresh_trim_context)
        self._processing_thread: VideoProcessingThread | None = None
        self._project_root = self.workspace.root
        self._build_ui()
        self.controller._install_shortcuts()
        self.controller._connect_signals()
        self.styling._apply_style()
        self.controller._emphasize_operation_tool("crop")
        self.controller._update_process_state()

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
        self.playback._release_capture()
        self.state.duration_ms = 0
        if hasattr(self, "preview"):
            self.preview.set_frame(None)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.preview.reactivate)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)
        self.preview = RegionPreviewView()
        left_panel = QWidget()
        left_panel.setObjectName("WorkspaceSidebar")
        left_panel.setMinimumWidth(420)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)
        build_video_sources(self, left_layout)
        right_panel = QWidget()
        right_panel.setObjectName("WorkspaceCanvas")
        right_panel.setMinimumWidth(390)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        self.preview_title = QLabel("Select a video from the uploaded list.")
        self.preview_title.setObjectName("PreviewTitle")
        right_layout.addWidget(self.preview_title)
        operations_bar = QFrame()
        operations_bar.setObjectName("OperationsBar")
        operations_layout = QVBoxLayout(operations_bar)
        operations_layout.setContentsMargins(12, 8, 12, 8)
        operations_layout.setSpacing(8)
        tool_row = QHBoxLayout()
        tool_row.setSpacing(8)
        tool_row.addWidget(QLabel("Operations"))
        self.crop_tool_button = make_tool_button("Regions", theme.TOOL_3)
        self.enhancements_tool_button = make_tool_button("Enhancements", theme.TOOL_2)
        self.trim_tool_button = make_tool_button("Trim", theme.TOOL_1)
        set_tooltip(self.crop_tool_button, "Create or edit crop regions.", "Ctrl+1")
        set_tooltip(self.enhancements_tool_button, "Adjust preview and export enhancement settings.", "Ctrl+2")
        set_tooltip(self.trim_tool_button, "Create or edit trim ranges.", "Ctrl+3")
        self.crop_tool_button.setChecked(True)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.crop_tool_button)
        self.tool_group.addButton(self.enhancements_tool_button)
        self.tool_group.addButton(self.trim_tool_button)
        tool_row.addWidget(self.crop_tool_button)
        tool_row.addWidget(self.enhancements_tool_button)
        tool_row.addWidget(self.trim_tool_button)
        tool_row.addStretch(1)
        quality_separator = QFrame()
        quality_separator.setFrameShape(QFrame.VLine)
        quality_separator.setFrameShadow(QFrame.Plain)
        tool_row.addWidget(quality_separator)
        self.export_quality_controls = QWidget()
        self.export_quality_controls.setObjectName("ExportQualityControls")
        quality_layout = QHBoxLayout(self.export_quality_controls)
        quality_layout.setContentsMargins(2, 0, 0, 0)
        quality_layout.setSpacing(6)
        quality_layout.addWidget(QLabel("Export quality"))
        quality_layout.addWidget(QLabel("CRF"))
        self.crf_spin = QSpinBox()
        self.crf_spin.setObjectName("VideoCrfSpin")
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(18)
        self.crf_spin.setFixedWidth(62)
        self.crf_spin.setToolTip("Constant Rate Factor: lower values preserve more detail and create larger files.")
        quality_layout.addWidget(self.crf_spin)
        quality_layout.addWidget(QLabel("Preset"))
        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("VideoPresetCombo")
        self.preset_combo.addItems(
            ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        )
        self.preset_combo.setCurrentText("slow")
        self.preset_combo.setMinimumWidth(96)
        self.preset_combo.setMaximumWidth(120)
        self.preset_combo.setToolTip("Encoding speed preset: slower presets take longer but generally compress better.")
        quality_layout.addWidget(self.preset_combo)
        tool_row.addWidget(self.export_quality_controls)
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
        self.workspace_splitter = splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 760])

    def profile_manifest_path(self) -> Path | None:
        """Return the manifest most recently imported or exported in this workspace."""
        return self.state.profile_manifest_path

    def settings_snapshot(self) -> VideoSettingsSnapshot:
        return VideoSettingsSnapshot(
            self.controller._current_processing_options(), self.trims._trim_ranges_for_manifest()
        )

    def _default_output_root(self) -> Path:
        return self.workspace.manual / "video_processing"

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()


VideoProcessingWindow = VideoEditorWidget
