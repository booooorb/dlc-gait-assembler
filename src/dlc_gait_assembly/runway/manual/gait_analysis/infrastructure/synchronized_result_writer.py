"""Persist calculated synchronized cycle tables, session summaries, and QC metadata."""

from __future__ import annotations

import json
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_output_contracts import (
    StrokeOutputBundle,
)


def write_synchronized_recording(calculation, view_set, output_folder):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    stem = view_set.name
    paths = {name: output_folder / f"{stem}_{name}.csv" for name in calculation.tables}
    paths["qc_report"] = output_folder / f"{stem}_qc_report.json"
    for name, table in calculation.tables.items():
        table.to_csv(paths[name], index=False)
    paths["qc_report"].write_text(json.dumps(calculation.qc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return StrokeOutputBundle(**paths, messages=calculation.messages)
