"""Assemble artifact previews, checkpoint descriptions, and review decision controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_stickplot_panel import (
    DoubleClickLabel,
)
from dlc_gait_assembly.shared.client.qt_sliding_tabs import install_sliding_tab_bar


def build_automatic_review_view(self, layout):
    self.pipeline_review_panel = QFrame()
    self.pipeline_review_panel.setObjectName("PipelineReviewPanel")
    review_layout = QHBoxLayout(self.pipeline_review_panel)
    self.pipeline_review_layout = review_layout
    review_layout.setContentsMargins(6, 6, 6, 6)
    review_layout.setSpacing(6)
    self.pipeline_review_preview_stack = QStackedWidget()
    self.pipeline_review_preview_stack.setObjectName("PipelineReviewPreviewStack")
    self.pipeline_review_preview_stack.setMinimumSize(240, 78)
    self.pipeline_review_video_list = QListWidget()
    self.pipeline_review_video_list.setObjectName("PipelineReviewVideoList")
    self.pipeline_review_video_list.setToolTip(
        "Review the generated preview for each queued video. Double-click a row to open a larger viewer before accepting or rejecting this checkpoint."
    )
    self.pipeline_review_video_list.setWordWrap(False)
    self.pipeline_review_video_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.pipeline_review_preview_stack.addWidget(self.pipeline_review_video_list)
    self.pipeline_component_tabs = QTabWidget()
    install_sliding_tab_bar(self.pipeline_component_tabs, theme.TOOL_1)
    self.pipeline_component_tabs.setObjectName("PipelineComponentTabs")
    self.pipeline_component_tabs.setDocumentMode(True)
    self.pipeline_component_tabs.tabBar().setExpanding(True)
    self.pipeline_component_tabs.setToolTip(
        "Switch between region outputs to verify that each one used the correct model."
    )
    self.pipeline_review_preview_stack.addWidget(self.pipeline_component_tabs)
    self.pipeline_component_video_lists: dict[str, QListWidget] = {}
    self.pipeline_stickplot_preview = DoubleClickLabel()
    self.pipeline_stickplot_preview.setObjectName("PipelineStickplotPreview")
    self.pipeline_stickplot_preview.setAlignment(Qt.AlignCenter)
    self.pipeline_stickplot_preview.setCursor(Qt.PointingHandCursor)
    self.pipeline_stickplot_preview.setToolTip("Click to open the full-size stickplot preview.")
    self.pipeline_review_preview_stack.addWidget(self.pipeline_stickplot_preview)
    review_layout.addWidget(self.pipeline_review_preview_stack, 1)
    review_copy = QVBoxLayout()
    self.pipeline_review_title = QLabel()
    self.pipeline_review_title.setObjectName("PipelineReviewTitle")
    review_copy.addWidget(self.pipeline_review_title)
    self.pipeline_review_description = QLabel()
    self.pipeline_review_description.setObjectName("PipelineReviewDescription")
    self.pipeline_review_description.setWordWrap(True)
    review_copy.addWidget(self.pipeline_review_description)
    review_copy.addStretch(1)
    review_buttons = QHBoxLayout()
    self.pipeline_change_settings_button = QPushButton("Change configuration")
    self.pipeline_change_settings_button.setObjectName("PipelineChangeSettingsButton")
    self.pipeline_change_settings_button.setToolTip(
        "Open the profile setting responsible for this rejected preview. After fixing it, return here and resume the walkthrough."
    )
    self.pipeline_needs_changes_button = QPushButton("Needs changes")
    self.pipeline_needs_changes_button.setObjectName("RemoveButton")
    self.pipeline_needs_changes_button.setToolTip(
        "Reject this checkpoint and pause the pipeline so its profile settings can be corrected."
    )
    self.pipeline_approve_button = QPushButton("Confirm and continue")
    self.pipeline_approve_button.setObjectName("PrimaryButton")
    self.pipeline_approve_button.setToolTip("Accept this preview as correct and continue to the next pipeline stage.")
    review_buttons.addWidget(self.pipeline_change_settings_button)
    review_buttons.addStretch(1)
    review_buttons.addWidget(self.pipeline_needs_changes_button)
    review_buttons.addWidget(self.pipeline_approve_button)
    review_copy.addLayout(review_buttons)
    review_layout.addLayout(review_copy, 2)
    self.pipeline_review_panel.hide()
    layout.addWidget(self.pipeline_review_panel, 1)
