"""Coordinate video-run readiness, execution, cancellation, completion, and review handoffs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import StageReview
from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import RUN_PREVIEW_TOOLTIP
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_worker import AutomatedPipelineWorker


class AutomaticRunController:
    """AutomaticRunController operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _set_run_readiness(self, text: str, state: str) -> None:
        self.view.run_readiness_label.setText(f"●  {text}")
        self.view.run_readiness_label.setProperty("readinessState", state)
        self.view.run_readiness_label.style().unpolish(self.view.run_readiness_label)
        self.view.run_readiness_label.style().polish(self.view.run_readiness_label)

    def _toggle_pipeline_run(self) -> None:
        if self.view._pipeline_worker is not None and self.view._pipeline_worker.isRunning():
            self.view._pipeline_worker.request_cancel()
            self.view.run_pipeline_button.setText("Stopping")
            self.view.run_pipeline_button.setEnabled(False)
            self._set_run_readiness("Stopping after current operation", "running")
            self.view.run_log._append_console("[Pipeline] Stop requested; waiting for the current operation.")
            return
        if self.view._pipeline_real_complete:
            self.view._pipeline_real_complete = False
            self.view._pipeline_demo_blocked_stage = None
            self.view._pipeline_demo_waiting_for_review = None
            self.view.set_pipeline_running(False)
            self.view.run_pipeline_button.setText("Run pipeline")
            self.view.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.view.run_pipeline_button.setEnabled(True)
            self._set_run_readiness("Ready", "ready")
            return
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

    def _start_pipeline(self, profile: AutomatedPipelineProfile) -> None:
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
        self.view.pipeline_review_panel.hide()
        self.view.automation_console.clear()
        self.view.set_pipeline_running(True)
        self.view.run_pipeline_button.setText("Stop pipeline")
        self.view.run_pipeline_button.setToolTip("Stop after the currently running external operation finishes.")
        self.view.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Running", "running")
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
        )
        self.view._pipeline_worker = worker
        worker.stage_started.connect(self.view.stage_progress._pipeline_stage_started)
        worker.output_folder_ready.connect(self._pipeline_output_folder_ready)
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
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_folder)))

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
        self.view.run_pipeline_button.setToolTip("Return to the queue, correct the profile, and run again.")
        self.view.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Failed", "error")
        self.view.run_log._append_console(f"[Failed] {message}")

    def _pipeline_run_cancelled(self) -> None:
        if self.view._pipeline_demo_blocked_stage is not None:
            return
        self.view._pipeline_real_waiting_for_review = None
        self.view._pipeline_real_complete = False
        self.view.pipeline_review_panel.hide()
        self.view.set_pipeline_running(False)
        self.view.run_pipeline_button.setText("Run pipeline")
        self.view.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
        self.view.run_pipeline_button.setEnabled(True)
        self._set_run_readiness("Stopped", "neutral")
        self.view.run_log._append_console("[Pipeline] Stopped.")

    def _pipeline_worker_finished(self, worker: AutomatedPipelineWorker) -> None:
        if self.view._pipeline_worker is worker:
            self.view._pipeline_worker = None
        worker.deleteLater()


try:
    import cv2
except ImportError:
    cv2 = None
