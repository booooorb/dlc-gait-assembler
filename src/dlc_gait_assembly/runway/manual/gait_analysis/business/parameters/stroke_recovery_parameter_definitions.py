"""Define research outcomes, extraction types, units, and provenance for stroke recovery."""

from dataclasses import dataclass

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_contracts import (
    GaitParameterDefinition,
    ParameterExtractionType,
)

ALMA_REFERENCE = "https://doi.org/10.1038/s42003-022-03077-6"
WEBER_REFERENCE = "https://doi.org/10.1186/s12915-022-01434-9"
MOUSEWALKER_REFERENCE = "https://doi.org/10.1186/s12915-015-0154-0"
SYMMETRY_REFERENCE = "https://doi.org/10.1007/s11357-024-01210-3"
VARIABILITY_REFERENCE = "https://doi.org/10.3390/sym14101995"
SOURCE = "Stroke recovery"

# These are extensions of the published trajectory measures, not additional
# parameters claimed to have been validated by ALMA or Weber et al.
STROKE_STRIDE_MEASURES = {
    "hindpaw_robust_excursion (cm)": (
        "Hindpaw protraction–retraction excursion (cm)",
        "P95(toe x - hip x) - P5(toe x - hip x), divided by this side's pixels/cm",
        "Toe and hip",
        "cm",
        ParameterExtractionType.KINEMATICS,
    ),
    "swing_mean_toe_clearance (cm)": (
        "Mean toe clearance during swing (cm)",
        "mean(stance median toe y - swing toe y) / this side's pixels/cm",
        "Toe",
        "cm",
        ParameterExtractionType.SWING,
    ),
    "swing_peak_clearance_time (%)": (
        "Time of peak toe clearance within swing (%)",
        "100 × (peak clearance frame - swing onset) / swing duration in frames",
        "Toe",
        "% of swing",
        ParameterExtractionType.SWING,
    ),
    "swing_knee_range_of_motion (deg)": (
        "Knee range of motion during swing (deg)",
        "max(ankle-knee-hip angle) - min(angle), using swing frames only",
        "Ankle, knee and hip",
        "deg",
        ParameterExtractionType.SWING,
    ),
    "swing_ankle_range_of_motion (deg)": (
        "Ankle range of motion during swing (deg)",
        "max(MTP-ankle-knee angle) - min(angle), using swing frames only",
        "MTP, ankle and knee",
        "deg",
        ParameterExtractionType.SWING,
    ),
}
STROKE_STRIDE_NAMES = tuple(STROKE_STRIDE_MEASURES)
BOTTOM_RECOVERY_NAMES = (
    "hindlimb_single_support (%)",
    "opposite_hindlimb_single_support (%)",
    "hindlimb_phase_alternation_error (%)",
)


@dataclass(frozen=True)
class RecoveryOutcome:
    key: str
    label: str
    columns: tuple[str, ...]
    unit: str
    markers: str
    reference: str
    factor: float = 1.0
    forelimb: bool = False
    variability: bool = False


RECOVERY_OUTCOMES = (
    RecoveryOutcome(
        "stride_duration", "Stride duration", ("cycle duration (s)",), "s", "Toe", ALMA_REFERENCE, variability=True
    ),
    RecoveryOutcome("stance_duration", "Stance duration", ("stance duration (s)",), "s", "Toe", WEBER_REFERENCE),
    RecoveryOutcome("swing_duration", "Swing duration", ("swing duration (s)",), "s", "Toe", WEBER_REFERENCE),
    RecoveryOutcome(
        "stride_length", "Stride length", ("stride length (cm)",), "cm", "Toe", ALMA_REFERENCE, variability=True
    ),
    RecoveryOutcome(
        "step_height",
        "Hindpaw vertical excursion (ALMA step height)",
        ("step height (cm)",),
        "cm",
        "Toe",
        ALMA_REFERENCE,
        variability=True,
    ),
    RecoveryOutcome(
        "knee_range_of_motion",
        "Knee range of motion",
        ("knee joint amplitude (deg)",),
        "deg",
        "Ankle, knee and hip",
        ALMA_REFERENCE,
    ),
    RecoveryOutcome(
        "ankle_range_of_motion",
        "Ankle range of motion",
        ("ankle joint amplitude (deg)",),
        "deg",
        "MTP, ankle and knee",
        ALMA_REFERENCE,
    ),
    RecoveryOutcome(
        "hindpaw_robust_excursion",
        "Hindpaw protraction–retraction excursion",
        ("hindpaw_robust_excursion (cm)",),
        "cm",
        "Toe and hip",
        WEBER_REFERENCE,
    ),
    RecoveryOutcome(
        "forepaw_vertical_excursion",
        "Forepaw vertical excursion",
        ("{prefix}-front-toe-tip__Movement",),
        "cm",
        "Fore toe",
        WEBER_REFERENCE,
        factor=0.1,
        forelimb=True,
    ),
    RecoveryOutcome(
        "forepaw_robust_excursion",
        "Forepaw protraction–retraction excursion",
        ("{side}__front__protraction", "{side}__front__retraction"),
        "cm",
        "Fore toe and shoulder",
        WEBER_REFERENCE,
        factor=0.1,
        forelimb=True,
    ),
    RecoveryOutcome(
        "wrist_vertical_excursion",
        "Wrist vertical excursion",
        ("{prefix}-wrist__Movement",),
        "cm",
        "Wrist",
        WEBER_REFERENCE,
        factor=0.1,
        forelimb=True,
    ),
)


