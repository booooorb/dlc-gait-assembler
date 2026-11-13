"""Define ALMA analysis settings and translate already-loaded scientific defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AnalysisType = Literal["Treadmill", "Spontaneous walking"]
CalibrationMethod = Literal["reference", "manual", "map", "per_view", "treadmill"]
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
    calibration_method: CalibrationMethod | None = None
    reference_segment: str = "ankle_toe"
    reference_length_cm: float = 0.0  # Requires a measured length; no anatomical default.
    calibration_map_path: Path | None = None
    right_to_left: bool | str = False
    pixels_per_cm: float | None = None
    no_outlier_filter: bool = False
    dragging_filter: bool = False
    likelihood_threshold: float = 0.5
    drag_clearance_cm: float = 0.1
    drag_min_consecutive_frames: int = 4
    runway_confidence_threshold: float = 0.6
    runway_max_gap_s: float = 0.02
    runway_min_body_speed: float = 0.25
    runway_min_contact_s: float = 0.03
    runway_joint_interpolation: Literal["none", "linear", "pchip"] = "none"
    runway_joint_max_gap_s: float = 0.02
    runway_joint_max_interpolated_fraction: float = 0.10
    runway_joint_max_segment_change: float = 0.35
    runway_joint_filter_cutoff: float | None = None
    runway_stickplot_source: Literal["tracked", "analysis"] = "tracked"
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
    # Legacy manifests keep their established augmented exports. The UI uses
    # native ALMA or the dedicated side/underside workflow explicitly.
    output_format: Literal["legacy", "alma", "alma_side_rust_bottom"] = "legacy"

    def __post_init__(self):
        if self.calibration_method is None:
            # Preserve callers that supply a scale without specifying its mode.
            method = (
                "per_view"
                if self.view_calibration
                else "map"
                if self.calibration_map_path
                else "manual"
                if self.pixels_per_cm is not None
                else "reference"
            )
            object.__setattr__(self, "calibration_method", method)


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
    reference_length_cm = config.get("reference_length_cm") or 0.0
    auto_calibrate_spatial = coerce_bool(config.get("auto_calibrate_spatial", False))
    likelihood_threshold = config.get("kinematics_likelihood_threshold", 0.5)
    if likelihood_threshold == "":
        likelihood_threshold = 0.5
    return AlmaSettings(
        output_format=config.get("output_format", "alma"),
        stride_detection_method=config.get("stride_detection_method", "ALMA (legacy)"),
        limb_scope="Hindlimb + Forelimb"
        if str(config.get("limb_scope", "Hindlimb")).strip().casefold() == "hindlimb + forelimb".casefold()
        else "Hindlimb",
        frame_rate=float(config.get("frame_rate", 120.0)),
        filter_cutoff=float(config.get("lowpass_filter_cutoff", 6.0)),
        treadmill_speed_cm_s=float(cm_speed),
        calibration_method=config.get("calibration_method")
        or ("per_view" if config.get("view_calibration") else "reference" if auto_calibrate_spatial else "manual"),
        calibration_map_path=Path(config["calibration_map_path"]) if config.get("calibration_map_path") else None,
        reference_segment=str(config.get("reference_segment", "ankle_toe")),
        reference_length_cm=float(reference_length_cm),
        right_to_left=right_to_left,
        pixels_per_cm=None if pixels_per_cm is None else float(pixels_per_cm),
        no_outlier_filter=coerce_bool(config.get("no_outlier_filter", False)),
        dragging_filter=coerce_bool(config.get("dragging_filter", False)),
        likelihood_threshold=float(likelihood_threshold),
        drag_clearance_cm=float(config.get("drag_clearance_cm", 0.1)),
        drag_min_consecutive_frames=int(config.get("drag_min_consecutive_frames", 4)),
        **{
            name: float(config.get(name, default))
            for name, default in (
                ("runway_confidence_threshold", 0.6),
                ("runway_max_gap_s", 0.02),
                ("runway_min_body_speed", 0.25),
                ("runway_min_contact_s", 0.03),
                ("runway_joint_max_gap_s", 0.02),
                ("runway_joint_max_interpolated_fraction", 0.10),
                ("runway_joint_max_segment_change", 0.35),
            )
        },
        runway_joint_interpolation=config.get("runway_joint_interpolation", "none"),
        runway_joint_filter_cutoff=(
            float(config["runway_joint_filter_cutoff"])
            if config.get("runway_joint_filter_cutoff") not in (None, "")
            else None
        ),
        runway_stickplot_source=config.get("runway_stickplot_source", "tracked"),
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
