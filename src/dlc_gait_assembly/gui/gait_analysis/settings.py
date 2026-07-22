"""Runway-analysis labels and pure settings helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from dlc_gait_assembly.gui.gait_analysis.pairing import normalized_bodypart_label

STANDARD_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")
SIDE_VIEW_LABELS = STANDARD_BODYPARTS
BOTTOM_VIEW_LABELS = ("center back", "back left", "back right", "body reference")
MULTI_SIDE_VIEW_MODE_LABEL = "Multi side view"
SINGLE_SIDE_VIEW_MODE_LABEL = "Single side view"
BODY_PART_ALIASES = {
    "toe": (
        "toe", "toer", "toel", "toe_r", "toe_l", "l-back-toe",
        "l-back-toe_tip", "r-back-toe", "r-back-toe_tip",
    ),
    "mtp": ("mtp", "mtpr", "mtpl", "mtp_r", "mtp_l", "l-back-mtp", "r-back-mtp"),
    "ankle": (
        "ankle", "ankler", "anklel", "ankle_r", "ankle_l",
        "l-back-ankle", "r-back-ankle",
    ),
    "knee": ("knee", "kneer", "kneel", "knee_r", "knee_l", "l-back-knee", "r-back-knee"),
    "hip": ("hip", "hipr", "hipl", "hip_r", "hip_l", "l-hip", "r-hip"),
    "iliac crest": (
        "iliac crest", "iliac-crest", "iliac_crest", "crest", "crestr",
        "crestl", "crest_r", "crest_l", "iliac crestr", "iliac crestl",
        "iliacr", "iliacl", "l-iliac-crest", "r-iliac-crest",
    ),
    "center back": (
        "center back", "center-back", "centre back", "centre-back",
        "back-center", "back-centre", "d-center-back",
    ),
    "back left": ("back left", "back-left", "left back", "left-back", "d-back-left"),
    "back right": ("back right", "back-right", "right back", "right-back", "d-back-right"),
    "body reference": (
        "body reference", "body-reference", "reference", "ref", "tail base", "tail-base",
    ),
}


def auto_bodypart_label(raw_bodyparts: list[str], standard_bodypart: str) -> str | None:
    aliases = {
        normalized_bodypart_label(alias)
        for alias in BODY_PART_ALIASES.get(standard_bodypart, (standard_bodypart,))
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


def read_dlc_bodyparts(csv_path: Path) -> list[str]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
            bodyparts = next(reader)
            coords = next(reader)
        except StopIteration as exc:
            raise ValueError(
                f"{csv_path} does not look like a DeepLabCut CSV with "
                "scorer/bodyparts/coords rows."
            ) from exc
    labels: list[str] = []
    seen: set[str] = set()
    for bodypart, coord in zip(bodyparts, coords, strict=False):
        label = bodypart.strip()
        if coord.strip().lower() == "x" and label and label not in seen:
            labels.append(label)
            seen.add(label)
    if not labels:
        raise ValueError(f"No body part labels were found in {csv_path}.")
    return labels


def reference_segment_label(segment: str) -> str:
    labels = {
        "ankle_toe": "ankle_toe (1.5cm)",
        "hip_knee": "hip_knee (2.5cm)",
        "knee_ankle": "knee_ankle (2.0cm)",
        "ankle_mtp": "ankle_mtp (0.8cm)",
    }
    return labels.get(segment, "ankle_toe (1.5cm)")
