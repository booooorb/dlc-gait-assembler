"""Single source of truth for automated pipeline stage identity and order."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal


class AutomatedStage(IntEnum):
    VIDEO_PROCESSING = 0
    DEEPLABCUT_ANALYSIS = 1
    KNEE_CORRECTION = 2
    LABELED_VIDEOS = 3
    STICKPLOT = 4
    GAIT_ANALYSIS = 5


@dataclass(frozen=True)
class StageSpec:
    stage: AutomatedStage
    label: str
    completion_label: str
    short_label: str
    preview_message: str
    activity: str
    review_kind: Literal["videos", "stickplots"] | None = None


AUTOMATED_STAGE_SPECS = (
    StageSpec(
        AutomatedStage.VIDEO_PROCESSING,
        "Video processing",
        "Video processing",
        "Process videos",
        "Preparing and processing source videos",
        "Processing",
        "videos",
    ),
    StageSpec(
        AutomatedStage.DEEPLABCUT_ANALYSIS,
        "DeepLabCut analysis",
        "DLC analyzing videos",
        "DLC analysis",
        "Running DeepLabCut pose estimation",
        "Analyzing poses",
    ),
    StageSpec(
        AutomatedStage.KNEE_CORRECTION,
        "Knee correction",
        "Triangulate knee coordinate",
        "Triangulate knee",
        "Triangulating the knee coordinate",
        "Triangulating knee",
    ),
    StageSpec(
        AutomatedStage.LABELED_VIDEOS,
        "Labeled video creation",
        "Create labeled videos",
        "Create videos",
        "Creating labeled review videos",
        "Creating videos",
        "videos",
    ),
    StageSpec(
        AutomatedStage.STICKPLOT,
        "Stickplot generation",
        "Stickplot generation",
        "Make stickplot",
        "Generating gait stickplots",
        "Generating",
        "stickplots",
    ),
    StageSpec(
        AutomatedStage.GAIT_ANALYSIS,
        "Gait analysis",
        "Gait analysis",
        "Gait analysis",
        "Running gait analysis",
        "Analyzing gait",
    ),
)


def coerce_automated_stage(value: int | AutomatedStage) -> AutomatedStage:
    try:
        return AutomatedStage(value)
    except ValueError as exc:
        raise ValueError(f"Unknown automated pipeline stage: {value}") from exc


def stage_spec(value: int | AutomatedStage) -> StageSpec:
    return AUTOMATED_STAGE_SPECS[int(coerce_automated_stage(value))]
