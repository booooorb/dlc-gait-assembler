"""Calculate the maintained custom SOP measurements on authoritative ALMA cycles."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_MARKERS,
    CUSTOM_SOP_PARAMETER_NAMES,
    CustomSopExtraction,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaPreprocessedCoordinates
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


def extract_custom_sop_parameters(
    raw_dataframe, alma_parameters, settings, kinematics, preprocessed: AlmaPreprocessedCoordinates | None = None
) -> CustomSopExtraction:
    """Calculate the SOP's 12 supported custom measures on ALMA gait-cycle windows."""
    import numpy as np

    preprocessed = preprocessed or prepare_alma_coordinates(raw_dataframe, settings, kinematics, CUSTOM_SOP_MARKERS)
    _validate_preprocessed_coordinates(preprocessed, raw_dataframe, settings)
    columns = preprocessed.columns
    present_markers = {marker for (marker, _coord) in columns}
    (scalar_scale, _source) = _resolve_pixels_per_cm(raw_dataframe, columns, settings)
    bottom_x_scale = configured_axis_scale(settings, "bottom", "x", scalar_scale)
    bottom_y_scale = configured_axis_scale(settings, "bottom", "y", scalar_scale)
    side_y_scales = {side: configured_axis_scale(settings, side, "y", scalar_scale) for side in ("left", "right")}
    required_series = {
        marker: preprocessed.series[marker] for marker in CUSTOM_SOP_MARKERS if marker in preprocessed.series
    }
    left_stance = stance_mask(required_series, "d-back-left", bottom_x_scale, bottom_y_scale, settings, np)
    right_stance = stance_mask(required_series, "d-back-right", bottom_x_scale, bottom_y_scale, settings, np)
    cycle_keys = [
        name
        for name in ("limb (hind left / right)", "stride_start (frame)", "stride_end (frame)")
        if name in alma_parameters.columns
    ]
    output = alma_parameters.loc[:, cycle_keys].copy().reset_index(drop=True)
    output.insert(0, "gait_cycle", range(1, len(output) + 1))
    enabled_parameters = _enabled_parameters(settings, CUSTOM_SOP_PARAMETER_NAMES)
    for parameter in enabled_parameters:
        output[parameter] = np.nan
    for row_index, parameter_row in alma_parameters.reset_index(drop=True).iterrows():
        bounds = _cycle_bounds(parameter_row, len(raw_dataframe))
        if bounds is None:
            continue
        (start, end) = bounds
        cycle_slice = slice(start, end + 1)
        duration = end - start + 1
        left_cycle_stance = mask_slice(left_stance, cycle_slice, duration, np)
        right_cycle_stance = mask_slice(right_stance, cycle_slice, duration, np)
        left_x = _slice(required_series, "d-back-left", "x", cycle_slice)
        left_y = _slice(required_series, "d-back-left", "y", cycle_slice)
        right_x = _slice(required_series, "d-back-right", "x", cycle_slice)
        right_y = _slice(required_series, "d-back-right", "y", cycle_slice)
        if all(value is not None for value in (left_x, left_y, right_x, right_y)) and bottom_x_scale and bottom_y_scale:
            bilateral = left_cycle_stance & right_cycle_stance
            separation = np.sqrt(
                ((left_x - right_x) / bottom_x_scale) ** 2 + ((left_y - right_y) / bottom_y_scale) ** 2
            )
            values = {
                "mean_hindlimb_base_support": masked_stat(separation, bilateral, np.nanmean, np),
                "variance_hindlimb_base_support": masked_variance(separation, bilateral, np),
            }
            for name, value in values.items():
                if name in output.columns:
                    output.at[row_index, name] = value
        right_onsets = np.flatnonzero(right_cycle_stance & ~np.r_[False, right_cycle_stance[:-1]])
        if len(right_onsets):
            if "left_right_hindlimb_phase_offset" in output.columns:
                output.at[row_index, "left_right_hindlimb_phase_offset"] = 100.0 * float(right_onsets[0]) / duration
        if "hindlimb_stance_overlap_fraction" in output.columns:
            output.at[row_index, "hindlimb_stance_overlap_fraction"] = (
                100.0 * float(np.count_nonzero(left_cycle_stance & right_cycle_stance)) / duration
            )
        for side, prefix in (("left", "l"), ("right", "r")):
            for bodypart in ("mtp", "knee"):
                y = _slice(required_series, f"{prefix}-back-{bodypart}", "y", cycle_slice)
                (average, excursion) = height_metrics(y, side_y_scales[side], np)
                average_name = f"{side}_{bodypart}_average_height"
                excursion_name = f"{side}_{bodypart}_vertical_excursion"
                if average_name in output.columns:
                    output.at[row_index, average_name] = average
                if excursion_name in output.columns:
                    output.at[row_index, excursion_name] = excursion
    available = tuple(name for name in enabled_parameters if output[name].notna().any())
    missing = tuple(marker for marker in CUSTOM_SOP_MARKERS if marker not in present_markers)
    return CustomSopExtraction(output, available, missing)


def configured_axis_scale(settings, view: str, axis: str, fallback):
    configured = (settings.view_calibration or {}).get(view)
    if isinstance(configured, (int, float)) and float(configured) > 0:
        return float(configured)
    if isinstance(configured, dict):
        value = configured.get(f"{axis}_pixels_per_cm", configured.get("pixels_per_cm"))
        if value and float(value) > 0:
            return float(value)
    return float(fallback) if fallback and float(fallback) > 0 else None


def stance_mask(series, marker, x_scale, y_scale, settings, np):
    x = _slice(series, marker, "x", slice(None))
    y = _slice(series, marker, "y", slice(None))
    if x is None or y is None or (not x_scale) or (not y_scale):
        return None
    dx = np.diff(x, prepend=np.nan) / float(x_scale)
    dy = np.diff(y, prepend=np.nan) / float(y_scale)
    speed = np.sqrt(dx**2 + dy**2) * float(settings.frame_rate)
    stance = np.isfinite(speed) & (speed <= float(settings.swing_speed_threshold_cm_s))
    if len(stance) > 1:
        stance[0] = stance[1]
    return stance


def mask_slice(mask, cycle_slice, duration: int, np):
    if mask is None:
        return np.zeros(duration, dtype=bool)
    output = np.asarray(mask[cycle_slice], dtype=bool)
    if len(output) == duration:
        return output
    padded = np.zeros(duration, dtype=bool)
    padded[: min(duration, len(output))] = output[:duration]
    return padded


def masked_stat(values, mask, function, np):
    selected = np.asarray(values, dtype=float)[np.asarray(mask, dtype=bool)]
    return _safe_stat(function, selected, np)


def masked_variance(values, mask, np):
    selected = np.asarray(values, dtype=float)[np.asarray(mask, dtype=bool)]
    selected = selected[np.isfinite(selected)]
    return float(np.var(selected, ddof=1)) if len(selected) > 1 else np.nan


def height_metrics(values, pixels_per_cm, np):
    if values is None or not pixels_per_cm or float(pixels_per_cm) <= 0:
        return (np.nan, np.nan)
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return (np.nan, np.nan)
    height = (float(np.max(finite)) - finite) / float(pixels_per_cm)
    return (float(np.mean(height)), float(np.max(height) - np.min(height)))
