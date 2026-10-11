"""Define shared automatic-stage events, artifact reviews, and review decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AutomatedStage

ReviewKind = Literal["videos", "stickplots", "none"]


class AutomaticReviewDecision(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


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
