"""Calculate vertical displacement, height, and related trajectory measurements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import slice as _slice


def write_vertical_features(output, row_index, prefix, series, cycle_slice, pixels_per_cm, np):
    if not pixels_per_cm or pixels_per_cm <= 0:
        return
    millimeters_per_pixel = 10.0 / pixels_per_cm
    for marker_suffix in (
        "back-ankle",
        "back-toe",
        "hip",
        "iliac-crest",
        "front-toe-tip",
        "wrist",
        "elbow",
        "shoulder",
    ):
        marker = f"{prefix}-{marker_suffix}"
        y = _slice(series, marker, "y", cycle_slice)
        if y is None or not np.isfinite(y).any():
            continue
        oriented_y = -y if prefix == "l" else y
        average_height = (np.nanmean(oriented_y) - np.nanmin(oriented_y)) * millimeters_per_pixel
        movement = (np.nanmax(oriented_y) - np.nanmin(oriented_y)) * millimeters_per_pixel
        average_name = f"{marker}__Average_Height"
        if average_name in output.columns:
            output.at[row_index, average_name] = average_height
        movement_name = f"{marker}__Movement"
        if movement_name in output.columns:
            output.at[row_index, movement_name] = movement
