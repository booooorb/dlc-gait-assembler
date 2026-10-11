"""Assemble media, settings, drawing, results, and export controls for calibration."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import (
    CalibrationSettingsSnapshot,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_use_cases import calculate_calibration_report
from dlc_gait_assembly.runway.manual.calibration.client.calibration_canvas import CalibrationPreviewView
from dlc_gait_assembly.runway.manual.calibration.client.calibration_controller import CalibrationController
from dlc_gait_assembly.runway.manual.calibration.client.calibration_editor_state import CalibrationEditorState
from dlc_gait_assembly.runway.manual.calibration.client.calibration_media_panel import (
    CalibrationMediaPanel,
    build_calibration_media,
)
from dlc_gait_assembly.runway.manual.calibration.client.calibration_results_panel import build_calibration_results
from dlc_gait_assembly.runway.manual.calibration.client.calibration_settings_panel import build_calibration_settings
from dlc_gait_assembly.runway.manual.calibration.client.calibration_styles import CalibrationStyle, make_tool_button
from dlc_gait_assembly.shared.business.media_access_contracts import MediaAccessPort
from dlc_gait_assembly.shared.client.media_seek_slider import MediaSeekSlider
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip

try:
    import cv2
except ImportError:
    cv2 = None


class ManualCalibrationWidget(QWidget):
    def __init__(self, *, use_cases, media_access: MediaAccessPort, workspace):
        super().__init__()
        self.workspace = workspace
        self.state = CalibrationEditorState()
        self.media_access = media_access
        self.use_cases = use_cases
        self.controller = CalibrationController(self)
        self.media_panel = CalibrationMediaPanel(self)
        self.styling = CalibrationStyle(self)
        self.setObjectName("ManualCalibrationWidget")
        self._project_root = self.workspace.root
        self._capture = None
        self._frame_load_timer = QTimer(self)
        self._frame_load_timer.setSingleShot(True)
        self._frame_load_timer.setInterval(35)
        self._frame_load_timer.timeout.connect(self.media_panel._load_pending_frame)
        self._build_ui()
        self.controller._install_shortcuts()
        self.controller._connect_signals()
        self.styling._apply_style()
        self.controller._emphasize_calibration_tool("x")
        self.controller._update_calibration_results()

    def can_close(self, parent=None) -> bool:
        return True

    def release_resources(self) -> None:
        self.controller._save_media_state()
        self.media_panel._release_capture()
        self.state.duration_ms = 0
        self.state.fps = 0.0
        self.state.frame_count = 0
        if hasattr(self, "preview"):
            self.state.loading_media = True
            try:
                self.preview.set_frame(None)
            finally:
                self.state.loading_media = False

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter)
        left_panel = QWidget()
        left_panel.setObjectName("WorkspaceSidebar")
        left_panel.setMinimumWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)
        build_calibration_media(self, left_layout)
        build_calibration_results(self, left_layout)
        right_panel = QWidget()
        right_panel.setObjectName("WorkspaceCanvas")
        right_panel.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        self.preview_title = QLabel("Open a calibration image or video.")
        self.preview_title.setObjectName("PreviewTitle")
        right_layout.addWidget(self.preview_title)
        tools_bar = QFrame()
        tools_bar.setObjectName("OperationsBar")
        tools_layout = QHBoxLayout(tools_bar)
        tools_layout.setContentsMargins(12, 8, 12, 8)
        tools_layout.setSpacing(12)
        tool_buttons_row = QHBoxLayout()
        tool_buttons_row.setContentsMargins(0, 0, 0, 0)
        tool_buttons_row.setSpacing(8)
        self.x_tool_button = make_tool_button("X-calibration stick", theme.TOOL_3)
        set_tooltip(self.x_tool_button, "Draw an x-axis calibration stick.", "Ctrl+1")
        self.y_tool_button = make_tool_button("Y-calibration stick", theme.TOOL_2)
        set_tooltip(self.y_tool_button, "Draw a y-axis calibration stick.", "Ctrl+2")
        self.cm_tool_button = make_tool_button("Marker", theme.TOOL_1)
        set_tooltip(self.cm_tool_button, "Add calibration markers to a stick.", "Ctrl+3")
        self.x_tool_button.setChecked(True)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.x_tool_button)
        self.tool_group.addButton(self.y_tool_button)
        self.tool_group.addButton(self.cm_tool_button)
        tool_buttons_row.addWidget(self.x_tool_button)
        tool_buttons_row.addWidget(self.y_tool_button)
        tool_buttons_row.addWidget(self.cm_tool_button)
        (margin_row, settings_layout) = build_calibration_settings(self, tool_buttons_row, tools_layout)
        margin_row.addWidget(self.tau_spin)
        settings_layout.addLayout(margin_row)
        self.euclidean_lengths_checkbox = QCheckBox("Euclidean distance")
        self.euclidean_lengths_checkbox.setChecked(True)
        set_tooltip(
            self.euclidean_lengths_checkbox,
            "Measure each marker segment as the full distance between two points instead of only x/y axis distance.",
            "Ctrl+E",
        )
        settings_layout.addWidget(self.euclidean_lengths_checkbox)
        tools_layout.addWidget(self.settings_frame, 0, Qt.AlignTop)
        right_layout.addWidget(tools_bar)
        self.preview = CalibrationPreviewView()
        right_layout.addWidget(self.preview, 1)
        timeline_row = QHBoxLayout()
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(180)
        self.timeline = MediaSeekSlider()
        self.timeline.setRange(0, 0)
        self.timeline.setEnabled(False)
        timeline_row.addWidget(self.time_label)
        timeline_row.addWidget(self.timeline, 1)
        right_layout.addLayout(timeline_row)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 890])

    def profile_calibration_map_path(self) -> Path | None:
        """Return the conversion map most recently exported in this workspace."""
        return self.state.profile_calibration_map_path

    def settings_snapshot(self) -> CalibrationSettingsSnapshot | None:
        sticks = self.controller._all_calibration_sticks()
        report = calculate_calibration_report(
            sticks,
            self.tau_spin.value(),
            self.euclidean_lengths_checkbox.isChecked(),
            self.marker_interval_spin.value(),
            self.marker_unit_combo.currentText(),
        )
        return CalibrationSettingsSnapshot(tuple(sticks), report) if report.view_axis else None

    def _default_output_root(self) -> Path:
        output_root = self.workspace.manual / "calibration"
        return output_root

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()
