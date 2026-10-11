"""Define ALMA analysis settings and translate already-loaded scientific defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AnalysisType = Literal["Treadmill", "Spontaneous walking"]
CalibrationMethod = Literal["reference", "manual"]
InputMode = Literal["Multi side view", "Single side view", "Three-view", "Single-side ALMA"]
LimbScope = Literal["Hindlimb", "Hindlimb + Forelimb"]
LesionHemisphere = Literal["left", "right", "none", "unknown"]
ALMA_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")


@dataclass(frozen=True)
class AlmaSettings:
    input_mode: InputMode = "Multi side view"
    limb_scope: LimbScope = "Hindlimb"
    analysis_type: AnalysisType = "Treadmill"
    stride_detection_method: str = "ALMA (legacy)"
    mixture_context_ms: float = 60.0
    stance_speed_threshold_px_frame: float = 7.0
    maximum_tracking_speed_px_frame: float = 100.0
    minimum_stance_frames: int = 1
    minimum_swing_frames: int = 1
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
    stroke_likelihood_threshold: float = 0.5
    max_interpolation_gap_frames: int = -1  # Auto: short internal gaps, at most 50 ms.
    swing_speed_threshold_cm_s: float = 10.0
    minimum_synchronized_cycles: int = 5
    view_calibration: dict[str, object] | None = None
    view_timing: dict[str, object] | None = None
    enabled_parameter_names: tuple[str, ...] | None = None


def settings_from_alma_config(config: dict) -> AlmaSettings:
    right_to_left = config.get("right_to_left", False)
    if isinstance(right_to_left, str):
        right_to_left = "auto" if right_to_left.lower() == "auto" else coerce_bool(right_to_left)
    pixels_per_cm = config.get("pixels_per_cm", None)
    if pixels_per_cm == "":
        pixels_per_cm = None
    cm_speed = config.get("cm_speed", None)
    if cm_speed in (None, ""):
        cm_speed = 30.0
    reference_length_cm = config.get("reference_length_cm", 1.5)
    if reference_length_cm == "":
        reference_length_cm = 1.5
    auto_calibrate_spatial = coerce_bool(config.get("auto_calibrate_spatial", True), default=True)
    likelihood_threshold = config.get("kinematics_likelihood_threshold", 0.5)
    if likelihood_threshold == "":
        likelihood_threshold = 0.5
    return AlmaSettings(
        limb_scope="Hindlimb + Forelimb"
        if str(config.get("limb_scope", "Hindlimb")).strip().casefold() == "hindlimb + forelimb".casefold()
        else "Hindlimb",
        frame_rate=float(config.get("frame_rate", 120.0)),
        filter_cutoff=float(config.get("lowpass_filter_cutoff", 6.0)),
        treadmill_speed_cm_s=float(cm_speed),
        calibration_method="reference" if auto_calibrate_spatial else "manual",
        reference_segment=str(config.get("reference_segment", "ankle_toe")),
        reference_length_cm=float(reference_length_cm),
        right_to_left=right_to_left,
        pixels_per_cm=None if pixels_per_cm is None else float(pixels_per_cm),
        no_outlier_filter=coerce_bool(config.get("no_outlier_filter", False)),
        dragging_filter=coerce_bool(config.get("dragging_filter", False)),
        likelihood_threshold=float(likelihood_threshold),
        drag_clearance_cm=float(config.get("drag_clearance_cm", 0.1)),
        drag_min_consecutive_frames=int(config.get("drag_min_consecutive_frames", 4)),
        step_height_min_cm=float(config.get("step_height_min_cm", 0.0)),
        step_height_max_cm=float(config.get("step_height_max_cm", 2.0)),
        stride_length_min_cm=float(config.get("stride_length_min_cm", 0.0)),
        stride_length_max_cm=float(config.get("stride_length_max_cm", 8.0)),
        generate_alma_representations=coerce_bool(config.get("generate_alma_representations", True), default=True),
        generate_rustlab1_parameters=coerce_bool(config.get("generate_rustlab1_parameters", True), default=True),
        stroke_analysis_enabled=coerce_bool(config.get("stroke_analysis_enabled", True), default=True),
        stroke_likelihood_threshold=float(likelihood_threshold),
        max_interpolation_gap_frames=int(config.get("max_interpolation_gap_frames", -1)),
        swing_speed_threshold_cm_s=float(config.get("swing_speed_threshold_cm_s", 10.0)),
        minimum_synchronized_cycles=int(config.get("minimum_synchronized_cycles", 5)),
        view_calibration=config.get("view_calibration"),
        view_timing=config.get("view_timing"),
    )


def coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)
