"""Persist detected or reviewed Ladder events with the existing single/dual-view CSV schemas."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import (
    COMBINED_LADDER_OUTPUT_COLUMNS,
    LADDER_OUTPUT_COLUMNS,
    LadderEvent,
)


def write_ladder_events(
    events: list[LadderEvent] | tuple[LadderEvent, ...], output_file: Path, *, combined: bool | None = None
) -> Path:
    """Write reviewed events using ALMA-compatible columns."""
    import csv

    if combined is None:
        combined = any(event.view != "single" or event.source_file for event in events)
    columns = COMBINED_LADDER_OUTPUT_COLUMNS if combined else LADDER_OUTPUT_COLUMNS
    rows = []
    for event in events:
        if not event.included:
            continue
        classification = "" if event.classification in ("unreviewed", "footfall") else event.classification
        row = {
            "time (frame)": int(event.peak_frame),
            "depth (pixel)": float(event.depth_px),
            "start (frame)": int(event.start_frame),
            "end (frame)": int(event.end_frame),
            "duration (s)": float(event.duration_s),
            "bodypart": event.bodypart,
            "slip or fall": classification,
        }
        if combined:
            row["view"] = event.view
            row["source file"] = event.source_file
        rows.append(row)
    output_file = Path(output_file).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return output_file


class LadderEventExporter:
    def write(self, events, destination, combined=False):
        return write_ladder_events(events, destination, combined=combined)
