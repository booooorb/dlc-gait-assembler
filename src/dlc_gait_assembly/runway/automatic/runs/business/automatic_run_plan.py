"""Resolve the six automatic stages and optional-stage skip decisions."""

from __future__ import annotations

from dataclasses import dataclass

from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import (
    AutomatedStage,
    coerce_automated_stage,
)
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile


@dataclass(frozen=True)
class AutomaticRunPlan:
    profile: AutomatedPipelineProfile
    enable_knee_correction: bool = True
    enable_gait_analysis: bool = True

    def stage_enabled(self, stage_index: int | AutomatedStage) -> bool:
        stage = coerce_automated_stage(stage_index)
        if stage is AutomatedStage.KNEE_CORRECTION:
            return (
                self.enable_knee_correction
                and self.profile.knee_correction_enabled
                and (self.profile.knee_manifest is not None)
            )
        if stage in (AutomatedStage.STICKPLOT, AutomatedStage.GAIT_ANALYSIS):
            return (
                self.enable_gait_analysis
                and self.profile.gait_analysis_enabled
                and (self.profile.analysis_manifest is not None)
                and (self.profile.calibration_map is not None)
            )
        return True

    def stage_skip_reason(self, stage_index: int | AutomatedStage) -> str:
        stage = coerce_automated_stage(stage_index)
        if stage is AutomatedStage.KNEE_CORRECTION:
            if not self.enable_knee_correction:
                return "Knee correction disabled for this run"
            if not self.profile.knee_correction_enabled:
                return "Knee correction excluded from this profile"
            return "No knee correction manifest in the profile"
        if stage in (AutomatedStage.STICKPLOT, AutomatedStage.GAIT_ANALYSIS):
            if not self.enable_gait_analysis:
                return "Gait analysis disabled for this run"
            return "Gait analysis excluded from this profile"
        return "Stage disabled for this run"
