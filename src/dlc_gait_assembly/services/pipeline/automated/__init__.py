"""Automated pipeline orchestration and typed stage contracts."""

from dlc_gait_assembly.services.pipeline.automated.models import (
    AutomatedPipelineResult,
    ReviewArtifact,
    StageReview,
)
from dlc_gait_assembly.services.pipeline.automated.run import AutomatedPipelineRun
from dlc_gait_assembly.services.pipeline.automated.stages import (
    AUTOMATED_STAGE_SPECS,
    AutomatedStage,
    StageSpec,
    coerce_automated_stage,
    stage_spec,
)

__all__ = [
    "AUTOMATED_STAGE_SPECS",
    "AutomatedPipelineResult",
    "AutomatedPipelineRun",
    "AutomatedStage",
    "ReviewArtifact",
    "StageReview",
    "StageSpec",
    "coerce_automated_stage",
    "stage_spec",
]
