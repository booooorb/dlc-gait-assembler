"""Bridge automatic execution, cancellation, and review waiting into Qt signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import AutomaticReviewDecision
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.runs.business.automatic_execution_control import (
    AutomaticExecutionControl,
    AutomaticExecutionEvents,
    AutomaticRunCancelled,
)
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_coordinator import execute_automatic_run


class AutomatedPipelineWorker(QThread):
    output_folder_ready = Signal(object)
    stage_started = Signal(int, str)
    stage_progress = Signal(int, int, int, str)
    stage_skipped = Signal(int, str)
    log_message = Signal(str)
    review_requested = Signal(int, object)
    run_completed = Signal(object)
    run_failed = Signal(int, str)
    run_cancelled = Signal()

    def __init__(
        self,
        profile: AutomatedPipelineProfile,
        video_paths: list[Path],
        project_root: Path,
        enable_knee_correction: bool = True,
        enable_gait_analysis: bool = True,
        parent=None,
        *,
        run_factory,
        output_root=None,
    ):
        super().__init__(parent)
        self.setStackSize(8 * 1024 * 1024)
        self.run_factory = run_factory
        self.output_root = output_root
        self._profile = profile
        self._video_paths = video_paths
        self._project_root = project_root
        self._enable_knee_correction = enable_knee_correction
        self._enable_gait_analysis = enable_gait_analysis
        self.execution_control = AutomaticExecutionControl()

    @property
    def waiting_for_review(self) -> bool:
        return self.execution_control.waiting_for_review

    def request_cancel(self) -> None:
        self.execution_control.request_cancel()

    def approve_review(self) -> None:
        self.execution_control.decide_review(AutomaticReviewDecision.APPROVE)

    def reject_review(self) -> None:
        self.execution_control.decide_review(AutomaticReviewDecision.REJECT)

    def run(self) -> None:
        try:
            pipeline = self.run_factory(
                self._profile,
                self._video_paths,
                self._project_root,
                output_root=self.output_root,
                enable_knee_correction=self._enable_knee_correction,
                enable_gait_analysis=self._enable_gait_analysis,
            )
            self.output_folder_ready.emit(pipeline.output_folder)
            self.log_message.emit(f"Output folder: {pipeline.output_folder}")
            events = AutomaticExecutionEvents(
                self.stage_started.emit,
                self.stage_progress.emit,
                self.stage_skipped.emit,
                self.log_message.emit,
                self.review_requested.emit,
            )
            result = execute_automatic_run(pipeline, events, self.execution_control)
            self.run_completed.emit(result)
        except AutomaticRunCancelled:
            self.run_cancelled.emit()
        except Exception as exc:
            self.run_failed.emit(self.execution_control.current_stage, str(exc))
