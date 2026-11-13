"""Exclude the retired custom parameter family, including old saved selections."""

RETIRED_CUSTOM_NAMES = frozenset({
    "mean_hindlimb_base_support", "variance_hindlimb_base_support", "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction", "left_mtp_average_height", "left_mtp_vertical_excursion",
    "right_mtp_average_height", "right_mtp_vertical_excursion", "left_knee_average_height",
    "left_knee_vertical_excursion", "right_knee_average_height", "right_knee_vertical_excursion",
    "opposite_hindlimb_phase_offset (%)", "hindlimb_swing_overlap_fraction", "hindlimb_stance_overlap (%)",
    "hindlimb_swing_overlap (%)", "hindlimb_opposite_phase (%)", "hindlimb_same_phase (%)",
})


def is_retired_custom_name(name):
    name = str(name).removeprefix("left__").removeprefix("right__")
    return name in RETIRED_CUSTOM_NAMES or any(
        name.startswith(f"{retired}{suffix}")
        for retired in RETIRED_CUSTOM_NAMES for suffix in ("__", "_mean", "_sd", "_std", "_median")
    )


def without_custom_parameters(table):
    return table.drop(columns=[name for name in table if is_retired_custom_name(name)], errors="ignore")
