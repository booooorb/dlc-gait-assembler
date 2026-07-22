"""Typed models shared by automated-profile persistence and user interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AutomatedPipelineProfile:
    id: str
    name: str
    processing_manifest: Path | None
    calibration_map: Path | None
    deeplabcut_models: dict[str, Path]
    analysis_manifest: Path | None = None
    knee_manifest: Path | None = None
    gait_analysis_enabled: bool = True
    knee_correction_enabled: bool = False
    updated_at: str = ""


@dataclass(frozen=True)
class ProfileDraft:
    """Editable profile inputs before the store owns copies of their assets."""

    name: str
    processing_manifest: Path
    calibration_map: Path | None
    deeplabcut_models: dict[str, Path]
    analysis_manifest: Path | None = None
    knee_manifest: Path | None = None
    gait_analysis_enabled: bool = True
    knee_correction_enabled: bool = False

    def snapshot(self) -> tuple[str, ...]:
        """Return a deterministic value suitable for dirty-state comparisons."""

        models = tuple(
            f"{region}={path}"
            for region, path in sorted(self.deeplabcut_models.items())
        )
        return (
            self.name.strip(),
            str(self.processing_manifest or ""),
            str(self.calibration_map or ""),
            str(self.analysis_manifest or ""),
            str(self.knee_manifest or ""),
            str(self.gait_analysis_enabled),
            str(self.knee_correction_enabled),
            *models,
        )
