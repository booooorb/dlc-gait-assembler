"""Supported bottom-paw outputs and retired center-marker measurements."""

from __future__ import annotations

RETIRED_BOTTOM_PARAMETER_NAMES = frozenset(
    f"{paw}__{statistic}_Angle" for paw in ("LB", "RB", "LF", "RF") for statistic in ("avg", "max", "min")
) | frozenset({"left_hindpaw_midline_distance", "right_hindpaw_midline_distance"})
RETIRED_CENTER_QC_NAMES = frozenset(
    {
        "body_speed_cm_s",
        "mean_speed_cm_s",
        "speed_cv",
        "session_speed_cm_s",
        "session_speed_cv",
    }
)


def without_retired_bottom_parameters(table):
    retired = RETIRED_BOTTOM_PARAMETER_NAMES | RETIRED_CENTER_QC_NAMES
    return table.loc[:, [name for name in table if name.removesuffix("__iqr") not in retired]]
