"""Resolve required markers and aliases for the selected method, camera views, and limb scope."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import normalized_bodypart_label

STANDARD_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")
SIDE_VIEW_LABELS = STANDARD_BODYPARTS
BOTTOM_VIEW_LABELS = ("back left", "back right", "front left", "front right")
FORELIMB_SIDE_VIEW_LABELS = ("front toe tip", "wrist", "elbow", "shoulder")
FORELIMB_BOTTOM_VIEW_LABELS = ("front left", "front right")
MULTI_SIDE_VIEW_MODE_LABEL = "Multi side view"
SINGLE_SIDE_VIEW_MODE_LABEL = "Single side view"
BODY_PART_ALIASES = {
    "toe": (
        "back_toe",
        "back toe tip",
        "toe",
        "toer",
        "toel",
        "toe_r",
        "toe_l",
        "l-back-toe",
        "l-back-toe_tip",
        "r-back-toe",
        "r-back-toe_tip",
    ),
    "mtp": ("mtp", "mtpr", "mtpl", "mtp_r", "mtp_l", "l-back-mtp", "r-back-mtp"),
    "ankle": ("ankle", "ankler", "anklel", "ankle_r", "ankle_l", "l-back-ankle", "r-back-ankle"),
    "knee": ("knee", "kneer", "kneel", "knee_r", "knee_l", "l-back-knee", "r-back-knee"),
    "hip": ("hip", "hipr", "hipl", "hip_r", "hip_l", "l-hip", "r-hip"),
    "iliac crest": (
        "iliac crest",
        "iliac-crest",
        "iliac_crest",
        "crest",
        "crestr",
        "crestl",
        "crest_r",
        "crest_l",
        "iliac crestr",
        "iliac crestl",
        "iliacr",
        "iliacl",
        "l-iliac-crest",
        "r-iliac-crest",
    ),
    "back left": ("back left", "back-left", "left back", "left-back", "d-back-left", "lhpaw"),
    "back right": ("back right", "back-right", "right back", "right-back", "d-back-right", "rhpaw"),
    "front toe tip": ("front toe tip", "front-toe-tip", "front toe", "front-toe", "l-front-toe-tip", "r-front-toe-tip"),
    "wrist": ("wrist", "l-wrist", "r-wrist"),
    "elbow": ("elbow", "ellbow", "l-elbow", "r-elbow", "l-ellbow", "r-ellbow"),
    "shoulder": ("shoulder", "l-shoulder", "r-shoulder"),
    "front left": ("front left", "front-left", "left front", "left-front", "d-front-left", "lfpaw"),
    "front right": ("front right", "front-right", "right front", "right-front", "d-front-right", "rfpaw"),
}


def auto_bodypart_label(raw_bodyparts: list[str], standard_bodypart: str) -> str | None:
    aliases = {
        normalized_bodypart_label(alias) for alias in BODY_PART_ALIASES.get(standard_bodypart, (standard_bodypart,))
    }
    for raw_bodypart in raw_bodyparts:
        if normalized_bodypart_label(raw_bodypart) in aliases:
            return raw_bodypart
    return None


def raw_label_for_standard(mapping: dict[str, str], standard_bodypart: str) -> str | None:
    for raw_bodypart, mapped_bodypart in mapping.items():
        if mapped_bodypart == standard_bodypart:
            return raw_bodypart
    return None


def reference_segment_label(segment: str) -> str:
    labels = {
        "ankle_toe": "ankle_toe (1.5cm)",
        "hip_knee": "hip_knee (2.5cm)",
        "knee_ankle": "knee_ankle (2.0cm)",
        "ankle_mtp": "ankle_mtp (0.8cm)",
    }
    return labels.get(segment, "ankle_toe (1.5cm)")
