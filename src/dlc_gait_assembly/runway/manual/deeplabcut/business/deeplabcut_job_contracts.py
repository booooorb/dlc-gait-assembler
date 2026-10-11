"""Define DeepLabCut analysis/labeled-video jobs, model metadata, and produced artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DlcAnalysisJob:
    region: str
    model_path: Path
    video_paths: tuple[Path, ...]


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
