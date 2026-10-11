"""Define Ladder detection settings, events, output schemas, and single/dual-view results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

LadderDetectionMethod = Literal["Deviation", "Baseline", "Threshold"]
LadderClassification = Literal["unreviewed", "footfall", "slip", "fall"]
LadderView = Literal["single", "left", "right"]
LADDER_OUTPUT_COLUMNS = (
    "time (frame)",
    "depth (pixel)",
    "start (frame)",
    "end (frame)",
    "duration (s)",
    "bodypart",
    "slip or fall",
)
COMBINED_LADDER_OUTPUT_COLUMNS = (*LADDER_OUTPUT_COLUMNS, "view", "source file")


@dataclass(frozen=True)
class LadderSettings:
    """Settings used by ALMA's ladder-rung footfall detector."""

    method: LadderDetectionMethod = "Deviation"
    frame_rate: float = 120.0
    likelihood_threshold: float = 0.1
    depth_threshold: float = 0.8
    threshold: float | None = None
    baseline_window_frames: int | None = None


@dataclass(frozen=True)
class LadderEvent:
    bodypart: str
    peak_frame: int
    start_frame: int
    end_frame: int
    peak_y_px: float
    depth_px: float
    duration_s: float
    classification: LadderClassification = "unreviewed"
    included: bool = True
    view: LadderView = "single"
    source_file: str = ""


@dataclass(frozen=True)
class LadderRunResult:
    input_file: Path
    output_file: Path
    events: tuple[LadderEvent, ...]


@dataclass(frozen=True)
class DualLadderRunResult:
    left_result: LadderRunResult
    right_result: LadderRunResult
    output_file: Path
    events: tuple[LadderEvent, ...]
