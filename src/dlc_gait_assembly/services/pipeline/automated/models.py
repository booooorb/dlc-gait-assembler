"""Typed values emitted by the automated pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.services.pipeline.automated.stages import AutomatedStage

ReviewKind = Literal["videos", "stickplots", "none"]


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


@dataclass(frozen=True)
class AutomatedPipelineResult:
    output_folder: Path
    output_manifest: Path
    processed_videos: tuple[Path, ...]
    coordinate_csvs: tuple[Path, ...]
    labeled_videos: tuple[Path, ...]
    stickplots: tuple[Path, ...]
    analysis_outputs: tuple[Path, ...]
