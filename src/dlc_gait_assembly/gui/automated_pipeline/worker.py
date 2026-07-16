from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.services.automated_profiles import AutomatedPipelineProfile
from dlc_gait_assembly.services.pipeline.automated import AutomatedPipelineRun


REVIEW_STAGES = {0, 1, 3}


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
    ):
        super().__init__(parent)
        self._profile = profile
        self._video_paths = video_paths
        self._project_root = project_root
        self._enable_knee_correction = enable_knee_correction
        self._enable_gait_analysis = enable_gait_analysis
        self._cancel_requested = Event()
        self._review_released = Event()
        self._review_approved = False
        self._waiting_for_review = False

    @property
    def waiting_for_review(self) -> bool:
        return self._waiting_for_review

    def request_cancel(self) -> None:
        self._cancel_requested.set()
        self._review_released.set()

    def approve_review(self) -> None:
        self._review_approved = True
        self._review_released.set()

    def reject_review(self) -> None:
        self._review_approved = False
        self._review_released.set()

    def run(self) -> None:
        stage_index = -1
        try:
            pipeline = AutomatedPipelineRun(
                self._profile,
                self._video_paths,
                self._project_root,
                enable_knee_correction=self._enable_knee_correction,
                enable_gait_analysis=self._enable_gait_analysis,
            )
            self.output_folder_ready.emit(pipeline.output_folder)
            self.log_message.emit(f"Output folder: {pipeline.output_folder}")
            for stage_index, label in enumerate(
                (
                    "Video processing",
                    "DeepLabCut analysis",
                    "Knee correction",
                    "Stickplot generation",
                    "Gait analysis",
                )
            ):
                if self._cancel_requested.is_set():
                    self.run_cancelled.emit()
                    return
                self.stage_started.emit(stage_index, label)
                stage_enabled = pipeline.stage_enabled(stage_index)
                self.log_message.emit(
                    f"Started {label}" if stage_enabled else pipeline.stage_skip_reason(stage_index)
                )
                pipeline.run_stage(
                    stage_index,
                    lambda current, total, message, stage=stage_index: self.stage_progress.emit(
                        stage, current, total, message
                    ),
                )
                if not stage_enabled:
                    reason = pipeline.stage_skip_reason(stage_index)
                    self.stage_skipped.emit(stage_index, reason)
                    self.log_message.emit(f"Skipped {label}")
                    continue
                self.stage_progress.emit(stage_index, 1, 1, f"{label} complete")
                self.log_message.emit(f"Completed {label}")

                if self._cancel_requested.is_set():
                    self.run_cancelled.emit()
                    return

                if stage_index in REVIEW_STAGES:
                    self._waiting_for_review = True
                    self._review_approved = False
                    self._review_released.clear()
                    self.review_requested.emit(stage_index, pipeline.review_artifacts(stage_index))
                    self._review_released.wait()
                    self._waiting_for_review = False
                    if self._cancel_requested.is_set() or not self._review_approved:
                        self.run_cancelled.emit()
                        return
                    self.log_message.emit(f"Approved {label} review")

            self.run_completed.emit(pipeline.result())
        except Exception as exc:
            self.run_failed.emit(stage_index, str(exc))
