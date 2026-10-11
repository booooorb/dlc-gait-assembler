"""AutomaticProfileEditorState owns selections, editable state, and preview validity for this workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile


@dataclass
class AutomaticProfileEditorState:
    profiles: dict[str, AutomatedPipelineProfile] = field(default_factory=lambda: {})
    current_profile_id: str | None = None
    manifest_source: Path | None = None
    calibration_source: Path | None = None
    analysis_manifest_source: Path | None = None
    knee_manifest_source: Path | None = None
    regions: tuple[str, ...] = ()
    model_sources: dict[str, Path | None] = field(default_factory=lambda: {})
    saved_snapshot: tuple[str, ...] | None = None
