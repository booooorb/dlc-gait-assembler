"""Define ALMA measurement names, units, descriptions, and marker requirements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_contracts import (
    GaitParameterDefinition,
)

ALMA_REMOVED_VARIABILITY_NAMES = (
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
)
ALMA_MULTIVIEW_PARAMETER_NAMES = tuple(f"{side}__{name}" for side in ("left", "right") for name in ALMA_PARAMETER_NAMES)


def alma_multiview_definition(side: str, name: str) -> GaitParameterDefinition:
    base = alma_definition(name)
    side_label = side.title()
    return GaitParameterDefinition(
        f"{side}__{name}",
        "ALMA",
        "Multi-view",
        f"{side_label} side view",
        f"{side_label} {base.markers.lower()}",
        base.calculation,
    )


def alma_definition(name: str) -> GaitParameterDefinition:
    lowered = name.lower()
    markers = "Toe and iliac crest"
    if "joint" in lowered:
        joint = lowered.split(" joint", 1)[0]
        markers = joint_markers(joint)
    elif "drag" in lowered or "step height" in lowered or "velocity during swing" in lowered:
        markers = "Toe"
    elif "stride length" in lowered or "cycle velocity" in lowered:
        markers = "Toe"
    formula = alma_formula(name)
    return GaitParameterDefinition(name, "ALMA", "Single-view", "Side view", markers, formula)


def alma_formula(name: str) -> str:
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
        return f"{summary} pairwise dynamic-time-warping distance of toe trajectories in the {plane} plane across {count} consecutive strides"
    return "ALMA gait-cycle calculation"


def joint_markers(joint: str) -> str:
    return {
        "mtp": "Toe, MTP, and ankle",
        "ankle": "MTP, ankle, and knee",
        "knee": "Ankle, knee, and hip",
        "hip": "Knee, hip, and iliac crest",
    }.get(joint, "Adjacent joint markers")


def parameter_unit(parameter: str) -> str:
    lowered = parameter.lower()
    if "(cm/s)" in lowered:
        return "cm/s"
    if "(cm)" in lowered:
        return "cm"
    if "(deg)" in lowered:
        return "degrees"
    if "(s)" in lowered:
        return "seconds"
    if "(%)" in lowered:
        return "percent"
    if "frames" in lowered:
        return "frames"
    return "unitless"
