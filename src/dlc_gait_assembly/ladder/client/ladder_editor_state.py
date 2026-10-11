"""LadderEditorState owns selections, editable state, and preview validity for this workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderEvent


@dataclass
class LadderEditorState:
    csv_path: Path | None = None
    right_csv_path: Path | None = None
    video_path: Path | None = None
    right_video_path: Path | None = None
    events: list[LadderEvent] = field(default_factory=lambda: [])
    video_frame_counts: dict = field(default_factory=lambda: {"single": 0, "left": 0, "right": 0})
    active_preview_view: str = "single"
