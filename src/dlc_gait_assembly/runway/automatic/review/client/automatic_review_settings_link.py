"""Request the appropriate manual-stage page when reviewed artifacts need correction."""

from __future__ import annotations

from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import PIPELINE_REVIEW_GATES
from dlc_gait_assembly.runway.automatic.review.business.automatic_review_rules import review_remediation_stage


class AutomaticReviewSettingsLink:
    """AutomaticReviewSettingsLink operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _open_pipeline_fix_settings(self) -> None:
        stage_index = self.view._pipeline_demo_blocked_stage
        if stage_index is None:
            return
        if self.view._pipeline_review_artifacts is not None:
            stage = self.view._pipeline_review_artifacts.stage
            self.view.manual_tool_requested.emit(review_remediation_stage(stage))
        else:
            gate = PIPELINE_REVIEW_GATES[stage_index]
            self.view.profiles._show_profile_configuration()
            self.view.configuration_tabs.setCurrentIndex(int(gate["tab"]))
