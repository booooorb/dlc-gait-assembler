"""Assemble independent Ladder inputs, detection settings, event review, and export controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget

from dlc_gait_assembly.ladder.client.ladder_analysis_controller import LadderAnalysisController
from dlc_gait_assembly.ladder.client.ladder_analysis_styles import LadderAnalysisStyle
from dlc_gait_assembly.ladder.client.ladder_detection_settings import build_ladder_settings
from dlc_gait_assembly.ladder.client.ladder_detection_worker import DualLadderAnalysisThread, LadderAnalysisThread
from dlc_gait_assembly.ladder.client.ladder_editor_state import LadderEditorState
from dlc_gait_assembly.ladder.client.ladder_event_review_table import LadderEventReviewTable, build_ladder_events
from dlc_gait_assembly.ladder.client.ladder_input_panel import LadderInputPanel, build_ladder_inputs
from dlc_gait_assembly.ladder.client.ladder_video_review import LadderVideoReview, build_ladder_video
from dlc_gait_assembly.shared.business.media_access_contracts import MediaAccessPort
from dlc_gait_assembly.shared.client.qt_input_behaviors import install_wheel_value_guard


class LadderAnalysisWidget(QWidget):
    back_requested = Signal()

    def __init__(self, *, use_cases, media_access: MediaAccessPort, workspace):
        super().__init__()
        self.workspace = workspace
        self.state = LadderEditorState()
        self.media_access = media_access
        self.use_cases = use_cases
        self.controller = LadderAnalysisController(self)
        self.inputs = LadderInputPanel(self)
        self.review = LadderEventReviewTable(self)
        self.video_review = LadderVideoReview(self)
        self.styling = LadderAnalysisStyle(self)
        self.setObjectName("LadderAnalysisWidget")
        self._project_root = self.workspace.root
        self._defaults = self.use_cases.defaults
        self._worker: LadderAnalysisThread | DualLadderAnalysisThread | None = None
        self._video_capture = None
        self._right_video_capture = None
        self._build_ui()
        self.controller._connect_signals()
        self._wheel_guard = install_wheel_value_guard(self)
        self.styling._apply_style()
        self.controller._update_mode()
        self.controller._update_method_controls()
        self.controller._update_run_state()

    def can_close(self, parent=None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                parent or self,
                "Ladder analysis is running",
                "Wait for the current ALMA ladder analysis to finish before closing this window.",
            )
            return False
        return True

    def release_resources(self) -> None:
        for attribute in ("_video_capture", "_right_video_capture"):
            capture = getattr(self, attribute)
            if capture is not None:
                capture.release()
                setattr(self, attribute, None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        title = QLabel("ALMA ladder-rung analysis")
        title.setObjectName("TitleLabel")
        title_row = QHBoxLayout()
        self.back_to_gait_button = QPushButton("← Gait analysis")
        self.back_to_gait_button.clicked.connect(self.back_requested.emit)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.back_to_gait_button)
        subtitle = QLabel(
            "Detect paw placements from DeepLabCut coordinates, review them against the video, and classify slips or falls before export."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        root.addLayout(title_row)
        root.addWidget(subtitle)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)
        controls = QWidget()
        controls.setObjectName("WorkspaceSidebar")
        controls.setMinimumWidth(390)
        controls.setMaximumWidth(500)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 12, 0)
        controls_layout.setSpacing(12)
        build_ladder_inputs(self, controls_layout)
        build_ladder_settings(self, controls_layout)
        review = QWidget()
        review.setObjectName("WorkspaceCanvas")
        review_layout = QVBoxLayout(review)
        review_layout.setContentsMargins(12, 0, 0, 0)
        review_layout.setSpacing(12)
        build_ladder_video(self, review_layout)
        controls_scroll = build_ladder_events(self, review_layout)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_scroll.setMinimumWidth(410)
        controls_scroll.setMaximumWidth(520)
        controls_scroll.setWidget(controls)
        splitter.addWidget(controls_scroll)
        splitter.addWidget(review)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _default_output_folder(self) -> Path:
        path = self.workspace.ladder_analyses
        return path

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()
