"""Define DeepLabCut analysis/labeled-video jobs, model metadata, and produced artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DlcTrainedModel:
    config_path: Path
    iteration: int
    training_fraction: float
    trainingsetindex: int
    shuffle: int
    engine_override: str | None = None

    @property
    def training_identity(self) -> tuple[int, float, int]:
        return self.iteration, self.training_fraction, self.shuffle


@dataclass(frozen=True)
class DlcAnalysisJob:
    region: str
    model_path: Path
    video_paths: tuple[Path, ...]
    labeled_video_confidence: float | None = None
    shuffle: int | None = None


@dataclass(frozen=True)
class DlcAnalysisResult:
    region: str
    video_paths: tuple[Path, ...]
    csv_paths: tuple[Path, ...]
    h5_paths: tuple[Path, ...]
    labeled_video_paths: tuple[Path, ...]


@dataclass(frozen=True)
class OrganizedManualOutputs:
    analyzed_files: tuple[Path, ...]
    labeled_videos: tuple[Path, ...]
