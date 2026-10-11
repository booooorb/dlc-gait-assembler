"""Pause run presentation for artifact review and connect approval or rejection actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import StageReview
from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import (
    PIPELINE_REVIEW_GATES,
    PIPELINE_STAGES,
    STOP_PREVIEW_TOOLTIP,
)


class AutomaticReviewController:
    """AutomaticReviewController operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _pause_for_pipeline_review(self, stage_index: int, artifacts: StageReview | None = None) -> None:
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self.view._pipeline_demo_timer.stop()
        self.view._pipeline_demo_waiting_for_review = stage_index
        self.view.stage_progress._set_pipeline_overview_compact(True)
        self.view.pipeline_review_title.setText(str(gate["title"]))
        self.view.pipeline_review_description.setText(str(gate["description"]))
        self._populate_pipeline_review_preview(stage_index, artifacts)
        self.view.pipeline_change_settings_button.hide()
        self.view.pipeline_needs_changes_button.show()
        self.view.pipeline_approve_button.show()
        self.view.pipeline_activity_panel.hide()
        self.view.pipeline_review_panel.show()
        self.view.run_log._set_pipeline_log_state("Review", "review")
        self.view.pipeline_stage_status_labels[stage_index].setText("Awaiting confirmation")
        self.view.pipeline_stage_review_labels[stage_index].setText("Awaiting review")
        self.view.pipeline_progress_bar.set_active(False)
        self.view.stage_progress._set_pipeline_stage_progress(
            stage_index, 100, False, "ready", indicator_state="active"
        )
        self.view.run_pipeline_button.setText("Awaiting confirmation")
        self.view.run_pipeline_button.setEnabled(False)
        self.view.run_pipeline_button.setToolTip(
            "The walkthrough is paused. Use Confirm and continue or Needs changes in the review panel."
        )
        self.view.runs._set_run_readiness("Review required", "review")
        self.view.run_log._append_console(f"[Manual check] {gate['title']}. Pipeline paused.")

    def _populate_pipeline_review_preview(self, stage_index: int, artifacts: StageReview | None = None) -> None:
        if stage_index == 4:
            self.view.pipeline_review_layout.setStretch(0, 2)
            self.view.pipeline_review_layout.setStretch(1, 1)
        else:
            self.view.pipeline_review_layout.setStretch(0, 1)
            self.view.pipeline_review_layout.setStretch(1, 2)
        if artifacts is not None:
            self._populate_real_pipeline_review_preview(stage_index, artifacts)
            return
        if stage_index == 4:
            self.view._pipeline_stickplot_path = self.view.review_artifacts.reference_stickplot()
            self.view.pipeline_stickplot_preview.setText("")
            loaded = self.view.pipeline_stickplot_preview.load_image_data(
                self.view.review_artifacts.image_bytes(self.view._pipeline_stickplot_path),
                self.view._pipeline_stickplot_path.suffix,
            )
            if not loaded:
                self.view.pipeline_stickplot_preview.setPixmap(QPixmap())
                self.view.pipeline_stickplot_preview.setText("The real ALMA reference stickplot is unavailable.")
            self.view._pipeline_stickplot_pixmap = self.view.pipeline_stickplot_preview.pixmap()
            self.view.pipeline_stickplot_preview.setToolTip(
                "Actual ALMA stickplot generated from the bundled reference DLC coordinate dataset. Click it to open a larger viewer."
            )
            self.view.pipeline_review_preview_stack.setCurrentWidget(self.view.pipeline_stickplot_preview)
            return
        self.view.pipeline_review_video_list.clear()
        component_names = self.view.profile_state.regions or ("Full frame",)
        regions = ", ".join(component_names)
        enhancements = self._processing_enhancement_summary()
        preview_paths: list[Path | None] = list(self.view._video_paths)
        if not preview_paths:
            preview_paths = [None] * self.view._pipeline_demo_total_videos
        if stage_index == 0:
            for index, path in enumerate(preview_paths, start=1):
                source_name = path.name if path is not None else f"Demo video {index}.mp4"
                display_name = source_name
                details = f"Regions: {regions}  •  Enhancements: {enhancements}"
                item = QListWidgetItem(f"{display_name}  —  {details}")
                item.setData(Qt.UserRole, str(path) if path is not None else "")
                item.setData(Qt.UserRole + 1, details)
                item.setData(Qt.UserRole + 2, display_name)
                item.setData(Qt.UserRole + 4, "All regions")
                item.setToolTip(
                    "Inspect this processed output for the expected crop regions and enhancements. Double-click to open a larger preview."
                )
                self.view.pipeline_review_video_list.addItem(item)
        else:
            self.view.pipeline_component_video_lists.clear()
            while self.view.pipeline_component_tabs.count():
                page = self.view.pipeline_component_tabs.widget(0)
                self.view.pipeline_component_tabs.removeTab(0)
                page.deleteLater()
            for component in component_names:
                model_source = self.view.profile_state.model_sources.get(component)
                model_name = model_source.name if model_source is not None else "configured model"
                component_list = QListWidget()
                component_list.setObjectName("PipelineReviewVideoList")
                component_list.setWordWrap(False)
                component_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                component_list.itemDoubleClicked.connect(self.view.review_video._open_pipeline_review_video)
                self.view.pipeline_component_tabs.addTab(component_list, component)
                self.view.pipeline_component_tabs.setTabToolTip(
                    self.view.pipeline_component_tabs.count() - 1, f"{component} component • {model_name}"
                )
                self.view.pipeline_component_video_lists[component] = component_list
                component_slug = component.replace(" ", "_")
                for index, path in enumerate(preview_paths, start=1):
                    source_name = path.name if path is not None else f"Demo video {index}.mp4"
                    display_name = f"{Path(source_name).stem}_{component_slug}_DLC.mp4"
                    details = f"Component: {component}  •  Model: {model_name}"
                    item = QListWidgetItem(f"{display_name}  —  {details}")
                    item.setData(Qt.UserRole, str(path) if path is not None else "")
                    item.setData(Qt.UserRole + 1, details)
                    item.setData(Qt.UserRole + 2, display_name)
                    item.setData(Qt.UserRole + 4, component)
                    item.setToolTip(
                        f"Inspect the {component} tracking overlay produced with {model_name}. Double-click to open a larger preview."
                    )
                    component_list.addItem(item)
            self.view.pipeline_review_preview_stack.setCurrentWidget(self.view.pipeline_component_tabs)
            return
        self.view.pipeline_review_preview_stack.setCurrentWidget(self.view.pipeline_review_video_list)

    def _populate_real_pipeline_review_preview(self, stage_index: int, artifacts: StageReview) -> None:
        items = artifacts.items
        if stage_index == 4:
            image_paths = [item.path for item in items if self.view.review_artifacts.exists(item.path)]
            self.view._pipeline_stickplot_path = image_paths[0] if image_paths else None
            self.view.pipeline_stickplot_preview.setText("")
            loaded = (
                self.view.pipeline_stickplot_preview.load_image_data(
                    self.view.review_artifacts.image_bytes(self.view._pipeline_stickplot_path),
                    self.view._pipeline_stickplot_path.suffix,
                )
                if self.view._pipeline_stickplot_path is not None
                else False
            )
            if not loaded:
                self.view.pipeline_stickplot_preview.setPixmap(QPixmap())
                self.view.pipeline_stickplot_preview.setText("No stickplot image was produced")
            self.view._pipeline_stickplot_pixmap = self.view.pipeline_stickplot_preview.pixmap()
            self.view.pipeline_review_preview_stack.setCurrentWidget(self.view.pipeline_stickplot_preview)
            return
        if stage_index == 0:
            self.view.pipeline_review_video_list.clear()
            for artifact in items:
                self.view.review_video._add_real_review_video_item(self.view.pipeline_review_video_list, artifact)
            self.view.pipeline_review_preview_stack.setCurrentWidget(self.view.pipeline_review_video_list)
            return
        self.view.pipeline_component_video_lists.clear()
        while self.view.pipeline_component_tabs.count():
            page = self.view.pipeline_component_tabs.widget(0)
            self.view.pipeline_component_tabs.removeTab(0)
            page.deleteLater()
        views = []
        for artifact in items:
            view = artifact.view or "Full frame"
            if view not in views:
                views.append(view)
        for view in views:
            component_list = QListWidget()
            component_list.setObjectName("PipelineReviewVideoList")
            component_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            component_list.itemDoubleClicked.connect(self.view.review_video._open_pipeline_review_video)
            self.view.pipeline_component_tabs.addTab(component_list, view)
            self.view.pipeline_component_video_lists[view] = component_list
            for artifact in items:
                if (artifact.view or "Full frame") == view:
                    self.view.review_video._add_real_review_video_item(component_list, artifact)
        self.view.pipeline_review_preview_stack.setCurrentWidget(self.view.pipeline_component_tabs)

    def _processing_enhancement_summary(self) -> str:
        if self.view.profile_state.manifest_source is None:
            return "manifest settings"
        enhancements = self.view.review_artifacts.processing_enhancements(self.view.profile_state.manifest_source)
        if enhancements is None:
            return "manifest settings"
        neutral_one = {"contrast", "saturation", "gamma"}
        active = []
        for name, value in enhancements.items():
            if isinstance(value, bool):
                enabled = value
            elif isinstance(value, (int, float)):
                enabled = value != (1 if name in neutral_one else 0)
            else:
                enabled = value not in (None, "", "none", "None")
            if enabled:
                active.append(name.replace("_", " "))
        return ", ".join(active) if active else "none"

    def _approve_pipeline_review(self) -> None:
        stage_index = self.view._pipeline_demo_waiting_for_review
        if stage_index is None:
            return
        real_review = self.view._pipeline_real_waiting_for_review == stage_index
        self.view._pipeline_demo_waiting_for_review = None
        self.view._pipeline_real_waiting_for_review = None
        self.view.pipeline_review_panel.hide()
        self.view.run_pipeline_button.setEnabled(True)
        if real_review and self.view._pipeline_worker is not None:
            self.view.run_pipeline_button.setText("Stop pipeline")
            self.view.run_pipeline_button.setToolTip("Stop after the currently running external operation finishes.")
            self.view.runs._set_run_readiness("Continuing", "running")
            self.view.run_log._append_console(f"[Confirmed] {PIPELINE_STAGES[stage_index]}.")
            self.view._pipeline_worker.approve_review()
            return
        self.view.run_pipeline_button.setText("Stop preview")
        self.view.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self.view.runs._set_run_readiness("Playing preview", "running")
        self.view.run_log._append_console(f"[Confirmed] {PIPELINE_STAGES[stage_index]}.")
        self.view.run_log._append_console(f"[Complete] {PIPELINE_STAGES[stage_index]}.")
        self.view.demo._begin_pipeline_demo_stage(stage_index + 1)

    def _reject_pipeline_review(self) -> None:
        stage_index = self.view._pipeline_demo_waiting_for_review
        if stage_index is None:
            return
        real_review = self.view._pipeline_real_waiting_for_review == stage_index
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self.view._pipeline_demo_waiting_for_review = None
        self.view._pipeline_real_waiting_for_review = None
        self.view._pipeline_demo_blocked_stage = stage_index
        self.view.run_log._set_pipeline_log_state("Paused", "paused")
        self.view.pipeline_review_title.setText("Pipeline paused — changes required")
        self.view.pipeline_review_description.setText(
            f"Update the {gate['setting']}. Resuming will replay the preceding stage and show this preview check again."
        )
        self.view.pipeline_change_settings_button.setText(f"Open {gate['setting']}")
        self.view.pipeline_change_settings_button.show()
        self.view.pipeline_needs_changes_button.hide()
        self.view.pipeline_approve_button.hide()
        card = self.view.pipeline_stage_cards[stage_index]
        card.setProperty("pipelineState", "blocked")
        card.style().unpolish(card)
        card.style().polish(card)
        self.view.pipeline_stage_status_labels[stage_index].setText("Changes required")
        self.view.pipeline_stage_review_labels[stage_index].setText("Needs changes")
        self.view.stage_progress._set_pipeline_stage_progress(stage_index, 100, False, "error", indicator_state="error")
        self.view.run_pipeline_button.setEnabled(True)
        if real_review:
            self.view._pipeline_real_complete = True
            self.view.run_pipeline_button.setText("Back to videos")
            self.view.run_pipeline_button.setToolTip(
                "Return to the queue. The next run will use the corrected profile."
            )
            if self.view._pipeline_worker is not None:
                self.view._pipeline_worker.reject_review()
        else:
            self.view.run_pipeline_button.setText("Resume preview")
            self.view.run_pipeline_button.setToolTip(
                f"Replay the affected stage after updating the {gate['setting']}, then return to this review checkpoint."
            )
        self.view.runs._set_run_readiness("Changes required", "error")
        self.view.run_log._append_console(f"[Changes required] Update the {gate['setting']}; pipeline remains paused.")

    def _resume_pipeline_demo(self) -> None:
        stage_index = self.view._pipeline_demo_blocked_stage
        if stage_index is None:
            return
        replay_stage = int(PIPELINE_REVIEW_GATES[stage_index]["replay_stage"])
        self.view._pipeline_demo_blocked_stage = None
        self.view.pipeline_review_panel.hide()
        self.view.run_pipeline_button.setText("Stop preview")
        self.view.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self.view.runs._set_run_readiness("Replaying stage", "running")
        self.view.run_log._append_console(
            f"[Resume] Replaying {PIPELINE_STAGES[replay_stage]} before re-checking the preview."
        )
        self.view.demo._begin_pipeline_demo_stage(replay_stage)


try:
    import cv2
except ImportError:
    cv2 = None
