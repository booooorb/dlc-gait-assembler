"""Validate review decisions and resolve the owning remediation stage."""

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import (
    AutomaticReviewDecision,
    StageReview,
)
from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AutomatedStage


def validate_review_decision(review: StageReview, decision: AutomaticReviewDecision) -> AutomaticReviewDecision:
    if review.kind == "none":
        raise ValueError("This stage does not require review.")
    if not isinstance(decision, AutomaticReviewDecision):
        raise ValueError("Choose approve, reject, or cancel for this review.")
    return decision


def review_remediation_stage(stage: AutomatedStage) -> str:
    stages = {
        AutomatedStage.VIDEO_PROCESSING: "video_processing",
        AutomatedStage.LABELED_VIDEOS: "deeplabcut",
        AutomatedStage.STICKPLOT: "gait_parameter_analysis",
    }
    try:
        return stages[stage]
    except KeyError as exc:
        raise ValueError(f"Stage {stage} does not require review.") from exc
