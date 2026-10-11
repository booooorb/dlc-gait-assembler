"""Validate manual classifications and inclusion while retaining detection coordinates."""

from dataclasses import replace

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderEvent

LADDER_REVIEW_CLASSIFICATIONS = ("unreviewed", "footfall", "slip", "fall")


def review_ladder_event(event: LadderEvent, classification: str, included: bool = True) -> LadderEvent:
    if classification not in LADDER_REVIEW_CLASSIFICATIONS:
        raise ValueError(f"Unknown Ladder classification: {classification}")
    return replace(event, classification=classification, included=bool(included))
