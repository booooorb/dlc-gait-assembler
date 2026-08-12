from __future__ import annotations

from dataclasses import dataclass

from dlc_gait_assembly.services.pipeline.rustlab1.extraction import (
    CUSTOM_SOP_PARAMETER_NAMES,
    RUSTLAB1_PARAMETER_NAMES,
)


@dataclass(frozen=True)
class GaitParameterDefinition:
    name: str
    source: str
    view_mode: str
    views: str
    markers: str
    calculation: str


ALMA_PARAMETER_NAMES = (
    "cycle duration (s)",
    "cycle duration (no. frames)",
    "cycle velocity (cm/s)",
    "stride length (cm)",
    "stance duration (s)",
    "swing duration (s)",
    "swing percentage (%)",
    "stance percentage (%)",
    "mean toe-to-crest distance (cm)",
    "max toe-to-crest distance (cm)",
    "min toe-to-crest distance (cm)",
    "toe-to-crest distance SD (cm)",
    "step height (cm)",
    "max velocity during swing (cm/s)",
    "mtp joint extension (deg)",
    "mtp joint flexion (deg)",
    "mtp joint amplitude (deg)",
    "mtp joint SD (deg)",
    "ankle joint extension (deg)",
    "ankle joint flexion (deg)",
    "ankle joint amplitude (deg)",
    "ankle joint SD (deg)",
    "knee joint extension (deg)",
    "knee joint flexion (deg)",
    "knee joint amplitude (deg)",
    "knee joint SD (deg)",
    "hip joint extension (deg)",
    "hip joint flexion (deg)",
    "hip joint amplitude (deg)",
    "hip joint SD (deg)",
    "drag duration (s)",
    "drag percentage (%)",
    "Variability x plane 5 strides mean",
    "Variability x plane 5 strides SD",
    "Variability y plane 5 strides mean",
    "Variability y plane 5 strides SD",
    "Variability xy plane 5 strides mean",
    "Variability xy plane 5 strides SD",
    "Variability x plane 10 strides mean",
    "Variability x plane 10 strides SD",
    "Variability y plane 10 strides mean",
    "Variability y plane 10 strides SD",
    "Variability xy plane 10 strides mean",
    "Variability xy plane 10 strides SD",
)


def gait_parameter_catalog() -> tuple[GaitParameterDefinition, ...]:
    definitions = [_alma_definition(name) for name in ALMA_PARAMETER_NAMES]
    definitions.extend(_rustlab1_definition(name) for name in RUSTLAB1_PARAMETER_NAMES)
    definitions.extend(_custom_definition(name) for name in CUSTOM_SOP_PARAMETER_NAMES)
    return tuple(definitions)


def _alma_definition(name: str) -> GaitParameterDefinition:
    lowered = name.lower()
    markers = "Toe and iliac crest"
    if "joint" in lowered:
        joint = lowered.split(" joint", 1)[0]
        markers = _joint_markers(joint)
    elif "drag" in lowered or "step height" in lowered or "velocity during swing" in lowered:
        markers = "Toe"
    elif "stride length" in lowered or "cycle velocity" in lowered:
        markers = "Toe"
    formula = _alma_formula(name)
    return GaitParameterDefinition(name, "ALMA", "Single-view", "Side view", markers, formula)


