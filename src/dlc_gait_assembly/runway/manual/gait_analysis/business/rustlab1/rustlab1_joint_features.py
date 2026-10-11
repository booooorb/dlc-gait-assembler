"""Calculate side-view hindlimb and forelimb joint-angle measurements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    safe_percentile as _safe_percentile,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    safe_stat as _safe_stat,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import slice as _slice


def write_forelimb_side_angles(output, row_index, side, prefix, series, cycle_slice, np) -> None:
    points = {
        name: (
            _slice(series, f"{prefix}-{name}", "x", cycle_slice),
            _slice(series, f"{prefix}-{name}", "y", cycle_slice),
        )
        for name in ("shoulder", "elbow", "wrist", "front-toe-tip")
    }
    angle_definitions = (
        ("shoulder_ellbow_wrist", "elbow", "wrist", "shoulder"),
        ("ellbow_wrist_toetip", "wrist", "front-toe-tip", "elbow"),
    )
    for joint_name, center_name, first_name, second_name in angle_definitions:
        arrays = (*points[center_name], *points[first_name], *points[second_name])
        if any(value is None for value in arrays):
            continue
        (center_x, center_y) = points[center_name]
        (first_x, first_y) = points[first_name]
        (second_x, second_y) = points[second_name]
        if prefix == "l":
            (center_y, first_y, second_y) = (-center_y, -first_y, -second_y)
        angle = np.degrees(
            np.arctan2(first_y - center_y, first_x - center_x) - np.arctan2(second_y - center_y, second_x - center_x)
        )
        angle = angle[np.isfinite(angle) & (angle < 180.0)]
        values = {
            f"avg_Angle__{side}__front__{joint_name}": abs(_safe_stat(np.nanmean, angle, np)),
            f"max_Angle__{side}__front__{joint_name}": abs(_safe_percentile(angle, 95, np)),
            f"min_Angle__{side}__front__{joint_name}": abs(_safe_percentile(angle, 10, np)),
        }
        for name, value in values.items():
            if name in output.columns:
                output.at[row_index, name] = value
