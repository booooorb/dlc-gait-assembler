"""Present started, skipped, active, and completed automatic-stage progress."""

from __future__ import annotations

from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import (
    PIPELINE_REVIEW_GATES,
    PIPELINE_STAGE_ACTIVITY,
    PIPELINE_STAGE_LABELS,
)


class AutomaticStageProgress:
    """AutomaticStageProgress operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _pipeline_stage_started(self, stage_index: int, label: str) -> None:
        activity = PIPELINE_STAGE_ACTIVITY[stage_index]
        self.view.set_pipeline_stage(
            stage_index,
            progress=0,
            processed_videos=0 if stage_index == 0 else None,
            total_videos=len(self.view._video_paths) if stage_index == 0 else None,
            status_text=activity,
        )
        self.view.pipeline_current_stage_label.setText(activity)
        self.view.pipeline_current_stage_label.setToolTip("")
        self.view.runs._set_run_readiness(label, "running")

    def _pipeline_stage_progressed(self, stage_index: int, current: int, total: int, message: str) -> None:
        progress = None if total <= 0 else max(0, current) / max(1, total) * 100.0
        activity = message or PIPELINE_STAGE_ACTIVITY[stage_index]
        compact_activity = activity
        if stage_index in (1, 3) and ":" in compact_activity:
            compact_activity = compact_activity.split(":", 1)[0]
        self.view.set_pipeline_stage(
            stage_index,
            progress=progress,
            processed_videos=current if stage_index == 0 else None,
            total_videos=total if stage_index == 0 else None,
            status_text=compact_activity,
        )
        self.view.pipeline_current_stage_label.setText(activity)
        self.view.pipeline_current_stage_label.setToolTip(activity)
        if message and stage_index != 1:
            self.view.run_log._append_console(f"[{PIPELINE_STAGE_LABELS[stage_index]}] {message}.")

    def _pipeline_stage_skipped(self, stage_index: int, reason: str) -> None:
        self.view._pipeline_skipped_stages.add(stage_index)
        card = self.view.pipeline_stage_cards[stage_index]
        card.setProperty("pipelineState", "skipped")
        card.style().unpolish(card)
        card.style().polish(card)
        self.view.pipeline_stage_status_labels[stage_index].setText("Skipped")
        if stage_index in PIPELINE_REVIEW_GATES:
            self.view.pipeline_stage_review_labels[stage_index].setText("Not included")
        self._set_pipeline_stage_progress(stage_index, 0, False, "primary", indicator_state="skipped")
        self.view.run_log._append_console(f"[Skipped] {reason}.")

    def _set_pipeline_overview_compact(self, compact: bool) -> None:
        self.view.automation_input_stack.setMinimumHeight(self.view._automation_input_default_minimum_height)
        self.view.automation_input_stack.setMaximumHeight(self.view._automation_input_default_maximum_height)
        self.view.automation_console_panel.setMinimumHeight(self.view._automation_console_default_minimum_height)
        self.view.automation_console_panel.setMaximumHeight(self.view._automation_console_default_maximum_height)

    def _set_pipeline_stage_progress(
        self,
        stage_index: int,
        value: float | None,
        active: bool,
        accent_role: str,
        *,
        indicator_state: str | None = None,
    ) -> None:
        if not 0 <= stage_index < len(self.view.pipeline_stage_progress_bars):
            return
        bar = self.view.pipeline_stage_progress_bars[stage_index]
        bar.set_accent_role(accent_role)
        if value is None:
            bar.setRange(0, 0)
        else:
            bar.setRange(0, 100)
            bar.setValue(round(max(0.0, min(100.0, value))))
        indicator_text = {"complete": "✓", "skipped": "–", "error": "!"}.get(indicator_state, str(stage_index + 1))
        bar.set_center_text(indicator_text)
        bar.set_active(active)

    def _emphasize_pipeline_stage(self, active_stage: int | None) -> None:
        """Animate a single stage forward without restarting on progress ticks."""
        if self.view._pipeline_stage_emphasis_initialized and active_stage == self.view._pipeline_emphasized_stage:
            return
        self.view._pipeline_stage_emphasis_initialized = True
        self.view._pipeline_emphasized_stage = active_stage
        self.view._pipeline_stage_emphasis_timer.stop()
        self.view._pipeline_stage_emphasis_elapsed = 0
        self.view._pipeline_stage_emphasis_starts = [
            (card.height(), indicator.width())
            for (card, indicator) in zip(
                self.view.pipeline_stage_cards, self.view.pipeline_stage_progress_bars, strict=True
            )
        ]
        self.view._pipeline_stage_emphasis_targets = [
            (138, 50) if index == active_stage else (120, 40) for index in range(len(self.view.pipeline_stage_cards))
        ]
        if active_stage is None:
            self.view._pipeline_stage_emphasis_targets = [(128, 44) for _card in self.view.pipeline_stage_cards]
        self.view._pipeline_stage_emphasis_timer.start()

    def _advance_pipeline_stage_emphasis(self) -> None:
        duration_ms = 240
        self.view._pipeline_stage_emphasis_elapsed = min(
            duration_ms,
            self.view._pipeline_stage_emphasis_elapsed + self.view._pipeline_stage_emphasis_timer.interval(),
        )
        progress = self.view._pipeline_stage_emphasis_elapsed / duration_ms
        eased = 1.0 - (1.0 - progress) ** 3
        for card, indicator, start, target in zip(
            self.view.pipeline_stage_cards,
            self.view.pipeline_stage_progress_bars,
            self.view._pipeline_stage_emphasis_starts,
            self.view._pipeline_stage_emphasis_targets,
            strict=True,
        ):
            card_height = round(start[0] + (target[0] - start[0]) * eased)
            indicator_size = round(start[1] + (target[1] - start[1]) * eased)
            card.setFixedHeight(card_height)
            indicator.setFixedSize(indicator_size, indicator_size)
        if self.view._pipeline_stage_emphasis_elapsed >= duration_ms:
            self.view._pipeline_stage_emphasis_timer.stop()
