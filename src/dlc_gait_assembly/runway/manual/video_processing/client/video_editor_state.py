"""VideoEditorState owns selections, editable state, and preview validity for this workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange


@dataclass
class VideoEditorState:
    current_video: Path | None = None
    duration_ms: int = 0
    fps: float = 0.0
    frame_count: int = 0
    loading_slider: bool = False
    pending_frame_ms: int | None = None
    processing_errors: list[str] = field(default_factory=lambda: [])
    processing_failures: list[tuple[str, str]] = field(default_factory=lambda: [])
    processing_outputs: list[tuple[str, str]] = field(default_factory=lambda: [])
    processing_options: ProcessingOptions | None = None
    processing_video_paths: list[Path] = field(default_factory=lambda: [])
    processing_trim_ranges_by_path: dict[str, tuple[TrimRange, ...]] = field(default_factory=lambda: {})
    profile_manifest_path: Path | None = None
    trim_ranges_by_video: dict[str, list[TrimRange]] = field(default_factory=lambda: {})
    active_trim_range_by_video: dict[str, int] = field(default_factory=lambda: {})
