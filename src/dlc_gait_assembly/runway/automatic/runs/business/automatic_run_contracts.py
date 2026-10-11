"""Define automatic run requests, accumulated stage artifacts, and final outcomes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class AutomatedPipelineResult:
    output_folder: Path
    output_manifest: Path
    processed_videos: tuple[Path, ...]
    coordinate_csvs: tuple[Path, ...]
    labeled_videos: tuple[Path, ...]
    stickplots: tuple[Path, ...]
    analysis_outputs: tuple[Path, ...]