def _alma_formula(name: str) -> str:
    formulas = {
        "cycle duration (s)": "(stride end frame - stride start frame) / frame rate",
        "cycle duration (no. frames)": "stride end frame - stride start frame",
        "cycle velocity (cm/s)": "stride length / cycle duration",
        "stride length (cm)": "absolute toe x-position change from stride start to end / pixels per cm",
        "stance duration (s)": "frames from stance onset to swing onset / frame rate",
        "swing duration (s)": "frames from swing onset to the next stance onset / frame rate",
        "swing percentage (%)": "100 × swing frames / cycle frames",
        "stance percentage (%)": "100 × stance frames / cycle frames",
        "mean toe-to-crest distance (cm)": "mean Euclidean toe-to-iliac-crest distance across the cycle / pixels per cm",
        "max toe-to-crest distance (cm)": "maximum Euclidean toe-to-iliac-crest distance / pixels per cm",
        "min toe-to-crest distance (cm)": "minimum Euclidean toe-to-iliac-crest distance / pixels per cm",
        "toe-to-crest distance SD (cm)": "standard deviation of toe-to-iliac-crest distance / pixels per cm",
        "step height (cm)": "highest swing toe position relative to stance ground level / pixels per cm",
        "max velocity during swing (cm/s)": "maximum frame-to-frame toe displacement during swing × frame rate / pixels per cm",
        "drag duration (s)": "consecutive swing frames with toe clearance below the drag threshold / frame rate",
        "drag percentage (%)": "100 × dragging swing frames / total swing frames",
    }
    if name in formulas:
        return formulas[name]
    lowered = name.lower()
    if "joint extension" in lowered:
        return "maximum joint angle during the gait cycle"
    if "joint flexion" in lowered:
        return "minimum joint angle during the gait cycle"
    if "joint amplitude" in lowered:
        return "maximum joint angle - minimum joint angle"
    if "joint sd" in lowered:
        return "standard deviation of the joint angle across the gait cycle"
    if lowered.startswith("variability"):
        plane = "xy" if "xy plane" in lowered else "x" if "x plane" in lowered else "y"
        count = 10 if "10 strides" in lowered else 5
        summary = "standard deviation" if lowered.endswith(" sd") else "mean"
        return (
            f"{summary} pairwise dynamic-time-warping distance of toe trajectories in the {plane} plane "
            f"across {count} consecutive strides"
        )
    return "ALMA gait-cycle calculation"


def _rustlab1_definition(name: str) -> GaitParameterDefinition:
    if name.startswith(("LB__", "RB__")):
        side = "left" if name.startswith("LB__") else "right"
        statistic = "mean" if "avg" in name else "95th percentile" if "max" in name else "10th percentile"
        return GaitParameterDefinition(
            name,
            "RustLab1",
            "Multi-view",
            "Bottom view",
            f"Bottom {side} hindpaw and center back",
            f"{statistic} absolute hindpaw-to-center-back angle within the ALMA gait-cycle window",
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
        calculation = f"{statistic} toe x-position minus hip x-position, converted to millimetres"
        markers = f"{side} hind toe and hip"
    return GaitParameterDefinition(name, "RustLab1", "Multi-view", f"{side} side view", markers, calculation)


def _custom_definition(name: str) -> GaitParameterDefinition:
    formulas = {
        "mean_hindlimb_base_support": "mean Euclidean separation of left and right hindpaws during bilateral stance",
        "variance_hindlimb_base_support": "sample variance of hindpaw separation during bilateral stance",
        "left_hindpaw_midline_distance": "mean left hindpaw-to-center-back distance during left stance",
        "right_hindpaw_midline_distance": "mean right hindpaw-to-center-back distance during right stance",
        "left_right_hindlimb_phase_offset": "100 × first right stance onset offset / gait-cycle frames",
        "hindlimb_stance_overlap_fraction": "100 × bilateral stance-overlap frames / gait-cycle frames",
    }
    if name in formulas:
        views = "Bottom view"
        markers = "Left hindpaw, right hindpaw, and center back"
        return GaitParameterDefinition(name, "Custom SOP", "Multi-view", views, markers, formulas[name])
    side = "Left" if name.startswith("left") else "Right"
    marker = "MTP" if "mtp" in name else "knee"
    if name.endswith("average_height"):
        calculation = "mean height above the cycle-local lowest marker position"
    else:
        calculation = "maximum - minimum marker height within the gait cycle"
    return GaitParameterDefinition(
        name,
        "Custom SOP",
        "Multi-view",
        f"{side} side view",
        f"{side} {marker}",
        calculation,
    )


def _joint_markers(joint: str) -> str:
    return {
        "mtp": "Toe, MTP, and ankle",
        "ankle": "MTP, ankle, and knee",
        "knee": "Ankle, knee, and hip",
        "hip": "Knee, hip, and iliac crest",
    }.get(joint, "Adjacent joint markers")


__all__ = ["ALMA_PARAMETER_NAMES", "GaitParameterDefinition", "gait_parameter_catalog"]
