"""Define custom SOP parameter names, units, and marker requirements."""

from __future__ import annotations

from dataclasses import dataclass

CUSTOM_SOP_PARAMETER_NAMES = (
    "mean_hindlimb_base_support",
    "variance_hindlimb_base_support",
    "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction",
    "left_mtp_average_height",
    "left_mtp_vertical_excursion",
    "right_mtp_average_height",
    "right_mtp_vertical_excursion",
    "left_knee_average_height",
    "left_knee_vertical_excursion",
    "right_knee_average_height",
    "right_knee_vertical_excursion",
)
CUSTOM_SOP_MARKERS = (
    "d-back-left",
    "d-back-right",
    "l-back-mtp",
    "l-back-knee",
    "r-back-mtp",
    "r-back-knee",
)


@dataclass(frozen=True)
class CustomSopExtraction:
    dataframe: object
    available_parameters: tuple[str, ...]
    missing_markers: tuple[str, ...]
