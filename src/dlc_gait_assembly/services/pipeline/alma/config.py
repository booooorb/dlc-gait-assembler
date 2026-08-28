"""ALMA configuration loading and translation."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.services.imports import default_alma_root as _default_alma_root
from dlc_gait_assembly.services.pipeline.alma.models import AlmaSettings


def default_alma_root(project_root: Path) -> Path:
    return _default_alma_root(project_root)


def load_alma_config_defaults(alma_root: Path) -> dict:
    config_path = alma_root / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
    except ModuleNotFoundError:
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=yaml.FullLoader) or {}


def settings_from_alma_config(config: dict) -> AlmaSettings:
    right_to_left = config.get("right_to_left", False)
    if isinstance(right_to_left, str):
        right_to_left = "auto" if right_to_left.lower() == "auto" else _coerce_bool(right_to_left)
    pixels_per_cm = config.get("pixels_per_cm", None)
    if pixels_per_cm == "":
        pixels_per_cm = None
    cm_speed = config.get("cm_speed", None)
    if cm_speed in (None, ""):
        cm_speed = 30.0
    reference_length_cm = config.get("reference_length_cm", 1.5)
    if reference_length_cm == "":
        reference_length_cm = 1.5
    auto_calibrate_spatial = _coerce_bool(config.get("auto_calibrate_spatial", True), default=True)
    likelihood_threshold = config.get("kinematics_likelihood_threshold", 0.5)
    if likelihood_threshold == "":
        likelihood_threshold = 0.5
    return AlmaSettings(
        limb_scope=(
            "Hindlimb + Forelimb"
            if str(config.get("limb_scope", "Hindlimb")).strip().casefold()
            == "hindlimb + forelimb".casefold()
            else "Hindlimb"
        ),
        frame_rate=float(config.get("frame_rate", 120.0)),
        filter_cutoff=float(config.get("lowpass_filter_cutoff", 6.0)),
        treadmill_speed_cm_s=float(cm_speed),
        calibration_method="reference" if auto_calibrate_spatial else "manual",
        reference_segment=str(config.get("reference_segment", "ankle_toe")),
        reference_length_cm=float(reference_length_cm),
        right_to_left=right_to_left,
        pixels_per_cm=None if pixels_per_cm is None else float(pixels_per_cm),
        no_outlier_filter=_coerce_bool(config.get("no_outlier_filter", False)),
        dragging_filter=_coerce_bool(config.get("dragging_filter", False)),
        likelihood_threshold=float(likelihood_threshold),
        drag_clearance_cm=float(config.get("drag_clearance_cm", 0.1)),
        drag_min_consecutive_frames=int(config.get("drag_min_consecutive_frames", 4)),
        step_height_min_cm=float(config.get("step_height_min_cm", 0.0)),
        step_height_max_cm=float(config.get("step_height_max_cm", 2.0)),
        stride_length_min_cm=float(config.get("stride_length_min_cm", 0.0)),
        stride_length_max_cm=float(config.get("stride_length_max_cm", 8.0)),
        generate_alma_representations=_coerce_bool(
            config.get("generate_alma_representations", True),
            default=True,
        ),
        generate_rustlab1_parameters=_coerce_bool(
            config.get("generate_rustlab1_parameters", True),
            default=True,
        ),
        stroke_analysis_enabled=_coerce_bool(
            config.get("stroke_analysis_enabled", True),
            default=True,
        ),
        stroke_likelihood_threshold=float(likelihood_threshold),
        max_interpolation_gap_frames=0,
        swing_speed_threshold_cm_s=float(config.get("swing_speed_threshold_cm_s", 10.0)),
        minimum_synchronized_cycles=int(config.get("minimum_synchronized_cycles", 5)),
        view_calibration=config.get("view_calibration"),
    )


def _coerce_bool(value, default: bool = False) -> bool:
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
