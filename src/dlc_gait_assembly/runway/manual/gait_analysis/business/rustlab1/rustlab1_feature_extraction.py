"""Assemble RustLab1 measurements for supplied canonical cycles using shared preprocessing."""

from __future__ import annotations

from dataclasses import dataclass

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaPreprocessedCoordinates
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    rustlab1_markers_for_scope,
    rustlab1_parameter_names_for_scope,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_signal_filtering import (
    validate_preprocessed_coordinates as _validate_preprocessed_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_spatial_scaling import (
    resolve_pixels_per_cm as _resolve_pixels_per_cm,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    cycle_bounds as _cycle_bounds,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    enabled_parameters as _enabled_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    safe_stat as _safe_stat,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import slice as _slice
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    step_duration_seconds as _step_duration_seconds,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_horizontal_features import (
    write_horizontal_features as _write_horizontal_features,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_interlimb_features import (
    rustlab1_stance_mask as _rustlab1_stance_mask,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_interlimb_features import (
    write_interlimb_coordination as _write_interlimb_coordination,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_joint_features import (
    write_forelimb_side_angles as _write_forelimb_side_angles,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_vertical_features import (
    write_vertical_features,
)


@dataclass(frozen=True)
class RustLab1Extraction:
    dataframe: object | None
    available_parameters: tuple[str, ...]
    missing_markers: tuple[str, ...]
    pixels_per_cm: float | None
    calibration_source: str


def extract_rustlab1_parameters(
    raw_dataframe, alma_parameters, settings, kinematics, preprocessed: AlmaPreprocessedCoordinates | None = None
) -> RustLab1Extraction:
    """Calculate the selected RustLab1 limb features on supplied gait-cycle rows.

    Post-ALMA callers supply ALMA's exact stride boundaries so merged outputs
    retain one row index. The standalone RustLab1 caller instead supplies its
    own bottom-paw stance-onset boundaries.
    """
    import numpy as np

    preprocessed = preprocessed or prepare_alma_coordinates(
        raw_dataframe, settings, kinematics, rustlab1_markers_for_scope(getattr(settings, "limb_scope", "Hindlimb"))
    )
    _validate_preprocessed_coordinates(preprocessed, raw_dataframe, settings)
    columns = preprocessed.columns
    present_markers = {marker for (marker, _coord) in columns}
    limb_scope = getattr(settings, "limb_scope", "Hindlimb")
    parameter_names = rustlab1_parameter_names_for_scope(limb_scope)
    required_markers = rustlab1_markers_for_scope(limb_scope)
    if not present_markers.intersection(required_markers):
        return RustLab1Extraction(None, (), required_markers, None, "not available")
    (pixels_per_cm, calibration_source) = _resolve_pixels_per_cm(raw_dataframe, columns, settings)
    cycle_keys = [
        name
        for name in ("limb (hind left / right)", "stride_start (frame)", "stride_end (frame)")
        if name in alma_parameters.columns
    ]
    output = alma_parameters.loc[:, cycle_keys].copy().reset_index(drop=True)
    output.insert(0, "gait_cycle", range(1, len(output) + 1))
    output["pixels_per_cm"] = pixels_per_cm
    enabled_parameters = _enabled_parameters(settings, parameter_names)
    for parameter in enabled_parameters:
        output[parameter] = np.nan
    required_series = {
        marker: preprocessed.series[marker] for marker in required_markers if marker in preprocessed.series
    }
    bottom_stance = {
        marker: _rustlab1_stance_mask(
            required_series, marker, np, float(getattr(settings, "stance_speed_threshold_px_frame", 7.0))
        )
        for marker in ("d-front-left", "d-front-right", "d-back-left", "d-back-right")
        if marker in required_series
    }
    from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import view_scale

    x_scales = {side: view_scale(settings, side, "x", pixels_per_cm) for side in ("left", "right")}
    y_scales = {side: view_scale(settings, side, "y", pixels_per_cm) for side in ("left", "right")}
    hip_cycle_means: dict[str, list[float]] = {"left": [], "right": []}
    cycle_groups: list[str] = []
    for row_index, parameter_row in alma_parameters.reset_index(drop=True).iterrows():
        cycle_groups.append(str(parameter_row.get("limb (hind left / right)", "all")))
        bounds = _cycle_bounds(parameter_row, len(raw_dataframe))
        if bounds is None:
            hip_cycle_means["left"].append(np.nan)
            hip_cycle_means["right"].append(np.nan)
            continue
        (start, end) = bounds
        cycle_slice = slice(start, end + 1)
        _write_interlimb_coordination(output, row_index, bottom_stance, cycle_slice, np)
        for side, prefix in (("left", "l"), ("right", "r")):
            write_vertical_features(output, row_index, prefix, required_series, cycle_slice, y_scales[side], np)
            _write_horizontal_features(
                output, row_index, side, prefix, required_series, cycle_slice, x_scales[side], np
            )
            _write_forelimb_side_angles(output, row_index, side, prefix, required_series, cycle_slice, np)
            duration_name = f"{side}__front__seconds"
            if duration_name in output.columns:
                output.at[row_index, duration_name] = _step_duration_seconds(
                    bottom_stance.get(f"d-front-{side}"), start, end, float(settings.frame_rate), np
                )
            hip = _slice(required_series, f"{prefix}-hip", "x", cycle_slice)
            hip_cycle_means[side].append(_safe_stat(np.nanmean, hip, np))
    if pixels_per_cm and pixels_per_cm > 0:
        for side in ("left", "right"):
            previous_by_group: dict[str, float] = {}
            differences: list[float] = []
            for group, mean in zip(cycle_groups, hip_cycle_means[side], strict=True):
                previous = previous_by_group.get(group, np.nan)
                differences.append((mean - previous) / x_scales[side] if np.isfinite(mean) else np.nan)
                if np.isfinite(mean):
                    previous_by_group[group] = mean
            movement_name = f"{side}__back__movement_per_step"
            if movement_name in output.columns:
                output[movement_name] = differences
    available = tuple(name for name in enabled_parameters if output[name].notna().any())
    missing = tuple(marker for marker in required_markers if marker not in present_markers)
    return RustLab1Extraction(output, available, missing, pixels_per_cm, calibration_source)
