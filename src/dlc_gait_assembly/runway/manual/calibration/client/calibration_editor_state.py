"""CalibrationEditorState owns selections, editable state, and preview validity for this workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick


@dataclass
class CalibrationEditorState:
    profile_calibration_map_path: Path | None = None
    current_media: Path | None = None
    calibration_sticks_by_media: dict[str, tuple[CalibrationStick, ...]] = field(default_factory=lambda: {})
    timeline_ms_by_media: dict[str, int] = field(default_factory=lambda: {})
    duration_ms: int = 0
    fps: float = 0.0
    frame_count: int = 0
    loading_slider: bool = False
    loading_media: bool = False
    pending_frame_ms: int | None = None