def recovery_outcomes(limb_scope):
    return tuple(
        outcome for outcome in RECOVERY_OUTCOMES if not outcome.forelimb or limb_scope == "Hindlimb + Forelimb"
    )


def stroke_recovery_definitions():
    definitions = []
    for view in ("side", "left", "right"):
        for name, (label, formula, markers, unit, extraction_type) in STROKE_STRIDE_MEASURES.items():
            definitions.append(
                GaitParameterDefinition(
                    name if view == "side" else f"{view}__{name}",
                    SOURCE,
                    "Single-view" if view == "side" else "Multi-view",
                    "Side view" if view == "side" else f"{view.title()} side view",
                    markers,
                    formula,
                    label if view == "side" else f"{view.title()} · {label}",
                    extraction_type,
                    unit,
                    reference=WEBER_REFERENCE if "excursion" in name else ALMA_REFERENCE,
                    method_note="Study-derived extension on accepted ALMA cycles; no baseline normalization. Image y increases downward. Missing required samples leave the value blank.",
                )
            )
    for name, label, formula in (
        (
            BOTTOM_RECOVERY_NAMES[0],
            "Reference hindlimb single support (%)",
            "100 × time(reference hindpaw stance AND opposite hindpaw swing) / cycle time",
        ),
        (
            BOTTOM_RECOVERY_NAMES[1],
            "Opposite hindlimb single support (%)",
            "100 × time(opposite hindpaw stance AND reference hindpaw swing) / cycle time",
        ),
        (
            BOTTOM_RECOVERY_NAMES[2],
            "Hindlimb departure from alternation (%)",
            "abs(opposite hindlimb stance-onset phase (%) - 50)",
        ),
    ):
        definitions.append(
            GaitParameterDefinition(
                name,
                SOURCE,
                "Multi-view",
                "Bottom view",
                "Left hindpaw (lhpaw) and right hindpaw (rhpaw)",
                formula,
                label,
                ParameterExtractionType.COORDINATION,
                "% of cycle",
                reference=MOUSEWALKER_REFERENCE,
                method_note="Study-derived hindlimb coordination measure. Hindlimb single support does not imply only one of all four paws contacts the ground. Phase error is relative to 50% alternation, not to the animal's baseline.",
            )
        )
    for outcome in RECOVERY_OUTCOMES:
        for suffix, label, formula in (
            ("symmetry_index (%)", "absolute symmetry index", "200 × abs(L - R) / (abs(L) + abs(R))"),
            (
                "lesion_asymmetry (%)",
                "signed lesion asymmetry",
                "200 × (contralesional - ipsilesional) / (abs(contralesional) + abs(ipsilesional))",
            ),
        ):
            definitions.append(
                GaitParameterDefinition(
                    f"{outcome.key}_{suffix}",
                    SOURCE,
                    "Multi-view",
                    "Left and right side views",
                    f"Bilateral {outcome.markers.lower()}",
                    formula,
                    f"{outcome.label} · {label} (%)",
                    ParameterExtractionType.ASYMMETRY,
                    "%",
                    "recording",
                    f"{outcome.reference}; {SYMMETRY_REFERENCE}",
                    "Study-derived comparison of independent side medians over complete accepted strides in the common camera interval. Requires the configured minimum count per side. SI=0 is symmetry; signed positive means larger contralesional value. A zero denominator is undefined. Lesion asymmetry is blank without left/right lesion metadata. Not a recovery score or a paired-stride statistic.",
                    outcome.forelimb,
                )
            )
        if outcome.variability:
            for side in ("left", "right"):
                definitions.append(
                    GaitParameterDefinition(
                        f"{side}__{outcome.key}_cv (%)",
                        SOURCE,
                        "Multi-view",
                        f"{side.title()} side view",
                        outcome.markers,
                        "100 × sample SD / abs(mean), across accepted complete same-side strides in the common interval",
                        f"{side.title()} {outcome.label.lower()} · coefficient of variation (%)",
                        ParameterExtractionType.VARIABILITY,
                        "%",
                        "recording",
                        VARIABILITY_REFERENCE,
                        "Descriptive statistical extension to rodent strides; CV is also used in human stroke gait studies. Requires at least three strides and the configured minimum count. Zero mean is undefined. Distinct from within-cycle SD and retired ALMA trajectory variability.",
                    )
                )
    return tuple(definitions)
