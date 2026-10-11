"""Coordinate left and right Ladder detections while preserving each view identity."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import DualLadderRunResult, LadderSettings


def run_dual_view_ladder_analysis(
    left_csv_file: Path,
    right_csv_file: Path,
    output_folder: Path,
    left_settings: LadderSettings,
    right_settings: LadderSettings,
    left_bodyparts: list[str],
    right_bodyparts: list[str],
    *,
    use_cases,
) -> DualLadderRunResult:
    """Analyze two side cameras independently and combine their ladder events.

    Each view keeps its own pixel-domain settings because resolution, framing,
    and camera angle can differ. Frame numbers are not rescaled or synchronized;
    the output records the source view/file for every event.
    """
    if len(left_bodyparts) != 2 or len(right_bodyparts) != 2:
        raise ValueError("Dual-view ladder analysis requires exactly two body parts per side.")
    output_folder = Path(output_folder)
    left_result = use_cases.run(left_csv_file, output_folder / "left", left_settings, left_bodyparts)
    right_result = use_cases.run(right_csv_file, output_folder / "right", right_settings, right_bodyparts)
    left_name = Path(left_csv_file).name
    right_name = Path(right_csv_file).name
    events = [replace(event, view="left", source_file=left_name) for event in left_result.events]
    events.extend(replace(event, view="right", source_file=right_name) for event in right_result.events)
    events.sort(key=lambda event: (event.peak_frame, event.view, event.bodypart))
    combined_name = f"{Path(left_csv_file).stem}__{Path(right_csv_file).stem}_ladder_combined.csv"
    output_file = use_cases.events.write(events, output_folder / combined_name, combined=True)
    return DualLadderRunResult(left_result, right_result, output_file, tuple(events))
