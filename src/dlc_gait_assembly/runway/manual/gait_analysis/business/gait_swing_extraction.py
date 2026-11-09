"""Extract conservative swing-phase and paw-excursion measures on accepted ALMA cycles."""

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import fix_column_names
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.stroke_recovery_parameter_definitions import (
    STROKE_STRIDE_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)


def joint_angles(series, markers):
    if any(marker not in series for marker in markers):
        return None
    points = [np.column_stack((series[m]["x"], series[m]["y"])) for m in markers]
    first, second = points[0] - points[1], points[2] - points[1]
    denominator = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1)
    cosine = np.divide(
        np.sum(first * second, axis=1), denominator, out=np.full(len(denominator), np.nan), where=denominator > 0
    )
    return np.degrees(np.arccos(np.clip(cosine, -1, 1)))


def extract_swing_features(raw, cycles, settings, filtering, pixels_per_cm, mapping=None):
    """Use the configured filter, actual side FPS, and ALMA's stance/swing split.

    Required coordinates must be observed throughout the relevant window. The
    interpolation used for filtering never turns an unobserved excursion into
    a measurement. Image Y is assumed to increase downward, as in ALMA.
    """
    normalized, _, _ = fix_column_names(raw.copy(), mapping or settings.custom_bodypart_mapping)
    prepared = prepare_alma_coordinates(normalized, settings, filtering)
    series = {}
    for marker, axes in prepared.series.items():
        if axes["x"] is None or axes["y"] is None:
            continue
        observed = np.isfinite(normalized[prepared.columns[marker, "x"]].to_numpy(float))
        observed &= np.isfinite(normalized[prepared.columns[marker, "y"]].to_numpy(float))
        likelihood_column = prepared.columns.get((marker, "likelihood"))
        if likelihood_column is not None and settings.likelihood_threshold > 0:
            confidence = normalized[likelihood_column].to_numpy(float)
            observed &= np.isfinite(confidence) & (confidence >= settings.likelihood_threshold)
        series[marker] = {axis: np.where(observed, values, np.nan) for axis, values in axes.items()}
    angles = {
        "knee": joint_angles(series, ("ankle", "knee", "hip")),
        "ankle": joint_angles(series, ("mtp", "ankle", "knee")),
    }
    output = pd.DataFrame(np.nan, index=cycles.index, columns=STROKE_STRIDE_NAMES)
    scale = float(pixels_per_cm) if pixels_per_cm is not None else np.nan
    calibrated = np.isfinite(scale) and scale > 0
    for index, row in cycles.iterrows():
        if not np.isfinite(row.get("cycle duration (s)", np.nan)) or row["cycle duration (s)"] <= 0:
            continue
        start, stop = (row.get(f"stride_{bound} (frame)", np.nan) for bound in ("start", "end"))
        if not np.isfinite(start + stop) or not 0 <= start < stop <= len(raw):
            continue
        start, stop = int(start), int(stop)
        toe, hip = series.get("toe", {}), series.get("hip", {})
        if calibrated and "x" in toe and "x" in hip:
            relative = (toe["x"] - hip["x"])[start:stop]
            if len(relative) >= 2 and np.isfinite(relative).all():
                low, high = np.percentile(relative, (5, 95))
                output.at[index, STROKE_STRIDE_NAMES[0]] = (high - low) / scale
        stance_seconds = row.get("stance duration (s)", np.nan)
        if not np.isfinite(stance_seconds):
            continue
        swing_start = start + int(round(stance_seconds * settings.frame_rate))
        if not start < swing_start < stop:
            continue
        if "y" in toe:
            stance_y, swing_y = toe["y"][start:swing_start], toe["y"][swing_start:stop]
            if np.isfinite(stance_y).all() and np.isfinite(swing_y).all() and len(swing_y) >= 2:
                clearance = np.median(stance_y) - swing_y
                if calibrated:
                    output.at[index, STROKE_STRIDE_NAMES[1]] = float(np.mean(clearance) / scale)
                # A flat or below-ground trace has no identifiable clearance peak.
                if np.max(clearance) > 0 and np.ptp(clearance) > 0:
                    output.at[index, STROKE_STRIDE_NAMES[2]] = 100.0 * np.argmax(clearance) / (stop - swing_start)
        for joint in ("knee", "ankle"):
            values = angles[joint]
            if values is not None:
                swing = values[swing_start:stop]
                if len(swing) >= 2 and np.isfinite(swing).all():
                    output.at[index, f"swing_{joint}_range_of_motion (deg)"] = float(np.ptp(swing))
    return output
