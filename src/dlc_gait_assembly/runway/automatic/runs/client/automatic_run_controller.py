"""Coordinate video-run readiness, execution, cancellation, completion, and review handoffs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import StageReview
from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import RUN_PREVIEW_TOOLTIP
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_history_dialog import AutomaticRunHistoryDialog
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_worker import AutomatedPipelineWorker


class AutomaticRunController:
    """AutomaticRunController operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _set_run_readiness(self, text: str, state: str) -> None:
        self.view.run_readiness_label.setText(f"●  {text}" if state != "ready" else "")
        self.view.run_readiness_label.setVisible(state != "ready")
        self.view.run_readiness_label.setProperty("readinessState", state)
        self.view.run_readiness_label.style().unpolish(self.view.run_readiness_label)
        self.view.run_readiness_label.style().polish(self.view.run_readiness_label)

    def _toggle_pipeline_run(self) -> None:
        worker = self.view._pipeline_worker
        if worker is not None:
            if not worker.isRunning():
                return
            worker.request_cancel()
            self.view.run_pipeline_button.setText("Pausing")
            self.view.run_pipeline_button.setEnabled(False)
            self._set_run_readiness("Pausing", "running")
            self.view.run_log._append_console("[Pipeline] Pause requested. Saving completed work.")
            return
        if self.view._pipeline_real_complete:
            self.view._pipeline_real_complete = False
            self.view._pipeline_demo_blocked_stage = None
            self.view._pipeline_demo_waiting_for_review = None
            self.view.set_pipeline_running(False)
            self.view.run_pipeline_button.setText("Run pipeline")
            self.view.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.view.run_pipeline_button.setEnabled(True)
            self.view.resume_pipeline_button.hide()
            self._set_run_readiness("Ready", "ready")
            return
        workflow = getattr(self.view, "workflow_controller", None)
        if workflow is not None:
            if workflow.active is None:
                workflow.window.routes._show_automated_pipeline()
                return
            if not self.view._video_paths:
                QMessageBox.information(self.view, "Add videos", "Add videos to this workflow before starting automation.")
                return
            if not workflow.confirm_save_before_run():
                return
            profile = workflow.active
        else:
            profile = self.view.profile_state.profiles.get(self.view.profile_state.current_profile_id or "")
        if profile is None or not self.view._video_paths:
            self.view.demo._toggle_pipeline_demo()
            return
        missing = self.view.profile_use_cases.missing_requirements(profile)
        if missing:
            QMessageBox.warning(
                self.view,
                "Profile setup incomplete",
                "Complete these profile settings before running:\n• " + "\n• ".join(missing),
            )
            self.view.profiles._show_profile_configuration()
            return
        self._start_pipeline(profile)

    def show_run_history(self, _checked=False, *, parent=None, resume=None):
        if self.view._pipeline_worker is not None:
            return
        try:
            runs = self.view.run_history(self.view._automated_output_root)
        except OSError as exc:
            QMessageBox.warning(parent or self.view, "Could not open run history", str(exc))
            return
        dialog = AutomaticRunHistoryDialog(parent or self.view, runs, open_outputs=self._open_folder)
        if dialog.exec() and dialog.selected_run is not None:
            (resume or self.resume_saved)(dialog.selected_run)

    def resume_saved(self, run):
        if self.view._pipeline_worker is None and run.can_resume:
            self._start_pipeline(None, resume_folder=run.output_folder, video_count=run.video_count)

    def resume_recent(self):
        folder = self.view._pipeline_output_folder
        if folder is not None and self.view._pipeline_worker is None:
            self._start_pipeline(None, resume_folder=folder, video_count=self.view._run_video_count)

    def _start_pipeline(self, profile: AutomatedPipelineProfile | None, *, resume_folder=None, video_count=None) -> None:
        self.view._run_video_count = video_count
        self.view._pipeline_real_complete = False
        self.view._pipeline_real_waiting_for_review = None
        self.view._pipeline_demo_waiting_for_review = None
        self.view._pipeline_demo_blocked_stage = None
        self.view._pipeline_review_artifacts = None
        self.view._pipeline_stickplot_path = None
        self.view._pipeline_stickplot_pixmap = None
        self.view._pipeline_output_folder = None
        self.view.open_pipeline_output_button.setText("Open outputs")
        self.view.open_pipeline_output_button.setToolTip(str(self.view._automated_output_root))
        self.view._pipeline_skipped_stages.clear()
        self.view.resume_pipeline_button.hide()
        self.view.run_history_button.setEnabled(False)
        self.view.pipeline_review_panel.hide()
        self.view.automation_console.clear()
        self.view.set_pipeline_running(True)
        self.view.run_pipeline_button.setText("Pause run")
        self.view.run_pipeline_button.setToolTip("Pause at the next safe point and save progress for later.")
        self.view.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Running", "running")
        if resume_folder is not None:
            self._pipeline_output_folder_ready(resume_folder)
            self.view.run_log._append_console("[Pipeline] Resuming saved automation run.")
        else:
            self.view.run_log._append_console(
                f'[Pipeline] Running profile "{profile.name}" on {len(self.view._video_paths)} video(s).'
            )
        worker = AutomatedPipelineWorker(
            profile,
            list(self.view._video_paths),
            self.view._project_root,
            parent=self.view,
            run_factory=self.view.run_factory,
            output_root=self.view._automated_output_root,
            resume_folder=resume_folder,
        )
        self.view._pipeline_worker = worker
        worker.stage_started.connect(self.view.stage_progress._pipeline_stage_started)
        worker.output_folder_ready.connect(self._pipeline_output_folder_ready)
        worker.video_count_ready.connect(self._set_run_video_count)
        worker.stage_progress.connect(self.view.stage_progress._pipeline_stage_progressed)
        worker.stage_skipped.connect(self.view.stage_progress._pipeline_stage_skipped)
        worker.log_message.connect(lambda message: self.view.run_log._append_console(f"[Pipeline] {message}."))
        worker.review_requested.connect(self._pipeline_review_requested)
        worker.run_completed.connect(self._pipeline_run_completed)
        worker.run_failed.connect(self._pipeline_run_failed)
        worker.run_cancelled.connect(self._pipeline_run_cancelled)
        worker.finished.connect(lambda: self._pipeline_worker_finished(worker))
        worker.start()

    def _pipeline_output_folder_ready(self, output_folder: object) -> None:
        self.view._pipeline_output_folder = Path(output_folder).expanduser().resolve()
        self.view.open_pipeline_output_button.setText("Open run output")
        self.view.open_pipeline_output_button.setToolTip(str(self.view._pipeline_output_folder))
        self.view.pipeline_current_stage_label.setToolTip(str(self.view._pipeline_output_folder))

    def _open_pipeline_output(self) -> None:
        output_folder = self.view._pipeline_output_folder or self.view._automated_output_root
        self._open_folder(output_folder)

    @staticmethod
    def _open_folder(folder):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _set_run_video_count(self, count):
        self.view._run_video_count = count

    def _pipeline_review_requested(self, stage_index: int, artifacts: object) -> None:
        self.view._pipeline_real_waiting_for_review = stage_index
        self.view._pipeline_review_artifacts = artifacts if isinstance(artifacts, StageReview) else None
        self.view.reviews._pause_for_pipeline_review(stage_index, self.view._pipeline_review_artifacts)

    def _pipeline_run_completed(self, result: object) -> None:
        self.view._pipeline_real_waiting_for_review = None
        self.view._pipeline_real_complete = True
        self.view.complete_pipeline("Pipeline complete")
        self.view.run_pipeline_button.setText("Back to videos")
        self.view.run_pipeline_button.setToolTip("Return to the video queue.")
        self.view.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Complete", "complete")
        output_folder = getattr(result, "output_folder", None)
        if output_folder is not None:
            self._pipeline_output_folder_ready(output_folder)
            self.view.run_log._append_console(f"[Complete] Results saved to {output_folder}.")
        output_manifest = getattr(result, "output_manifest", None)
        if output_manifest is not None:
            self.view.run_log._append_console(f"[Complete] Run manifest: {output_manifest}.")

    def _pipeline_run_failed(self, stage_index: int, message: str) -> None:
        self.view._pipeline_real_waiting_for_review = None
        self.view._pipeline_real_complete = True
        self.view.pipeline_review_panel.hide()
        self.view.pipeline_activity_panel.show()
        self.view.pipeline_progress_bar.set_active(False)
        self.view.pipeline_progress_bar.set_accent_role("error")
        self.view.run_log._set_pipeline_log_state("Failed", "error")
        if 0 <= stage_index < len(self.view.pipeline_stage_cards):
            card = self.view.pipeline_stage_cards[stage_index]
            card.setProperty("pipelineState", "blocked")
            card.style().unpolish(card)
            card.style().polish(card)
            self.view.pipeline_stage_status_labels[stage_index].setText("Failed")
            self.view.stage_progress._set_pipeline_stage_progress(
                stage_index, 100, False, "error", indicator_state="error"
            )
        self.view.run_pipeline_button.setText("Back to videos")
        self.view.run_pipeline_button.setToolTip("Return to the video queue.")
        self.view.run_pipeline_button.setEnabled(True)
        if self.view._pipeline_output_folder is not None:
            self.view.resume_pipeline_button.setText("Retry stage")
            self.view.resume_pipeline_button.show()
            self._set_run_readiness("Run saved", "error")
        else:
            self._set_run_readiness("Failed to start", "error")
        self.view.run_log._append_console(f"[Failed] {message}")

    def _pipeline_run_cancelled(self) -> None:
        if self.view._pipeline_demo_blocked_stage is not None:
            self.view.resume_pipeline_button.setText("Resume run")
            self.view.resume_pipeline_button.setVisible(self.view._pipeline_output_folder is not None)
            return
        self.view._pipeline_real_waiting_for_review = None
        self.view._pipeline_demo_waiting_for_review = None
        self.view._pipeline_real_complete = False
        self.view.pipeline_review_panel.hide()
        self.view.set_pipeline_running(False)
        self.view.run_pipeline_button.setText("Run pipeline")
        self.view.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
        self.view.run_pipeline_button.setEnabled(True)
        self.view.resume_pipeline_button.setText("Resume run")
        self.view.resume_pipeline_button.setVisible(self.view._pipeline_output_folder is not None)
        self._set_run_readiness("Paused", "neutral")
        self.view.run_log._append_console("[Pipeline] Paused. Open Run history to resume later.")

    def _pipeline_worker_finished(self, worker: AutomatedPipelineWorker) -> None:
        if self.view._pipeline_worker is worker:
            self.view._pipeline_worker = None
            self.view.run_history_button.setEnabled(True)
        worker.deleteLater()


try:
    import cv2
except ImportError:
    cv2 = None
