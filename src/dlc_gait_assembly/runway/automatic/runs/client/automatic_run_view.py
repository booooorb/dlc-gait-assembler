"""Assemble the automatic video queue, progress, execution controls, and run log."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.automatic.runs.client.automatic_video_queue import VideoDropList
from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    fixed_width_font as _dependency_theme_fixed_width_font,
)


def build_automatic_run_workspace(self, automation_content, automation_layout):
    video_panel = QFrame()
    video_panel.setObjectName("VideoDropPanel")
    video_layout = QVBoxLayout(video_panel)
    video_layout.setContentsMargins(14, 12, 14, 14)
    video_layout.setSpacing(10)
    video_toolbar = QHBoxLayout()
    video_toolbar.setSpacing(8)
    videos_title = QLabel("Videos")
    videos_title.setObjectName("AutomationPanelTitle")
    video_toolbar.addWidget(videos_title)
    self.video_count_label = QLabel("0 videos")
    self.video_count_label.setObjectName("VideoCountLabel")
    video_toolbar.addWidget(self.video_count_label)
    video_toolbar.addStretch(1)
    self.remove_videos_button = QPushButton("Remove")
    self.remove_videos_button.setObjectName("RemoveButton")
    self.remove_videos_button.setEnabled(False)
    self.remove_videos_button.setToolTip("Remove the selected videos from this queue. Files on disk are not deleted.")
    video_toolbar.addWidget(self.remove_videos_button)
    self.clear_videos_button = QPushButton("Clear")
    self.clear_videos_button.setObjectName("ClearButton")
    self.clear_videos_button.setEnabled(False)
    self.clear_videos_button.setToolTip("Remove every video from this queue. Files on disk are not deleted.")
    video_toolbar.addWidget(self.clear_videos_button)
    video_layout.addLayout(video_toolbar)
    self.video_list = VideoDropList()
    self.video_list.setObjectName("AutomationVideoDropList")
    self.upload_videos_button = self.video_list.add_videos_button
    self.video_list.setAccessibleDescription(
        "Drop source videos here or choose Add videos. Hover over a queued video to play a preview, or double-click to open the expanded preview."
    )
    self.video_list.setToolTip(
        "Queued source videos. Hover over a row for a quick preview, double-click it for a larger viewer, or select rows before choosing Remove."
    )
    self.video_list.setSelectionMode(QListWidget.ExtendedSelection)
    self.video_list.setMinimumHeight(280)
    video_layout.addWidget(self.video_list, 1)
    self.video_hover_card = QFrame(self.video_list.viewport())
    self.video_hover_card.setObjectName("VideoHoverCard")
    self.video_hover_card.setAttribute(Qt.WA_TransparentForMouseEvents)
    self.video_hover_card.setFixedSize(276, 206)
    hover_layout = QVBoxLayout(self.video_hover_card)
    hover_layout.setContentsMargins(8, 8, 8, 8)
    hover_layout.setSpacing(5)
    self.video_hover_preview = QLabel("Loading preview…")
    self.video_hover_preview.setObjectName("VideoHoverPreview")
    self.video_hover_preview.setAlignment(Qt.AlignCenter)
    self.video_hover_preview.setFixedSize(258, 145)
    hover_layout.addWidget(self.video_hover_preview)
    self.video_hover_name = QLabel()
    self.video_hover_name.setObjectName("VideoHoverName")
    hover_layout.addWidget(self.video_hover_name)
    self.video_hover_details = QLabel("Double-click for expanded preview")
    self.video_hover_details.setObjectName("VideoHoverDetails")
    hover_layout.addWidget(self.video_hover_details)
    self.video_hover_card.hide()
    self.video_panel = video_panel
    self.pipeline_status_panel = self._build_pipeline_status_panel()
    self.automation_input_stack = QStackedWidget()
    self.automation_input_stack.setObjectName("AutomationInputStack")
    self.automation_input_stack.addWidget(self.video_panel)
    self.automation_input_stack.addWidget(self.pipeline_status_panel)
    self.automation_input_stack.setCurrentWidget(self.video_panel)
    automation_content.addWidget(self.automation_input_stack, 3)
    console_panel = QFrame()
    console_panel.setObjectName("AutomationConsolePanel")
    console_layout = QVBoxLayout(console_panel)
    console_layout.setContentsMargins(14, 12, 14, 14)
    console_layout.setSpacing(10)
    console_header = QHBoxLayout()
    console_header.setSpacing(8)
    console_title = QLabel("Activity")
    console_title.setObjectName("AutomationPanelTitle")
    console_header.addWidget(console_title)
    console_header.addStretch(1)
    self.pipeline_log_state = QLabel("●  Ready")
    self.pipeline_log_state.setObjectName("PipelineLogState")
    self.pipeline_log_state.setProperty("logState", "ready")
    console_header.addWidget(self.pipeline_log_state)
    console_layout.addLayout(console_header)
    self.automation_console = QPlainTextEdit()
    self.automation_console.setObjectName("AutomationConsole")
    self.automation_console.setReadOnly(True)
    self.automation_console.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    self.automation_console.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.automation_console.setFont(_dependency_theme_fixed_width_font())
    self.automation_console.setToolTip(
        "Read-only activity log for the current automation preview, including stage progress, review pauses, and errors."
    )
    self.automation_console.setPlainText("[Ready]")
    console_layout.addWidget(self.automation_console, 1)
    automation_content.addWidget(console_panel, 2)
    self.automation_console_panel = console_panel
    self._automation_input_default_minimum_height = self.automation_input_stack.minimumHeight()
    self._automation_input_default_maximum_height = self.automation_input_stack.maximumHeight()
    self._automation_console_default_minimum_height = console_panel.minimumHeight()
    self._automation_console_default_maximum_height = console_panel.maximumHeight()
    automation_layout.addLayout(automation_content, 1)
