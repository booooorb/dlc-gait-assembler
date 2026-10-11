"""KneeEditorState owns selections, editable state, and preview validity for this workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import CoordinateFilePair


@dataclass
class KneeEditorState:
    profile_knee_manifest_path: Path | None = None
    selected_paths: list[Path] = field(default_factory=lambda: [])
    pairs: list[CoordinateFilePair] = field(default_factory=lambda: [])
    calibration_map_path: Path | None = None
    pixels_per_cm: float | None = None
    preview_original: object | None = None
    preview_corrected: object | None = None
    preview_report: object | None = None
    preview_cache: dict = field(default_factory=lambda: {})
    active_preview_pair_key: tuple[str, str, str] | None = None
    preview_frame_positions: tuple[int, ...] = ()
    preview_media_path: Path | None = None
    preview_video_frame_count: int = 0
