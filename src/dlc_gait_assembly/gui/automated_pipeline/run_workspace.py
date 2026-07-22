from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.automated_pipeline.constants import (
    PIPELINE_PREVIEW_MESSAGES,
    PIPELINE_REVIEW_GATES,
    PIPELINE_STAGE_ACTIVITY,
    PIPELINE_STAGE_LABELS,
    PIPELINE_STAGES,
    RUN_PREVIEW_TOOLTIP,
    STOP_PREVIEW_TOOLTIP,
)
from dlc_gait_assembly.gui.automated_pipeline.previews import (
    AutomationVideoPreviewDialog,
)
from dlc_gait_assembly.gui.automated_pipeline.worker import AutomatedPipelineWorker
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedPipelineProfile,
)
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.pipeline.automated import (
    StageReview,
)

try:
    import cv2
except ImportError:
    cv2 = None


class RunWorkspacePage(QWidget):
    """Container for the video queue and pipeline status controls."""


class RunWorkspaceMixin:
    def _choose_videos(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add videos for automated processing",
            str(Path.home()),
            f"Video files ({extensions});;All files (*)",
        )
        self._add_video_paths([Path(path) for path in paths])

    def _add_video_paths(self, paths: object) -> None:
        added = 0
        skipped = 0
        known_paths = {str(path) for path in self._video_paths}
        for raw_path in paths if isinstance(paths, (list, tuple)) else ():
            path = Path(raw_path).expanduser().resolve()
            key = str(path)
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS or key in known_paths:
                skipped += 1
                continue
            self._video_paths.append(path)
            known_paths.add(key)
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, key)
            item.setToolTip(key)
            self.video_list.addItem(item)
            added += 1
        self._update_video_count()
        if added and self.video_list.currentRow() < 0:
            self.video_list.setCurrentRow(0)
        if added:
            self._append_console(f"[Videos] Added {added} video(s); {len(self._video_paths)} queued.")
        if skipped:
            self._append_console(f"[Videos] Skipped {skipped} unsupported or duplicate item(s).")

    def _remove_selected_videos(self) -> None:
        selected = self.video_list.selectedItems()
        if not selected:
            return
        self._stop_hover_preview()
        removed_paths = {str(item.data(Qt.UserRole)) for item in selected}
        for item in selected:
            self.video_list.takeItem(self.video_list.row(item))
        self._video_paths = [path for path in self._video_paths if str(path) not in removed_paths]
        self._update_video_count()
        self._append_console(f"[Videos] Removed {len(removed_paths)} video(s).")

    def _clear_videos(self) -> None:
        if not self._video_paths:
            return
        self._release_hover_capture()
        count = len(self._video_paths)
        self._video_paths.clear()
        self.video_list.clear()
        self.video_hover_card.hide()
        self._update_video_count()
        self._append_console(f"[Videos] Cleared {count} video(s).")

    def _update_video_count(self) -> None:
        count = len(self._video_paths)
        self.video_count_label.setText(f"{count} video" if count == 1 else f"{count} videos")
        self._sync_video_actions()
        self.video_list.viewport().update()

    def _sync_video_actions(self) -> None:
        has_videos = bool(self._video_paths)
        self.remove_videos_button.setEnabled(bool(self.video_list.selectedItems()))
        self.clear_videos_button.setEnabled(has_videos)

    def _append_console(self, message: str) -> None:
        lowered = message.lower()
        if any(token in lowered for token in ("error", "failed", "changes required")):
            accent = theme.STATUS_ERROR
        elif any(token in lowered for token in ("complete", "confirmed", "ready")):
            accent = theme.STATUS_READY
        elif any(token in lowered for token in ("review", "manual check", "resume")):
            accent = theme.STATUS_RUNNING
        else:
            accent = theme.CANVAS_TEXT

        if accent != theme.CANVAS_TEXT:
            accent = theme.mix_hex(accent, theme.CANVAS_TEXT, 0.22)

        cursor = self.automation_console.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        prefix_end = message.find("]") + 1
        if prefix_end > 0:
            prefix_format = QTextCharFormat()
            prefix_format.setForeground(QColor(accent))
            cursor.insertText(message[:prefix_end], prefix_format)
            body_format = QTextCharFormat()
            body_format.setForeground(QColor(theme.CANVAS_TEXT))
            cursor.insertText(message[prefix_end:], body_format)
        else:
            line_format = QTextCharFormat()
            line_format.setForeground(QColor(accent))
            cursor.insertText(message, line_format)
        self.automation_console.setTextCursor(cursor)
        self.automation_console.ensureCursorVisible()

    def _set_pipeline_log_state(self, text: str, state: str) -> None:
        self.pipeline_log_state.setText(f"●  {text}")
        self.pipeline_log_state.setProperty("logState", state)
        self.pipeline_log_state.style().unpolish(self.pipeline_log_state)
        self.pipeline_log_state.style().polish(self.pipeline_log_state)

    def _set_run_readiness(self, text: str, state: str) -> None:
        self.run_readiness_label.setText(f"●  {text}")
        self.run_readiness_label.setProperty("readinessState", state)
        self.run_readiness_label.style().unpolish(self.run_readiness_label)
        self.run_readiness_label.style().polish(self.run_readiness_label)

    def _toggle_pipeline_run(self) -> None:
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.request_cancel()
            self.run_pipeline_button.setText("Stopping")
            self.run_pipeline_button.setEnabled(False)
            self._set_run_readiness("Stopping after current operation", "running")
            self._append_console("[Pipeline] Stop requested; waiting for the current operation.")
            return
        if self._pipeline_real_complete:
            self._pipeline_real_complete = False
            self._pipeline_demo_blocked_stage = None
            self._pipeline_demo_waiting_for_review = None
            self.set_pipeline_running(False)
            self.run_pipeline_button.setText("Run pipeline")
            self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.run_pipeline_button.setEnabled(True)
            self._set_run_readiness("Ready", "ready")
            return

        profile = self._profiles.get(self._current_profile_id or "")
        if profile is None or not self._video_paths:
            self._toggle_pipeline_demo()
            return
        self._start_pipeline(profile)

    def _start_pipeline(self, profile: AutomatedPipelineProfile) -> None:
        self._pipeline_real_complete = False
        self._pipeline_real_waiting_for_review = None
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_demo_blocked_stage = None
        self._pipeline_review_artifacts = None
        self._pipeline_stickplot_path = None
        self._pipeline_stickplot_pixmap = None
        self._pipeline_output_folder = None
        self.open_pipeline_output_button.setText("Open outputs")
        self.open_pipeline_output_button.setToolTip(str(self._automated_output_root))
        self._pipeline_skipped_stages.clear()
        self.pipeline_review_panel.hide()
        self.automation_console.clear()
        self.set_pipeline_running(True)
        self.run_pipeline_button.setText("Stop pipeline")
        self.run_pipeline_button.setToolTip(
            "Stop after the currently running external operation finishes."
        )
        self.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Running", "running")
        self._append_console(
            f'[Pipeline] Running profile "{profile.name}" on {len(self._video_paths)} video(s).'
        )
        worker = AutomatedPipelineWorker(
            profile,
            list(self._video_paths),
            self._project_root,
            parent=self,
        )
        self._pipeline_worker = worker
        worker.stage_started.connect(self._pipeline_stage_started)
        worker.output_folder_ready.connect(self._pipeline_output_folder_ready)
        worker.stage_progress.connect(self._pipeline_stage_progressed)
        worker.stage_skipped.connect(self._pipeline_stage_skipped)
        worker.log_message.connect(lambda message: self._append_console(f"[Pipeline] {message}."))
        worker.review_requested.connect(self._pipeline_review_requested)
        worker.run_completed.connect(self._pipeline_run_completed)
        worker.run_failed.connect(self._pipeline_run_failed)
        worker.run_cancelled.connect(self._pipeline_run_cancelled)
        worker.finished.connect(lambda: self._pipeline_worker_finished(worker))
        worker.start()

    def _pipeline_output_folder_ready(self, output_folder: object) -> None:
        self._pipeline_output_folder = Path(output_folder).expanduser().resolve()
        self.open_pipeline_output_button.setText("Open run output")
        self.open_pipeline_output_button.setToolTip(str(self._pipeline_output_folder))
        self.pipeline_current_stage_label.setToolTip(str(self._pipeline_output_folder))

    def _open_pipeline_output(self) -> None:
        output_folder = self._pipeline_output_folder or self._automated_output_root
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_folder)))

    def _pipeline_stage_started(self, stage_index: int, label: str) -> None:
        activity = PIPELINE_STAGE_ACTIVITY[stage_index]
        self.set_pipeline_stage(
            stage_index,
            progress=0,
            processed_videos=0 if stage_index == 0 else None,
            total_videos=len(self._video_paths) if stage_index == 0 else None,
            status_text=activity,
        )
        self.pipeline_current_stage_label.setText(activity)
        self.pipeline_current_stage_label.setToolTip("")
        self._set_run_readiness(label, "running")

    def _pipeline_stage_progressed(
        self,
        stage_index: int,
        current: int,
        total: int,
        message: str,
    ) -> None:
        progress = None if total <= 0 else (max(0, current) / max(1, total)) * 100.0
        activity = message or PIPELINE_STAGE_ACTIVITY[stage_index]
        compact_activity = activity
        if stage_index in (1, 3) and ":" in compact_activity:
            compact_activity = compact_activity.split(":", 1)[0]
        self.set_pipeline_stage(
            stage_index,
            progress=progress,
            processed_videos=current if stage_index == 0 else None,
            total_videos=total if stage_index == 0 else None,
            status_text=compact_activity,
        )
        self.pipeline_current_stage_label.setText(activity)
        self.pipeline_current_stage_label.setToolTip(activity)
        if message and stage_index != 1:
            self._append_console(f"[{PIPELINE_STAGE_LABELS[stage_index]}] {message}.")

    def _pipeline_stage_skipped(self, stage_index: int, reason: str) -> None:
        self._pipeline_skipped_stages.add(stage_index)
        card = self.pipeline_stage_cards[stage_index]
        card.setProperty("pipelineState", "skipped")
        card.style().unpolish(card)
        card.style().polish(card)
        self.pipeline_stage_status_labels[stage_index].setText("Skipped")
        if stage_index in PIPELINE_REVIEW_GATES:
            self.pipeline_stage_review_labels[stage_index].setText("Not included")
        self._set_pipeline_stage_progress(
            stage_index, 0, False, "primary", indicator_state="skipped"
        )
        self._append_console(f"[Skipped] {reason}.")

    def _pipeline_review_requested(self, stage_index: int, artifacts: object) -> None:
        self._pipeline_real_waiting_for_review = stage_index
        self._pipeline_review_artifacts = artifacts if isinstance(artifacts, StageReview) else None
        self._pause_for_pipeline_review(stage_index, self._pipeline_review_artifacts)

    def _pipeline_run_completed(self, result: object) -> None:
        self._pipeline_real_waiting_for_review = None
        self._pipeline_real_complete = True
        self.complete_pipeline("Pipeline complete")
        self.run_pipeline_button.setText("Back to videos")
        self.run_pipeline_button.setToolTip("Return to the video queue.")
        self.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Complete", "complete")
        output_folder = getattr(result, "output_folder", None)
        if output_folder is not None:
            self._pipeline_output_folder_ready(output_folder)
            self._append_console(f"[Complete] Results saved to {output_folder}.")
        output_manifest = getattr(result, "output_manifest", None)
        if output_manifest is not None:
            self._append_console(f"[Complete] Run manifest: {output_manifest}.")

    def _pipeline_run_failed(self, stage_index: int, message: str) -> None:
        self._pipeline_real_waiting_for_review = None
        self._pipeline_real_complete = True
        self.pipeline_review_panel.hide()
        self.pipeline_activity_panel.show()
        self.pipeline_progress_bar.set_active(False)
        self.pipeline_progress_bar.set_accent_role("error")
        self._set_pipeline_log_state("Failed", "error")
        if 0 <= stage_index < len(self.pipeline_stage_cards):
            card = self.pipeline_stage_cards[stage_index]
            card.setProperty("pipelineState", "blocked")
            card.style().unpolish(card)
            card.style().polish(card)
            self.pipeline_stage_status_labels[stage_index].setText("Failed")
            self._set_pipeline_stage_progress(
                stage_index, 100, False, "error", indicator_state="error"
            )
        self.run_pipeline_button.setText("Back to videos")
        self.run_pipeline_button.setToolTip("Return to the queue, correct the profile, and run again.")
        self.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Failed", "error")
        self._append_console(f"[Failed] {message}")

    def _pipeline_run_cancelled(self) -> None:
        if self._pipeline_demo_blocked_stage is not None:
            return
        self._pipeline_real_waiting_for_review = None
        self._pipeline_real_complete = False
        self.pipeline_review_panel.hide()
        self.set_pipeline_running(False)
        self.run_pipeline_button.setText("Run pipeline")
        self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
        self.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Stopped", "neutral")
        self._append_console("[Pipeline] Stopped.")

    def _pipeline_worker_finished(self, worker: AutomatedPipelineWorker) -> None:
        if self._pipeline_worker is worker:
            self._pipeline_worker = None
        worker.deleteLater()

    def _toggle_pipeline_demo(self) -> None:
        if self._pipeline_demo_complete:
            self._pipeline_demo_complete = False
            self.pipeline_review_panel.hide()
            self.set_pipeline_running(False)
            self.run_pipeline_button.setText("Run pipeline")
            self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self._set_run_readiness("Preview only", "neutral")
            return
        if self._pipeline_demo_blocked_stage is not None:
            self._resume_pipeline_demo()
            return
        if self._pipeline_demo_waiting_for_review is not None:
            return
        if self._pipeline_demo_timer.isActive():
            self._pipeline_demo_timer.stop()
            self._pipeline_demo_waiting_for_review = None
            self._pipeline_demo_blocked_stage = None
            self.pipeline_review_panel.hide()
            self.set_pipeline_running(False)
            self.run_pipeline_button.setText("Run pipeline")
            self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self._set_run_readiness("Stopped", "neutral")
            self._append_console("[Preview] Stopped. No processing was performed.")
            return

        self._pipeline_demo_stage = 0
        self._pipeline_demo_progress = 0.0
        self._pipeline_demo_total_videos = len(self._video_paths) or 4
        self._pipeline_demo_last_processed = -1
        self._pipeline_demo_complete = False
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_demo_blocked_stage = None
        self.pipeline_review_panel.hide()
        self.set_pipeline_running(True)
        self.run_pipeline_button.setText("Stop preview")
        self.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self._set_run_readiness("Playing preview", "running")
        self._append_console("[Preview] Pipeline UI preview started; no files will be changed.")
        self._begin_pipeline_demo_stage(0)

    def _begin_pipeline_demo_stage(self, stage_index: int) -> None:
        self.pipeline_activity_panel.show()
        self._pipeline_demo_stage = stage_index
        self._pipeline_demo_progress = 0.0
        if stage_index == 0:
            self._pipeline_demo_last_processed = -1
        self._append_console(
            f"[{stage_index + 1}/{len(PIPELINE_STAGES)}] "
            f"{PIPELINE_PREVIEW_MESSAGES[stage_index]}."
        )
        self.set_pipeline_stage(
            stage_index,
            progress=0,
            processed_videos=0 if stage_index == 0 else None,
            total_videos=self._pipeline_demo_total_videos if stage_index == 0 else None,
            status_text=PIPELINE_STAGE_ACTIVITY[stage_index],
        )
        self._pipeline_demo_timer.start()

    def _advance_pipeline_demo(self) -> None:
        if (
            self._pipeline_demo_waiting_for_review is not None
            or self._pipeline_demo_blocked_stage is not None
        ):
            return
        if not 0 <= self._pipeline_demo_stage < len(PIPELINE_STAGES):
            return
        self._pipeline_demo_progress = min(100.0, self._pipeline_demo_progress + 4.0)
        processed_videos = None
        total_videos = None
        if self._pipeline_demo_stage == 0:
            total_videos = self._pipeline_demo_total_videos
            processed_videos = min(
                total_videos,
                round(total_videos * self._pipeline_demo_progress / 100.0),
            )
            if processed_videos != self._pipeline_demo_last_processed:
                self._pipeline_demo_last_processed = processed_videos
                self._append_console(
                    f"[Video processing] {processed_videos} / {total_videos} videos processed."
                )

        self.set_pipeline_stage(
            self._pipeline_demo_stage,
            progress=self._pipeline_demo_progress,
            processed_videos=processed_videos,
            total_videos=total_videos,
            status_text=PIPELINE_STAGE_ACTIVITY[self._pipeline_demo_stage],
        )
        if self._pipeline_demo_progress < 100:
            return

        completed_stage = self._pipeline_demo_stage
        if completed_stage in PIPELINE_REVIEW_GATES:
            self._pause_for_pipeline_review(completed_stage)
            return
        self._append_console(f"[Complete] {PIPELINE_STAGES[completed_stage]}.")
        next_stage = completed_stage + 1
        if next_stage >= len(PIPELINE_STAGES):
            self._pipeline_demo_timer.stop()
            self._pipeline_demo_complete = True
            self.complete_pipeline("Pipeline preview complete")
            self.run_pipeline_button.setText("Back to videos")
            self.run_pipeline_button.setToolTip(
                "Return to the queued videos after the completed walkthrough. No files were changed."
            )
            self._set_run_readiness("Complete", "complete")
            self._append_console("[Preview complete] No processing was performed.")
            return
        self._begin_pipeline_demo_stage(next_stage)

    def set_pipeline_running(self, running: bool) -> None:
        """Swap the video queue for pipeline progress without starting any work."""
        was_running = self._pipeline_running
        self._pipeline_running = running
        if running:
            self._set_run_readiness("Running", "running")
            self._set_pipeline_overview_compact(True)
            self._stop_hover_preview()
            self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
            if self._pipeline_demo_waiting_for_review is None:
                self.pipeline_activity_panel.show()
            self.pipeline_progress_bar.set_accent_role("running")
            self.pipeline_progress_bar.set_active(True)
            if not was_running:
                total = len(self._video_paths)
                self.set_pipeline_stage(
                    0,
                    progress=0,
                    processed_videos=0,
                    total_videos=total,
                    status_text="Preparing videos",
                )
        else:
            self._pipeline_skipped_stages.clear()
            self._emphasize_pipeline_stage(None)
            self._set_pipeline_overview_compact(False)
            self.automation_input_stack.setCurrentWidget(self.video_panel)
            self.pipeline_progress_bar.set_active(False)
            self._set_pipeline_log_state("Ready", "ready")
            self._set_run_readiness("Ready", "ready")

    def set_pipeline_stage(
        self,
        stage_index: int,
        *,
        progress: float | None = None,
        processed_videos: int | None = None,
        total_videos: int | None = None,
        status_text: str | None = None,
    ) -> None:
        """Update the ordered progress view for a future pipeline controller."""
        if not 0 <= stage_index < len(PIPELINE_STAGES):
            raise ValueError(f"Pipeline stage index must be between 0 and {len(PIPELINE_STAGES) - 1}.")
        self._pipeline_running = True
        self._set_pipeline_overview_compact(True)
        if self._pipeline_demo_waiting_for_review is None:
            self.pipeline_review_panel.hide()
            self.pipeline_activity_panel.show()
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        self._set_pipeline_log_state("Running", "running")
        active_status = status_text or "In progress"
        stage_progress = None if progress is None else max(0.0, min(100.0, float(progress)))
        for index, (card, label, review_label) in enumerate(
            zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_status_labels,
                self.pipeline_stage_review_labels,
                strict=True,
            )
        ):
            if index < stage_index and index in self._pipeline_skipped_stages:
                state, text = "skipped", "Skipped"
                self._set_pipeline_stage_progress(
                    index, 0, False, "primary", indicator_state="skipped"
                )
            elif index < stage_index:
                state, text = "complete", "Complete"
                self._set_pipeline_stage_progress(
                    index, 100, False, "ready", indicator_state="complete"
                )
            elif index == stage_index:
                text = active_status
                if stage_progress is not None:
                    text = f"{active_status} {stage_progress:g}%"
                state = "active"
                self._set_pipeline_stage_progress(
                    index, stage_progress, True, "running", indicator_state="active"
                )
            else:
                state, text = "pending", "Waiting"
                self._set_pipeline_stage_progress(
                    index, 0, False, "primary", indicator_state="pending"
                )
            card.setProperty("pipelineState", state)
            label.setText(text)
            if index in PIPELINE_REVIEW_GATES:
                if index in self._pipeline_skipped_stages:
                    review_label.setText("Not included")
                else:
                    review_label.setText(
                        "Reviewed" if index < stage_index else "Review required"
                    )
            card.style().unpolish(card)
            card.style().polish(card)

        self._emphasize_pipeline_stage(stage_index)

        if processed_videos is not None or total_videos is not None:
            processed = max(0, processed_videos or 0)
            total = max(0, total_videos or 0)
            self.pipeline_video_progress_label.setText(
                f"{processed} / {total} videos processed"
            )

        if progress is None:
            self.pipeline_progress_bar.set_accent_role("running")
            self.pipeline_progress_bar.setRange(0, 0)
            self.pipeline_progress_bar.set_active(True)
            self.pipeline_progress_bar.setFormat("Working")
            return

        overall = round(((stage_index + stage_progress / 100.0) / len(PIPELINE_STAGES)) * 100)
        self.pipeline_progress_bar.set_accent_role("running")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(overall)
        self.pipeline_progress_bar.set_active(True)
        self.pipeline_progress_bar.setFormat("%p%")

    def _set_pipeline_overview_compact(self, compact: bool) -> None:
        # Keep both columns governed by the available workspace geometry. Fixed
        # heights here made the visible pipeline grow when execution or review
        # content replaced the video queue.
        self.automation_input_stack.setMinimumHeight(
            self._automation_input_default_minimum_height
        )
        self.automation_input_stack.setMaximumHeight(
            self._automation_input_default_maximum_height
        )
        self.automation_console_panel.setMinimumHeight(
            self._automation_console_default_minimum_height
        )
        self.automation_console_panel.setMaximumHeight(
            self._automation_console_default_maximum_height
        )

    def complete_pipeline(self, status_text: str = "Pipeline complete") -> None:
        self._pipeline_running = False
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        self.pipeline_review_panel.hide()
        self.pipeline_activity_panel.show()
        for index, (card, label, review_label) in enumerate(
            zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_status_labels,
                self.pipeline_stage_review_labels,
                strict=True,
            )
        ):
            skipped = index in self._pipeline_skipped_stages
            card.setProperty("pipelineState", "skipped" if skipped else "complete")
            label.setText("Skipped" if skipped else "Complete")
            if review_label.text():
                review_label.setText("Not included" if skipped else "Reviewed")
            self._set_pipeline_stage_progress(
                index,
                0 if skipped else 100,
                False,
                "primary" if skipped else "ready",
                indicator_state="skipped" if skipped else "complete",
            )
            card.style().unpolish(card)
            card.style().polish(card)
        self._emphasize_pipeline_stage(None)
        self.pipeline_progress_bar.set_accent_role("ready")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(100)
        self.pipeline_progress_bar.set_active(False)
        self.pipeline_progress_bar.setFormat("%p%")
        self._set_pipeline_log_state("Complete", "complete")

    def _set_pipeline_stage_progress(
        self,
        stage_index: int,
        value: float | None,
        active: bool,
        accent_role: str,
        *,
        indicator_state: str | None = None,
    ) -> None:
        if not 0 <= stage_index < len(self.pipeline_stage_progress_bars):
            return
        bar = self.pipeline_stage_progress_bars[stage_index]
        bar.set_accent_role(accent_role)
        if value is None:
            bar.setRange(0, 0)
        else:
            bar.setRange(0, 100)
            bar.setValue(round(max(0.0, min(100.0, value))))
        indicator_text = {
            "complete": "✓",
            "skipped": "–",
            "error": "!",
        }.get(indicator_state, str(stage_index + 1))
        bar.set_center_text(indicator_text)
        bar.set_active(active)

    def _emphasize_pipeline_stage(self, active_stage: int | None) -> None:
        """Animate a single stage forward without restarting on progress ticks."""
        if (
            self._pipeline_stage_emphasis_initialized
            and active_stage == self._pipeline_emphasized_stage
        ):
            return
        self._pipeline_stage_emphasis_initialized = True
        self._pipeline_emphasized_stage = active_stage
        self._pipeline_stage_emphasis_timer.stop()
        self._pipeline_stage_emphasis_elapsed = 0
        self._pipeline_stage_emphasis_starts = [
            (card.height(), indicator.width())
            for card, indicator in zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_progress_bars,
                strict=True,
            )
        ]
        self._pipeline_stage_emphasis_targets = [
            (138, 50) if index == active_stage else (120, 40)
            for index in range(len(self.pipeline_stage_cards))
        ]
        if active_stage is None:
            self._pipeline_stage_emphasis_targets = [
                (128, 44) for _card in self.pipeline_stage_cards
            ]
        self._pipeline_stage_emphasis_timer.start()

    def _advance_pipeline_stage_emphasis(self) -> None:
        duration_ms = 240
        self._pipeline_stage_emphasis_elapsed = min(
            duration_ms,
            self._pipeline_stage_emphasis_elapsed
            + self._pipeline_stage_emphasis_timer.interval(),
        )
        progress = self._pipeline_stage_emphasis_elapsed / duration_ms
        eased = 1.0 - (1.0 - progress) ** 3
        for card, indicator, start, target in zip(
            self.pipeline_stage_cards,
            self.pipeline_stage_progress_bars,
            self._pipeline_stage_emphasis_starts,
            self._pipeline_stage_emphasis_targets,
            strict=True,
        ):
            card_height = round(start[0] + (target[0] - start[0]) * eased)
            indicator_size = round(start[1] + (target[1] - start[1]) * eased)
            card.setFixedHeight(card_height)
            indicator.setFixedSize(indicator_size, indicator_size)
        if self._pipeline_stage_emphasis_elapsed >= duration_ms:
            self._pipeline_stage_emphasis_timer.stop()

    def _start_hover_preview(self, item: QListWidgetItem) -> None:
        self._release_hover_capture()
        path = Path(str(item.data(Qt.UserRole)))
        self._show_hover_card(item, path)
        self.video_hover_preview.setPixmap(QPixmap())
        if cv2 is None:
            self.video_hover_preview.setText("Preview unavailable")
            return
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            capture.release()
            self.video_hover_preview.setText("Could not play preview")
            return
        self._hover_capture = capture
        self._hover_preview_path = path
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        details = []
        if width > 0 and height > 0:
            details.append(f"{width}×{height}")
        if fps > 0:
            fps_text = f"{fps:.2f}".rstrip("0").rstrip(".")
            details.append(f"{fps_text} fps")
        if duration > 0:
            details.append(f"{duration:.1f} s")
        details.append(self._format_file_size(path.stat().st_size))
        self.video_hover_details.setText("  •  ".join(details))
        interval = round(1000 / fps) if fps > 0 else 83
        self._hover_preview_timer.start(max(33, min(150, interval)))
        self._advance_hover_preview()

    def _advance_hover_preview(self) -> None:
        capture = self._hover_capture
        if capture is None:
            return
        success, frame = capture.read()
        if not success or frame is None:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = capture.read()
        if not success or frame is None:
            self._release_hover_capture()
            self.video_hover_preview.setPixmap(QPixmap())
            self.video_hover_preview.setText("Could not play preview")
            return
        self._render_hover_preview_frame(frame)

    def _stop_hover_preview(self) -> None:
        self._release_hover_capture()
        self.video_hover_card.hide()

    def _release_hover_capture(self) -> None:
        self._hover_preview_timer.stop()
        if self._hover_capture is not None:
            self._hover_capture.release()
        self._hover_capture = None
        self._hover_preview_path = None

    def _show_hover_card(self, item: QListWidgetItem, path: Path) -> None:
        display_name = path.name if len(path.name) <= 36 else f"{path.stem[:29]}…{path.suffix}"
        self.video_hover_name.setText(display_name)
        self.video_hover_name.setToolTip(str(path))
        self.video_hover_details.setText("Double-click for expanded preview")
        viewport = self.video_list.viewport()
        item_rect = self.video_list.visualItemRect(item)
        margin = 8
        x = max(margin, viewport.width() - self.video_hover_card.width() - margin)
        y = item_rect.bottom() + 5
        if y + self.video_hover_card.height() > viewport.height() - margin:
            y = item_rect.top() - self.video_hover_card.height() - 5
        y = max(margin, y)
        self.video_hover_card.move(x, y)
        self.video_hover_card.raise_()
        self.video_hover_card.show()

    @staticmethod
    def _format_file_size(size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def _render_hover_preview_frame(self, frame) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.video_hover_preview.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_hover_preview.setText("")
        self.video_hover_preview.setPixmap(pixmap)

    def _open_large_video_preview(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.video_list.currentItem()
        if item is None:
            return
        path = Path(str(item.data(Qt.UserRole)))
        try:
            dialog = AutomationVideoPreviewDialog(path, self)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not preview video", str(exc))
            return
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        self._large_preview_dialog = dialog
        dialog.finished.connect(
            lambda _result, closed_dialog=dialog: self._large_preview_closed(closed_dialog)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _large_preview_closed(self, dialog: AutomationVideoPreviewDialog) -> None:
        if self._large_preview_dialog is dialog:
            self._large_preview_dialog = None

    def closeEvent(self, event) -> None:
        self._pipeline_demo_timer.stop()
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.request_cancel()
            self._pipeline_worker.wait()
        self._release_hover_capture()
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        if self._large_review_dialog is not None:
            self._large_review_dialog.close()
        super().closeEvent(event)
