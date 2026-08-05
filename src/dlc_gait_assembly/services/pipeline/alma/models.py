"""Dependency-light ALMA settings and result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AnalysisType = Literal["Treadmill", "Spontaneous walking"]
CalibrationMethod = Literal["reference", "manual"]
InputMode = Literal["Multi side view", "Single side view", "Three-view", "Single-side ALMA"]
LesionHemisphere = Literal["left", "right", "none", "unknown"]
ALMA_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")


@dataclass(frozen=True)
class AlmaSettings:
    input_mode: InputMode = "Multi side view"
    analysis_type: AnalysisType = "Treadmill"
    frame_rate: float = 120.0
    filter_cutoff: float = 6.0
    treadmill_speed_cm_s: float = 30.0
    calibration_method: CalibrationMethod = "reference"
    reference_segment: str = "ankle_toe"
    reference_length_cm: float = 1.5
    calibration_map_path: Path | None = None
    right_to_left: bool | str = False
    pixels_per_cm: float | None = None
    no_outlier_filter: bool = False
    dragging_filter: bool = False
    likelihood_threshold: float = 0.5
    drag_clearance_cm: float = 0.1
    drag_min_consecutive_frames: int = 4
    step_height_min_cm: float = 0.0
    step_height_max_cm: float = 2.0
    stride_length_min_cm: float = 0.0
    stride_length_max_cm: float = 8.0
    n_continuous_strides: int = 10
    generate_stickplot: bool = True
    generate_alma_representations: bool = True
    generate_rustlab1_parameters: bool = True
    custom_bodypart_mapping: dict[str, str] | None = None
    view_bodypart_mapping: dict[str, object] | None = None
    stroke_analysis_enabled: bool = True
    stroke_likelihood_threshold: float = 0.95
    max_interpolation_gap_frames: int = 5
    swing_speed_threshold_cm_s: float = 10.0
    minimum_synchronized_cycles: int = 5
    view_calibration: dict[str, object] | None = None


@dataclass(frozen=True)
class StrokeStudyMetadata:
    """Animal/session identifiers carried into every scientific output row."""

    animal_id: str = ""
    group: str = ""
    sex: str = ""
    lesion_hemisphere: LesionHemisphere = "unknown"
    timepoint: str = ""
    trial: str = ""
    session_id: str = ""


@dataclass(frozen=True)
class AlmaRunResult:
    input_file: Path
    output_files: tuple[Path, ...]
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlmaViewCsvSet:
    name: str
    left_csv: Path
    right_csv: Path
    bottom_csv: Path
    metadata: StrokeStudyMetadata | None = None

    @property
    def alma_csv(self) -> Path:
        return self.left_csv
