"""Combine maintained parameter definitions for selection, documentation, and export."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
    ALMA_REMOVED_VARIABILITY_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    alma_definition as _alma_definition,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    alma_multiview_definition as _alma_multiview_definition,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.bottom_paw_parameter_contract import (
    without_retired_bottom_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_contracts import (
    GaitParameterDefinition,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_PARAMETER_NAMES,
)


def gait_parameter_catalog() -> tuple[GaitParameterDefinition, ...]:
    definitions = [_alma_definition(name) for name in ALMA_PARAMETER_NAMES]
    definitions.extend(
        _alma_multiview_definition(side, name) for side in ("left", "right") for name in ALMA_PARAMETER_NAMES
    )
    definitions.extend(rustlab1_definition(name) for name in RUSTLAB1_PARAMETER_NAMES)
    definitions.extend(custom_definition(name) for name in CUSTOM_SOP_PARAMETER_NAMES)
    return tuple(definitions)


def rustlab1_definition(name: str) -> GaitParameterDefinition:
    if name in {"FLBR_RATIO", "FRBL_RATIO"}:
        diagonal = "left forepaw and right hindpaw" if name == "FLBR_RATIO" else "right forepaw and left hindpaw"
        return GaitParameterDefinition(
            name,
            "RustLab1",
            "Multi-view",
            "Bottom view",
            "All four paws (lhpaw, rhpaw, lfpaw, rfpaw)",
            f"fraction of non-all-stance gait-cycle frames in which the {diagonal} occupy different stance/swing phases",
            f"{diagonal.title()} asynchronous-phase fraction",
        )
    if name.endswith("__front__seconds"):
        side = "Left" if name.startswith("left__") else "Right"
        return GaitParameterDefinition(
            name,
            "RustLab1",
            "Multi-view",
            "Bottom view",
            f"Bottom {side.lower()} forepaw ({'lfpaw' if side == 'Left' else 'rfpaw'})",
            "median interval between consecutive forepaw stance onsets overlapping the ALMA gait-cycle window / frame rate",
            f"{side} forelimb step duration (s)",
        )
    if name.startswith(("avg_Angle__", "max_Angle__", "min_Angle__")):
        (statistic_key, side, _limb, joint) = name.split("__", 3)
        statistic = {"avg_Angle": "mean", "max_Angle": "95th percentile", "min_Angle": "10th percentile"}[statistic_key]
        joint_label = "elbow" if joint == "shoulder_ellbow_wrist" else "wrist"
        markers = "Shoulder, elbow, and wrist" if joint_label == "elbow" else "Elbow, wrist, and fore toe tip"
        return GaitParameterDefinition(
            name,
            "RustLab1",
            "Multi-view",
            f"{side.title()} side view",
            f"{side.title()} {markers.lower()}",
            f"absolute value of the signed {joint_label}-angle {statistic} within the ALMA gait-cycle window",
            f"{side.title()} forelimb {joint_label} angle — {statistic} (deg)",
        )
    side = "Left" if name.startswith(("l-", "left__")) else "Right"
    if "Average_Height" in name:
        marker = name.split("__", 1)[0]
        calculation = "mean vertical height above the cycle-local minimum, converted to millimetres"
        markers = marker
    elif "__Movement" in name:
        marker = name.split("__", 1)[0]
        calculation = "maximum - minimum vertical marker position within the cycle, converted to millimetres"
        markers = marker
    elif "movement_per_step" in name:
        calculation = "change in mean hip x-position from the previous same-limb cycle, converted to millimetres"
        markers = f"{side} hip"
    else:
        statistic = {
            "average": "mean",
            "median": "median",
            "protraction": "95th percentile",
            "retraction": "5th percentile",
        }.get(name.rsplit("__", 1)[-1], "summary")
        forelimb = "__front__" in name
        reference = "shoulder" if forelimb else "hip"
        limb = "fore" if forelimb else "hind"
        calculation = f"{statistic} {limb} toe x-position minus {reference} x-position, converted to millimetres"
        markers = f"{side} {limb} toe and {reference}"
    return GaitParameterDefinition(
        name, "RustLab1", "Multi-view", f"{side} side view", markers, calculation, rustlab1_display_name(name)
    )


def rustlab1_display_name(name: str) -> str:
    side = "Left" if name.startswith(("l-", "left__")) else "Right"
    if name.startswith(
        (
            "l-back-",
            "r-back-",
            "l-front-",
            "r-front-",
            "l-wrist",
            "r-wrist",
            "l-elbow",
            "r-elbow",
            "l-shoulder",
            "r-shoulder",
        )
    ):
        marker_name = name.split("__", 1)[0]
        if marker_name.endswith("back-toe"):
            bodypart = "hindpaw"
        elif marker_name.endswith("front-toe-tip"):
            bodypart = "forepaw"
        else:
            bodypart = marker_name.rsplit("-", 1)[-1]
        measure = "average height" if name.endswith("Average_Height") else "vertical excursion"
        return f"{side} {bodypart} {measure} (mm)"
    if name.startswith(("l-hip__", "r-hip__", "l-iliac-crest__", "r-iliac-crest__")):
        marker_name = name.split("__", 1)[0]
        bodypart = "iliac crest" if marker_name.endswith("iliac-crest") else "hip"
        measure = "average height" if name.endswith("Average_Height") else "vertical excursion"
        return f"{side} {bodypart} {measure} (mm)"
    if name.endswith("movement_per_step"):
        return f"{side} hip displacement per step (cm)"
    if name.endswith("__front__seconds"):
        return f"{side} forelimb step duration (s)"
    statistic = name.rsplit("__", 1)[-1]
    measure = {
        "average": "mean position",
        "median": "median position",
        "protraction": "protraction",
        "retraction": "retraction",
    }[statistic]
    forelimb = "__front__" in name
    return f"{side} {('forepaw' if forelimb else 'hindpaw')} {measure} relative to {('shoulder' if forelimb else 'hip')} (mm)"


def custom_definition(name: str) -> GaitParameterDefinition:
    formulas = {
        "mean_hindlimb_base_support": "mean Euclidean separation of left and right hindpaws during bilateral stance",
        "variance_hindlimb_base_support": "sample variance of hindpaw separation during bilateral stance",
        "left_right_hindlimb_phase_offset": "100 × first right stance onset offset / gait-cycle frames",
        "hindlimb_stance_overlap_fraction": "100 × bilateral stance-overlap frames / gait-cycle frames",
    }
    if name in formulas:
        views = "Bottom view"
        markers = "Left hindpaw (lhpaw) and right hindpaw (rhpaw)"
        return GaitParameterDefinition(name, "Custom SOP", "Multi-view", views, markers, formulas[name])
    side = "Left" if name.startswith("left") else "Right"
    marker = "MTP" if "mtp" in name else "knee"
    if name.endswith("average_height"):
        calculation = "mean height above the cycle-local lowest marker position"
    else:
        calculation = "maximum - minimum marker height within the gait cycle"
    return GaitParameterDefinition(
        name, "Custom SOP", "Multi-view", f"{side} side view", f"{side} {marker}", calculation
    )


def selected_alma_output(parameters, settings: AlmaSettings, side: str | None = None):
    parameters = parameters.drop(
        columns=[
            name
            for name in parameters
            if name.removeprefix("left__").removeprefix("right__") in ALMA_REMOVED_VARIABILITY_NAMES
        ],
        errors="ignore",
    )
    selected = settings.enabled_parameter_names
    if selected is None:
        return parameters
    selected_set = set(selected)
    has_side_selection = any(name.startswith(("left__", "right__")) for name in selected_set)
    gait_columns = set(ALMA_PARAMETER_NAMES)
    columns = [
        column
        for column in parameters.columns
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


def selected_combined_output(parameters, settings: AlmaSettings):
    parameters = without_retired_bottom_parameters(parameters)
    parameters = parameters.drop(
        columns=[
            name
            for name in parameters
            if name.removeprefix("left__").removeprefix("right__") in ALMA_REMOVED_VARIABILITY_NAMES
        ],
        errors="ignore",
    )
    selected = settings.enabled_parameter_names
    if selected is None:
        return parameters
    selected_set = set(selected)
    has_side_selection = any(name.startswith(("left__", "right__")) for name in selected_set)
    catalog_names = set(ALMA_PARAMETER_NAMES) | set(RUSTLAB1_PARAMETER_NAMES) | set(CUSTOM_SOP_PARAMETER_NAMES)

    def is_enabled(column: str) -> bool:
        if column in catalog_names:
            return column in selected_set
        if column.startswith(("left__", "right__")):
            unprefixed = column.split("__", 1)[1]
            if unprefixed in ALMA_PARAMETER_NAMES:
                return column in selected_set if has_side_selection else unprefixed in selected_set
        return True

    return parameters.loc[:, [column for column in parameters if is_enabled(column)]]
