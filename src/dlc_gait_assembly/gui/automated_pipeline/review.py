from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)

from dlc_gait_assembly.gui.automated_pipeline.constants import (
    PIPELINE_REVIEW_GATES,
    PIPELINE_STAGES,
    STOP_PREVIEW_TOOLTIP,
)
from dlc_gait_assembly.gui.automated_pipeline.previews import (
    AutomationVideoPreviewDialog,
    PipelineImagePreviewDialog,
    PipelineTextPreviewDialog,
    ReviewVideoSource,
)
from dlc_gait_assembly.services.pipeline.automated import (
    ReviewArtifact,
    StageReview,
)

try:
    import cv2
except ImportError:
    cv2 = None


class PipelineReviewMixin:
    def _pause_for_pipeline_review(
        self,
        stage_index: int,
        artifacts: StageReview | None = None,
    ) -> None:
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._pipeline_demo_timer.stop()
        self._pipeline_demo_waiting_for_review = stage_index
        self._set_pipeline_overview_compact(True)
        self.pipeline_review_title.setText(str(gate["title"]))
        self.pipeline_review_description.setText(str(gate["description"]))
        self._populate_pipeline_review_preview(stage_index, artifacts)
        self.pipeline_change_settings_button.hide()
        self.pipeline_needs_changes_button.show()
        self.pipeline_approve_button.show()
        self.pipeline_activity_panel.hide()
        self.pipeline_review_panel.show()
        self._set_pipeline_log_state("Review", "review")
        self.pipeline_stage_status_labels[stage_index].setText("Awaiting confirmation")
        self.pipeline_stage_review_labels[stage_index].setText("Awaiting review")
        self.pipeline_progress_bar.set_active(False)
        self._set_pipeline_stage_progress(
            stage_index, 100, False, "ready", indicator_state="active"
        )
        self.run_pipeline_button.setText("Awaiting confirmation")
        self.run_pipeline_button.setEnabled(False)
        self.run_pipeline_button.setToolTip(
            "The walkthrough is paused. Use Confirm and continue or Needs changes in the review panel."
        )
        self._set_run_readiness("Review required", "review")
        self._append_console(f"[Manual check] {gate['title']}. Pipeline paused.")

    def _populate_pipeline_review_preview(
        self,
        stage_index: int,
        artifacts: StageReview | None = None,
    ) -> None:
        if stage_index == 4:
            self.pipeline_review_layout.setStretch(0, 2)
            self.pipeline_review_layout.setStretch(1, 1)
        else:
            self.pipeline_review_layout.setStretch(0, 1)
            self.pipeline_review_layout.setStretch(1, 2)
        if artifacts is not None:
            self._populate_real_pipeline_review_preview(stage_index, artifacts)
            return
        if stage_index == 4:
            self._pipeline_stickplot_path = (
                self._project_root
                / "assets"
                / "analysis_previews"
                / "alma_reference_stickplot.svg"
            )
            self.pipeline_stickplot_preview.setText("")
            loaded = self.pipeline_stickplot_preview.load_image_path(
                self._pipeline_stickplot_path
            )
            if not loaded:
                self.pipeline_stickplot_preview.setPixmap(QPixmap())
                self.pipeline_stickplot_preview.setText(
                    "The real ALMA reference stickplot is unavailable."
                )
            self._pipeline_stickplot_pixmap = self.pipeline_stickplot_preview.pixmap()
            self.pipeline_stickplot_preview.setToolTip(
                "Actual ALMA stickplot generated from the bundled reference DLC coordinate "
                "dataset. Click it to open a larger viewer."
            )
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_stickplot_preview
            )
            return

        self.pipeline_review_video_list.clear()
        component_names = self._regions or ("Full frame",)
        regions = ", ".join(component_names)
        enhancements = self._processing_enhancement_summary()
        preview_paths: list[Path | None] = list(self._video_paths)
        if not preview_paths:
            preview_paths = [None] * self._pipeline_demo_total_videos
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
                    "Inspect this processed output for the expected crop regions and "
                    "enhancements. Double-click to open a larger preview."
                )
                self.pipeline_review_video_list.addItem(item)
        else:
            self.pipeline_component_video_lists.clear()
            while self.pipeline_component_tabs.count():
                page = self.pipeline_component_tabs.widget(0)
                self.pipeline_component_tabs.removeTab(0)
                page.deleteLater()
            for component in component_names:
                model_source = self._model_sources.get(component)
                model_name = model_source.name if model_source is not None else "configured model"
                component_list = QListWidget()
                component_list.setObjectName("PipelineReviewVideoList")
                component_list.setWordWrap(False)
                component_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                component_list.itemDoubleClicked.connect(
                    self._open_pipeline_review_video
                )
                self.pipeline_component_tabs.addTab(component_list, component)
                self.pipeline_component_tabs.setTabToolTip(
                    self.pipeline_component_tabs.count() - 1,
                    f"{component} component • {model_name}",
                )
                self.pipeline_component_video_lists[component] = component_list
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
                        f"Inspect the {component} tracking overlay produced with {model_name}. "
                        "Double-click to open a larger preview."
                    )
                    component_list.addItem(item)
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_component_tabs
            )
            return
        self.pipeline_review_preview_stack.setCurrentWidget(
            self.pipeline_review_video_list
        )

    def _populate_real_pipeline_review_preview(
        self,
        stage_index: int,
        artifacts: StageReview,
    ) -> None:
        items = artifacts.items
        if stage_index == 4:
            image_paths = [item.path for item in items if item.path.is_file()]
            self._pipeline_stickplot_path = image_paths[0] if image_paths else None
            self.pipeline_stickplot_preview.setText("")
            loaded = (
                self.pipeline_stickplot_preview.load_image_path(
                    self._pipeline_stickplot_path
                )
                if self._pipeline_stickplot_path is not None
                else False
            )
            if not loaded:
                self.pipeline_stickplot_preview.setPixmap(QPixmap())
                self.pipeline_stickplot_preview.setText("No stickplot image was produced")
            self._pipeline_stickplot_pixmap = self.pipeline_stickplot_preview.pixmap()
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_stickplot_preview
            )
            return

        if stage_index == 0:
            self.pipeline_review_video_list.clear()
            for artifact in items:
                self._add_real_review_video_item(self.pipeline_review_video_list, artifact)
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_review_video_list
            )
            return

        self.pipeline_component_video_lists.clear()
        while self.pipeline_component_tabs.count():
            page = self.pipeline_component_tabs.widget(0)
            self.pipeline_component_tabs.removeTab(0)
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
            component_list.itemDoubleClicked.connect(self._open_pipeline_review_video)
            self.pipeline_component_tabs.addTab(component_list, view)
            self.pipeline_component_video_lists[view] = component_list
            for artifact in items:
                if (artifact.view or "Full frame") == view:
                    self._add_real_review_video_item(component_list, artifact)
        self.pipeline_review_preview_stack.setCurrentWidget(self.pipeline_component_tabs)

    def _add_real_review_video_item(
        self,
        target: QListWidget,
        artifact: ReviewArtifact,
    ) -> None:
        path = artifact.path
        title = artifact.title or path.name
        view = artifact.view or "Full frame"
        details = f"View: {view}"
        item = QListWidgetItem(f"{title}  —  {details}")
        item.setData(Qt.UserRole, str(path))
        item.setData(Qt.UserRole + 1, details)
        item.setData(Qt.UserRole + 2, title)
        item.setData(Qt.UserRole + 4, view)
        item.setToolTip("Double-click to inspect this generated video.")
        target.addItem(item)

    def _processing_enhancement_summary(self) -> str:
        if self._manifest_source is None:
            return "manifest settings"
        try:
            data = json.loads(self._manifest_source.read_text(encoding="utf-8"))
            enhancements = data["operations"].get("enhancements", {})
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return "manifest settings"
        if not isinstance(enhancements, dict):
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

    def _open_pipeline_review_video(self, item: QListWidgetItem) -> None:
        if item.data(Qt.UserRole + 3) == "component_header":
            return
        title = str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0])
        details = str(item.data(Qt.UserRole + 1) or "")
        review_sources, selected_index = self._pipeline_review_sources(item)
        try:
            if review_sources:
                dialog: QDialog = AutomationVideoPreviewDialog(
                    review_sources[selected_index].path,
                    self,
                    review_sources=review_sources,
                    initial_source_index=selected_index,
                )
            else:
                dialog = PipelineTextPreviewDialog(
                    title,
                    f"{details}\n\nNo generated video exists in UI preview mode.",
                    self,
                )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not preview video", str(exc))
            return
        self._show_large_review_dialog(dialog)

    def _pipeline_review_sources(
        self,
        selected_item: QListWidgetItem,
    ) -> tuple[tuple[ReviewVideoSource, ...], int]:
        selected_list = selected_item.listWidget()
        if selected_list is self.pipeline_review_video_list:
            review_lists = (("All regions", self.pipeline_review_video_list),)
        else:
            review_lists = tuple(self.pipeline_component_video_lists.items())

        sources: list[ReviewVideoSource] = []
        selected_index = 0
        for fallback_view, review_list in review_lists:
            for row in range(review_list.count()):
                item = review_list.item(row)
                if item.data(Qt.UserRole + 3) == "component_header":
                    continue
                path_text = str(item.data(Qt.UserRole) or "")
                path = Path(path_text) if path_text else None
                if path is None or not path.is_file():
                    continue
                source = ReviewVideoSource(
                    path=path,
                    title=str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0]),
                    details=str(item.data(Qt.UserRole + 1) or ""),
                    view_name=str(item.data(Qt.UserRole + 4) or fallback_view),
                )
                if item is selected_item:
                    selected_index = len(sources)
                sources.append(source)
        return tuple(sources), selected_index

    def _open_large_stickplot_preview(self) -> None:
        if (
            self._pipeline_stickplot_path is None
            or not self._pipeline_stickplot_path.is_file()
        ):
            self._show_large_review_dialog(
                PipelineTextPreviewDialog(
                    "Generated stickplot preview",
                    "No ALMA or RustLab1 stickplot has been generated for this review.",
                    self,
                )
            )
            return
        self._show_large_review_dialog(
            PipelineImagePreviewDialog(
                "Generated stickplot preview",
                self._pipeline_stickplot_path,
                self,
            )
        )

    def _show_large_review_dialog(self, dialog: QDialog) -> None:
        if self._large_review_dialog is not None:
            self._large_review_dialog.close()
        self._large_review_dialog = dialog
        dialog.finished.connect(
            lambda _result, closed_dialog=dialog: self._large_review_closed(closed_dialog)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _large_review_closed(self, dialog: QDialog) -> None:
        if self._large_review_dialog is dialog:
            self._large_review_dialog = None

    def _approve_pipeline_review(self) -> None:
        stage_index = self._pipeline_demo_waiting_for_review
        if stage_index is None:
            return
        real_review = self._pipeline_real_waiting_for_review == stage_index
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_real_waiting_for_review = None
        self.pipeline_review_panel.hide()
        self.run_pipeline_button.setEnabled(True)
        if real_review and self._pipeline_worker is not None:
            self.run_pipeline_button.setText("Stop pipeline")
            self.run_pipeline_button.setToolTip(
                "Stop after the currently running external operation finishes."
            )
            self._set_run_readiness("Continuing", "running")
            self._append_console(f"[Confirmed] {PIPELINE_STAGES[stage_index]}.")
            self._pipeline_worker.approve_review()
            return
        self.run_pipeline_button.setText("Stop preview")
        self.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self._set_run_readiness("Playing preview", "running")
        self._append_console(f"[Confirmed] {PIPELINE_STAGES[stage_index]}.")
        self._append_console(f"[Complete] {PIPELINE_STAGES[stage_index]}.")
        self._begin_pipeline_demo_stage(stage_index + 1)

    def _reject_pipeline_review(self) -> None:
        stage_index = self._pipeline_demo_waiting_for_review
        if stage_index is None:
            return
        real_review = self._pipeline_real_waiting_for_review == stage_index
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_real_waiting_for_review = None
        self._pipeline_demo_blocked_stage = stage_index
        self._set_pipeline_log_state("Paused", "paused")
        self.pipeline_review_title.setText("Pipeline paused — changes required")
        self.pipeline_review_description.setText(
            f"Update the {gate['setting']}. Resuming will replay the preceding stage and "
            "show this preview check again."
        )
        self.pipeline_change_settings_button.setText(f"Open {gate['setting']}")
        self.pipeline_change_settings_button.show()
        self.pipeline_needs_changes_button.hide()
        self.pipeline_approve_button.hide()
        card = self.pipeline_stage_cards[stage_index]
        card.setProperty("pipelineState", "blocked")
        card.style().unpolish(card)
        card.style().polish(card)
        self.pipeline_stage_status_labels[stage_index].setText("Changes required")
        self.pipeline_stage_review_labels[stage_index].setText("Needs changes")
        self._set_pipeline_stage_progress(
            stage_index, 100, False, "error", indicator_state="error"
        )
        self.run_pipeline_button.setEnabled(True)
        if real_review:
            self._pipeline_real_complete = True
            self.run_pipeline_button.setText("Back to videos")
            self.run_pipeline_button.setToolTip(
                "Return to the queue. The next run will use the corrected profile."
            )
            if self._pipeline_worker is not None:
                self._pipeline_worker.reject_review()
        else:
            self.run_pipeline_button.setText("Resume preview")
            self.run_pipeline_button.setToolTip(
                f"Replay the affected stage after updating the {gate['setting']}, then return "
                "to this review checkpoint."
            )
        self._set_run_readiness("Changes required", "error")
        self._append_console(
            f"[Changes required] Update the {gate['setting']}; pipeline remains paused."
        )

    def _open_pipeline_fix_settings(self) -> None:
        stage_index = self._pipeline_demo_blocked_stage
        if stage_index is None:
            return
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._show_profile_configuration()
        self.configuration_tabs.setCurrentIndex(int(gate["tab"]))

    def _resume_pipeline_demo(self) -> None:
        stage_index = self._pipeline_demo_blocked_stage
        if stage_index is None:
            return
        replay_stage = int(PIPELINE_REVIEW_GATES[stage_index]["replay_stage"])
        self._pipeline_demo_blocked_stage = None
        self.pipeline_review_panel.hide()
        self.run_pipeline_button.setText("Stop preview")
        self.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self._set_run_readiness("Replaying stage", "running")
        self._append_console(
            f"[Resume] Replaying {PIPELINE_STAGES[replay_stage]} before re-checking the preview."
        )
        self._begin_pipeline_demo_stage(replay_stage)
