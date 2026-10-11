"""Calculate horizontal excursion, distance, and protraction/retraction measurements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    safe_percentile as _safe_percentile,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import (
    safe_stat as _safe_stat,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import slice as _slice


def write_horizontal_features(output, row_index, side, prefix, series, cycle_slice, pixels_per_cm, np) -> None:
    if not pixels_per_cm or pixels_per_cm <= 0:
        return
    millimeters_per_pixel = 10.0 / pixels_per_cm
    for limb, toe_marker, reference_marker in (
        ("back", f"{prefix}-back-toe", f"{prefix}-hip"),
        ("front", f"{prefix}-front-toe-tip", f"{prefix}-shoulder"),
    ):
        toe_x = _slice(series, toe_marker, "x", cycle_slice)
        reference_x = _slice(series, reference_marker, "x", cycle_slice)
        if toe_x is None or reference_x is None:
            continue
        distance_mm = (toe_x - reference_x) * millimeters_per_pixel
        values = {
            f"{side}__{limb}__average": _safe_stat(np.nanmean, distance_mm, np),
            f"{side}__{limb}__median": _safe_stat(np.nanmedian, distance_mm, np),
            f"{side}__{limb}__protraction": _safe_percentile(distance_mm, 95, np),
            f"{side}__{limb}__retraction": _safe_percentile(distance_mm, 5, np),
        }
        for name, value in values.items():
            if name in output.columns:
                output.at[row_index, name] = value
