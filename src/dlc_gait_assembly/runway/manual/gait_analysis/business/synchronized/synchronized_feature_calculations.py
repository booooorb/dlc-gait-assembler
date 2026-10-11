"""Calculate synchronized side/bottom trajectory measurements for supplied cycles."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    CUSTOM_STROKE_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    safe_mean as _safe_mean,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    safe_variance as _safe_variance,
)


def calculate_stroke_features(
    cycles, trajectories, calibration, pd, np, *, side_y_pixels_per_cm=None, enabled_parameter_names=None
):
    """Calculate the 12 supported custom gait-cycle measures specified by the SOP."""
    enabled = set(CUSTOM_STROKE_PARAMETER_NAMES) if enabled_parameter_names is None else set(enabled_parameter_names)
    enabled_columns = tuple(name for name in CUSTOM_STROKE_PARAMETER_NAMES if name in enabled)
    x_scale = float(calibration["x_pixels_per_cm"])
    y_scale = float(calibration["y_pixels_per_cm"])
    side_y_pixels_per_cm = side_y_pixels_per_cm or {"left": y_scale, "right": y_scale}
    rows = []
    for _, cycle in cycles.iterrows():
        left_start = int(cycle["left_stance_start_frame"])
        left_end = int(cycle["left_stance_end_frame"])
        right_start = cycle["right_stance_start_frame"]
        right_end = cycle["right_stance_end_frame"]
        overlap_start = max(left_start, int(right_start)) if pd.notna(right_start) else None
        overlap_end = min(left_end, int(right_end)) if pd.notna(right_end) else None
        needs_support = bool(enabled & {"mean_hindlimb_base_support", "variance_hindlimb_base_support"})
        if needs_support and overlap_start is not None and (overlap_end is not None) and (overlap_end >= overlap_start):
            overlap = trajectories.loc[overlap_start:overlap_end]
            separation = np.sqrt(
                ((overlap["left_x"] - overlap["right_x"]) / x_scale) ** 2
                + ((overlap["left_y"] - overlap["right_y"]) / y_scale) ** 2
            )
        else:
            separation = pd.Series(dtype=float)
        cycle_start = int(cycle["stride_start (frame)"])
        cycle_end = int(cycle["stride_end (frame)"])
        cycle_slice = trajectories.loc[cycle_start:cycle_end]
        values = {
            "mean_hindlimb_base_support": _safe_mean(separation, np),
            "variance_hindlimb_base_support": _safe_variance(separation, np),
            "left_right_hindlimb_phase_offset": cycle["left_right_hindlimb_phase_offset"],
            "hindlimb_stance_overlap_fraction": cycle["hindlimb_stance_overlap_fraction"],
        }
        row = {name: value for (name, value) in values.items() if name in enabled}
        for side in ("left", "right"):
            scale = side_y_pixels_per_cm.get(side)
            for bodypart in ("mtp", "knee"):
                average_name = f"{side}_{bodypart}_average_height"
                excursion_name = f"{side}_{bodypart}_vertical_excursion"
                if average_name not in enabled and excursion_name not in enabled:
                    continue
                (average, excursion) = cycle_height_metrics(cycle_slice.get(f"{side}_{bodypart}_y"), scale, np)
                if average_name in enabled:
                    row[average_name] = average
                if excursion_name in enabled:
                    row[excursion_name] = excursion
        rows.append(row)
    return pd.DataFrame(rows, columns=enabled_columns)


def bottom_trajectories(merged, settings, calibration, kinematics, pd, np, preprocessed=None):
    preprocessed = preprocessed or prepare_alma_coordinates(merged, settings, kinematics)
    columns = preprocessed.columns
    marker_map = {"left": "d-back-left", "right": "d-back-right"}
    result = pd.DataFrame(index=range(len(merged)))
    coverage = {}
    interpolation_counts = {}
    for label, marker in marker_map.items():
        for coord in ("x", "y"):
            column = columns.get((marker, coord))
            if column is None:
                result[f"{label}_{coord}"] = np.nan
                coverage[f"{marker}_{coord}"] = 0.0
                interpolation_counts[f"{marker}_{coord}"] = 0
                continue
            values = pd.to_numeric(merged[column], errors="coerce").astype(float)
            likelihood_column = columns.get((marker, "likelihood"))
            if likelihood_column is not None:
                likelihood = pd.to_numeric(merged[likelihood_column], errors="coerce")
                values = values.mask(likelihood < settings.likelihood_threshold)
            original_valid = values.notna()
            processed = preprocessed.series.get(marker, {}).get(coord)
            if processed is None:
                processed = np.full(len(merged), np.nan)
            processed = np.asarray(processed, dtype=float)
            interpolation_counts[f"{marker}_{coord}"] = int(
                np.count_nonzero(~original_valid.to_numpy(dtype=bool) & np.isfinite(processed))
            )
            coverage[f"{marker}_{coord}"] = float(original_valid.mean())
            result[f"{label}_{coord}"] = processed
    required = ["left_x", "left_y", "right_x", "right_y"]
    side_required = []
    for prefix in ("l", "r"):
        for bodypart in ("back-toe", "back-mtp", "back-ankle", "back-knee", "hip", "iliac-crest"):
            marker = f"{prefix}-{bodypart}"
            for coord in ("x", "y"):
                validity_name = f"required__{marker}__{coord}"
                side_required.append(validity_name)
                column = columns.get((marker, coord))
                if column is None:
                    result[validity_name] = False
                    coverage[f"{marker}_{coord}"] = 0.0
                    interpolation_counts[f"{marker}_{coord}"] = 0
                    continue
                values = pd.to_numeric(merged[column], errors="coerce").astype(float)
                likelihood_column = columns.get((marker, "likelihood"))
                if likelihood_column is not None:
                    likelihood = pd.to_numeric(merged[likelihood_column], errors="coerce")
                    values = values.mask(likelihood < settings.likelihood_threshold)
                original_valid = values.notna()
                processed = preprocessed.series.get(marker, {}).get(coord)
                if processed is None:
                    processed = np.full(len(merged), np.nan)
                processed = np.asarray(processed, dtype=float)
                result[validity_name] = np.isfinite(processed)
                if coord == "y" and bodypart in {"back-mtp", "back-knee"}:
                    output_bodypart = bodypart.removeprefix("back-")
                    side = "left" if prefix == "l" else "right"
                    result[f"{side}_{output_bodypart}_y"] = processed
                coverage[f"{marker}_{coord}"] = float(original_valid.mean())
                interpolation_counts[f"{marker}_{coord}"] = int(
                    np.count_nonzero(~original_valid.to_numpy(dtype=bool) & np.isfinite(processed))
                )
    result["required_tracking_valid"] = result[required].notna().all(axis=1) & result[side_required].all(axis=1)
    x_scale = float(calibration["x_pixels_per_cm"])
    y_scale = float(calibration["y_pixels_per_cm"])
    for side in ("left", "right"):
        dx = result[f"{side}_x"].diff() / x_scale
        dy = result[f"{side}_y"].diff() / y_scale
        speed = np.sqrt(dx**2 + dy**2) * float(settings.frame_rate)
        result[f"{side}_speed_cm_s"] = speed
        result[f"{side}_stance"] = speed <= float(settings.swing_speed_threshold_cm_s)
    return (
        result,
        {
            "marker_coordinate_coverage": coverage,
            "interpolated_samples": interpolation_counts,
            "required_tracking_coverage": float(result["required_tracking_valid"].mean()),
        },
    )


def interval_overlap(left_start, left_end, right_start, right_end):
    if right_start is None or right_end is None:
        return 0
    return max(0, min(left_end, right_end) - max(left_start, right_start) + 1)


def column_difference(dataframe, minuend: str, subtrahend: str, np):
    if minuend not in dataframe or subtrahend not in dataframe:
        return None
    return dataframe[minuend] - dataframe[subtrahend]


def cycle_height_metrics(values, pixels_per_cm, np) -> tuple[float, float]:
    """Return mean height above the cycle's lowest paw position and excursion."""
    if values is None or not pixels_per_cm or float(pixels_per_cm) <= 0:
        return (np.nan, np.nan)
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if len(finite) == 0:
        return (np.nan, np.nan)
    height = (float(np.max(finite)) - finite) / float(pixels_per_cm)
    return (float(np.mean(height)), float(np.max(height) - np.min(height)))
