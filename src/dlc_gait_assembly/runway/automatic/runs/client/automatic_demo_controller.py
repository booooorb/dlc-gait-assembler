"""Drive the automatic-workflow demonstration using packaged example artifacts."""

from __future__ import annotations

from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import (
    PIPELINE_PREVIEW_MESSAGES,
    PIPELINE_REVIEW_GATES,
    PIPELINE_STAGE_ACTIVITY,
    PIPELINE_STAGES,
    RUN_PREVIEW_TOOLTIP,
    STOP_PREVIEW_TOOLTIP,
)


class AutomaticDemoController:
    """AutomaticDemoController operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _toggle_pipeline_demo(self) -> None:
        if self.view._pipeline_demo_complete:
            self.view._pipeline_demo_complete = False
            self.view.pipeline_review_panel.hide()
            self.view.set_pipeline_running(False)
            self.view.run_pipeline_button.setText("Run pipeline")
            self.view.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.view.runs._set_run_readiness("Preview only", "neutral")
            return
        if self.view._pipeline_demo_blocked_stage is not None:
            self.view.reviews._resume_pipeline_demo()
            return
        if self.view._pipeline_demo_waiting_for_review is not None:
            return
        if self.view._pipeline_demo_timer.isActive():
            self.view._pipeline_demo_timer.stop()
            self.view._pipeline_demo_waiting_for_review = None
            self.view._pipeline_demo_blocked_stage = None
            self.view.pipeline_review_panel.hide()
            self.view.set_pipeline_running(False)
            self.view.run_pipeline_button.setText("Run pipeline")
            self.view.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.view.runs._set_run_readiness("Stopped", "neutral")
            self.view.run_log._append_console("[Preview] Stopped. No processing was performed.")
            return
        self.view._pipeline_demo_stage = 0
        self.view._pipeline_demo_progress = 0.0
        self.view._pipeline_demo_total_videos = len(self.view._video_paths) or 4
        self.view._pipeline_demo_last_processed = -1
        self.view._pipeline_demo_complete = False
        self.view._pipeline_demo_waiting_for_review = None
        self.view._pipeline_demo_blocked_stage = None
        self.view.pipeline_review_panel.hide()
        self.view.set_pipeline_running(True)
        self.view.run_pipeline_button.setText("Stop preview")
        self.view.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self.view.runs._set_run_readiness("Playing preview", "running")
        self.view.run_log._append_console("[Preview] Pipeline UI preview started; no files will be changed.")
        self._begin_pipeline_demo_stage(0)

    def _begin_pipeline_demo_stage(self, stage_index: int) -> None:
        self.view.pipeline_activity_panel.show()
        self.view._pipeline_demo_stage = stage_index
        self.view._pipeline_demo_progress = 0.0
        if stage_index == 0:
            self.view._pipeline_demo_last_processed = -1
        self.view.run_log._append_console(
            f"[{stage_index + 1}/{len(PIPELINE_STAGES)}] {PIPELINE_PREVIEW_MESSAGES[stage_index]}."
        )
        self.view.set_pipeline_stage(
            stage_index,
            progress=0,
            processed_videos=0 if stage_index == 0 else None,
            total_videos=self.view._pipeline_demo_total_videos if stage_index == 0 else None,
            status_text=PIPELINE_STAGE_ACTIVITY[stage_index],
        )
        self.view._pipeline_demo_timer.start()

    def _advance_pipeline_demo(self) -> None:
        if (
            self.view._pipeline_demo_waiting_for_review is not None
            or self.view._pipeline_demo_blocked_stage is not None
        ):
            return
        if not 0 <= self.view._pipeline_demo_stage < len(PIPELINE_STAGES):
            return
        self.view._pipeline_demo_progress = min(100.0, self.view._pipeline_demo_progress + 4.0)
        processed_videos = None
        total_videos = None
        if self.view._pipeline_demo_stage == 0:
            total_videos = self.view._pipeline_demo_total_videos
            processed_videos = min(total_videos, round(total_videos * self.view._pipeline_demo_progress / 100.0))
            if processed_videos != self.view._pipeline_demo_last_processed:
                self.view._pipeline_demo_last_processed = processed_videos
                self.view.run_log._append_console(
                    f"[Video processing] {processed_videos} / {total_videos} videos processed."
                )
        self.view.set_pipeline_stage(
            self.view._pipeline_demo_stage,
            progress=self.view._pipeline_demo_progress,
            processed_videos=processed_videos,
            total_videos=total_videos,
            status_text=PIPELINE_STAGE_ACTIVITY[self.view._pipeline_demo_stage],
        )
        if self.view._pipeline_demo_progress < 100:
            return
        completed_stage = self.view._pipeline_demo_stage
        if completed_stage in PIPELINE_REVIEW_GATES:
            self.view.reviews._pause_for_pipeline_review(completed_stage)
            return
        self.view.run_log._append_console(f"[Complete] {PIPELINE_STAGES[completed_stage]}.")
        next_stage = completed_stage + 1
        if next_stage >= len(PIPELINE_STAGES):
            self.view._pipeline_demo_timer.stop()
            self.view._pipeline_demo_complete = True
            self.view.complete_pipeline("Pipeline preview complete")
            self.view.run_pipeline_button.setText("Back to videos")
            self.view.run_pipeline_button.setToolTip(
                "Return to the queued videos after the completed walkthrough. No files were changed."
            )
            self.view.runs._set_run_readiness("Complete", "complete")
            self.view.run_log._append_console("[Preview complete] No processing was performed.")
            return
        self._begin_pipeline_demo_stage(next_stage)
