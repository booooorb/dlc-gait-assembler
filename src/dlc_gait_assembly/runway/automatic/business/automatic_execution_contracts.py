"""Define shared automatic-stage events, artifact reviews, and review decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AutomatedStage
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import DEFAULT_FINE_TUNE_EPOCHS
from dlc_gait_assembly.runway.automatic.review.business.automatic_label_correction import LabelEdit, LabelReviewSource
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings

ReviewKind = Literal["videos", "stickplots", "none"]


class AutomaticReviewDecision(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"
    CORRECT_LABELS = "correct_labels"


@dataclass(frozen=True)
class ReviewArtifact:
    path: Path
    title: str
    view: str | None = None


@dataclass(frozen=True)
class StageReview:
    stage: AutomatedStage
    kind: ReviewKind
    items: tuple[ReviewArtifact, ...] = ()
    label_sources: tuple[LabelReviewSource, ...] = ()
    knee_settings: KneeCorrectionSettings | None = None
    fine_tune_epochs: int = DEFAULT_FINE_TUNE_EPOCHS
    label_draft: tuple[LabelEdit, ...] = ()
    label_error: str = ""
