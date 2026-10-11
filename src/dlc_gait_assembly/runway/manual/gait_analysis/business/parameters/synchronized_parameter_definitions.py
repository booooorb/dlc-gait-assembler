"""Define synchronized and asymmetry measurement names, units, and requirements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.bottom_paw_parameter_contract import (
    without_retired_bottom_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_PARAMETER_NAMES,
)

CUSTOM_STROKE_PARAMETER_NAMES = CUSTOM_SOP_PARAMETER_NAMES
ASYMMETRY_PARAMETER_NAMES = (
    "step_height_asymmetry",
    "stride_length_asymmetry",
    "stance_percentage_asymmetry",
    "knee_range_of_motion_asymmetry",
    "protraction_retraction_excursion_asymmetry",
    "dragging_percentage_asymmetry",
)
PRIMARY_STROKE_PARAMETER_NAMES = (
    "hindlimb_phase_offset_deviation_from_baseline",
    "hindlimb_stance_overlap_fraction",
    "step_height_asymmetry",
    "stride_length_asymmetry",
    "knee_range_of_motion_asymmetry",
    "protraction_retraction_excursion_asymmetry",
)
IDENTIFIER_COLUMNS = ("animal_id", "group", "sex", "lesion_hemisphere", "timepoint", "trial", "session_id", "cycle_id")
CANONICAL_CYCLE_COLUMNS = (
    *IDENTIFIER_COLUMNS,
    "contralesional_side",
    "ipsilesional_side",
    "frame_rate_hz",
    "bottom_x_pixels_per_cm",
    "bottom_y_pixels_per_cm",
    "calibration_source",
    "left_calibration_source",
    "right_calibration_source",
    "left_view_csv",
    "right_view_csv",
    "bottom_view_csv",
    "stride_start (frame)",
    "stride_end (frame)",
    "left_stance_start_frame",
    "left_stance_end_frame",
    "right_stance_start_frame",
    "right_stance_end_frame",
    "cycle_duration_frames",
    "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction",
    "tracking_coverage",
    "cycle_valid",
    "rejection_reason",
)
ALMA_ASYMMETRY_COLUMNS = {
    "step_height_asymmetry": "step height (cm)",
    "stride_length_asymmetry": "stride length (cm)",
    "stance_percentage_asymmetry": "stance percentage (%)",
    "knee_range_of_motion_asymmetry": "knee joint amplitude (deg)",
    "dragging_percentage_asymmetry": "drag percentage (%)",
}


def selected_parameter_names(settings: AlmaSettings, available: tuple[str, ...]) -> tuple[str, ...]:
    selected = settings.enabled_parameter_names
    if selected is None:
        return available
    selected_set = set(selected)
    return tuple(name for name in available if name in selected_set)


def selected_alma_parameters(parameters, settings: AlmaSettings, side: str | None = None):
    selected = settings.enabled_parameter_names
    if selected is None:
        return parameters
    selected_set = set(selected)
    has_side_selection = any(name.startswith(("left__", "right__")) for name in selected_set)
    gait_columns = set(ALMA_PARAMETER_NAMES)
    columns = [
        column
        for column in parameters
        if column not in gait_columns
        or (
            side is None
            and column in selected_set
            or (
                side is not None
                and (f"{side}__{column}" in selected_set if has_side_selection else column in selected_set)
            )
        )
    ]
    return parameters.loc[:, columns]


def build_feature_dictionary(stride_features, pd):
    stride_features = without_retired_bottom_parameters(stride_features)
    rows = []
    for column in stride_features.columns:
        if column in IDENTIFIER_COLUMNS or column.endswith(("valid", "usable")):
            continue
        (family, source, unit, status) = feature_metadata(column)
        rows.append(
            {
                "feature": column,
                "family": family,
                "source": source,
                "unit": unit,
                "analysis_status": status,
                "required_markers": required_markers(column),
                "formula": formula(column),
            }
        )
    return pd.DataFrame(rows)


def feature_metadata(column: str) -> tuple[str, str, str, str]:
    if column in PRIMARY_STROKE_PARAMETER_NAMES:
        return ("stroke primary", "multi-view", unit_for(column), "primary")
    if column in CUSTOM_STROKE_PARAMETER_NAMES or column in ASYMMETRY_PARAMETER_NAMES:
        return ("coordination/asymmetry", "multi-view", unit_for(column), "secondary")
    if column in RUSTLAB1_PARAMETER_NAMES:
        return ("RustLab1", "side/bottom", unit_for(column), "secondary")
    if column.startswith(("left__", "right__")):
        return ("ALMA", column.split("__", 1)[0], unit_for(column), "secondary")
    if "tracking" in column or "match" in column or "speed_cv" in column:
        return ("quality control", "multi-view", unit_for(column), "qc")
    return ("cycle", "bottom", unit_for(column), "exploratory")


def unit_for(column: str) -> str:
    lowered = column.lower()
    if column in CUSTOM_STROKE_PARAMETER_NAMES and ("average_height" in lowered or "vertical_excursion" in lowered):
        return "cm"
    if "asymmetry" in lowered:
        return "unitless"
    if "fraction" in lowered or "percentage" in lowered or "phase_offset" in lowered:
        return "%"
    if "variance_hindlimb" in lowered:
        return "cm^2"
    if "frame" in lowered:
        return "frames"
    if "(s)" in lowered or "duration" in lowered:
        return "s"
    if "speed" in lowered or "velocity" in lowered:
        return "cm/s"
    if "angle" in lowered or "(deg)" in lowered:
        return "deg"
    if "(mm)" in lowered or "average_height" in lowered or "__movement" in lowered:
        return "mm"
    if "support" in lowered or "distance" in lowered or "height" in lowered or ("length" in lowered):
        return "cm"
    return ""


def required_markers(column: str) -> str:
    if column in {
        "mean_hindlimb_base_support",
        "variance_hindlimb_base_support",
        "left_right_hindlimb_phase_offset",
        "hindlimb_stance_overlap_fraction",
    }:
        return "bottom left hindpaw (lhpaw); bottom right hindpaw (rhpaw)"
    if column in CUSTOM_STROKE_PARAMETER_NAMES and "mtp" in column:
        return f"{column.split('_', 1)[0]} side-view MTP"
    if column in CUSTOM_STROKE_PARAMETER_NAMES and "knee" in column:
        return f"{column.split('_', 1)[0]} side-view knee"
    if "asymmetry" in column:
        return "bilateral side-view counterparts"
    if column.startswith(("left__", "right__")):
        return "toe; MTP; ankle; knee; hip; iliac crest"
    if column in RUSTLAB1_PARAMETER_NAMES:
        return "feature-specific side/down-view RustLab1 markers"
    return ""


def formula(column: str) -> str:
    formulas = {
        "mean_hindlimb_base_support": "mean Euclidean hindpaw separation during bilateral stance",
        "variance_hindlimb_base_support": "sample variance of hindpaw separation during bilateral stance",
        "left_right_hindlimb_phase_offset": "100 * (right stance onset - left onset) / left cycle frames",
        "hindlimb_stance_overlap_fraction": "100 * bilateral stance-overlap frames / left cycle frames",
        "left_mtp_average_height": "mean left MTP height above its cycle-local lowest position",
        "left_mtp_vertical_excursion": "maximum - minimum left MTP height within the cycle",
        "right_mtp_average_height": "mean right MTP height above its cycle-local lowest position",
        "right_mtp_vertical_excursion": "maximum - minimum right MTP height within the cycle",
        "left_knee_average_height": "mean left knee height above its cycle-local lowest position",
        "left_knee_vertical_excursion": "maximum - minimum left knee height within the cycle",
        "right_knee_average_height": "mean right knee height above its cycle-local lowest position",
        "right_knee_vertical_excursion": "maximum - minimum right knee height within the cycle",
    }
    if column in ASYMMETRY_PARAMETER_NAMES:
        return "(contralesional - ipsilesional) / mean(abs(contralesional), abs(ipsilesional))"
    if column in formulas:
        return formulas[column]
    if column.startswith(("left__", "right__")):
        return "ALMA KinematicsFunctions definition evaluated on the matched canonical cycle"
    if column in RUSTLAB1_PARAMETER_NAMES:
        return "RustLab1-derived definition evaluated on the authoritative ALMA stride window"
    return "cycle metadata or quality-control value; see feature name"
