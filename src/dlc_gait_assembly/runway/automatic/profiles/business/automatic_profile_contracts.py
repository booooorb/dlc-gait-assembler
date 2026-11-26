"""Define saved automatic profiles, asset references, and readiness results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FINE_TUNE_EPOCHS = 30
MAX_FINE_TUNE_EPOCHS = 2_147_483_647


def validate_fine_tune_epochs(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_FINE_TUNE_EPOCHS:
        raise ValueError(f"Fine-tuning epochs must be between 1 and {MAX_FINE_TUNE_EPOCHS}.")
    return value


def validate_deeplabcut_shuffles(shuffles: dict[str, int], models) -> dict[str, int]:
    if not isinstance(shuffles, dict) or any(
        region not in models or type(shuffle) is not int or shuffle < 0 for region, shuffle in shuffles.items()
    ):
        raise ValueError("A DeepLabCut shuffle selection is invalid for its assigned region.")
    return dict(shuffles)


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
    workspace_state: dict = field(default_factory=dict)
    labeled_video_confidence: float | None = None
    fine_tune_epochs: int = DEFAULT_FINE_TUNE_EPOCHS
    deeplabcut_shuffles: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileDraft:
    """Editable profile inputs before the store owns copies of their assets."""

    name: str
    processing_manifest: Path | None
    calibration_map: Path | None
    deeplabcut_models: dict[str, Path]
    analysis_manifest: Path | None = None
    knee_manifest: Path | None = None
    gait_analysis_enabled: bool = True
    knee_correction_enabled: bool = False
    labeled_video_confidence: float | None = None
    fine_tune_epochs: int = DEFAULT_FINE_TUNE_EPOCHS
    deeplabcut_shuffles: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> tuple[str, ...]:
        """Return a deterministic value suitable for dirty-state comparisons."""
        models = tuple(
            f"{region}={path}, shuffle={self.deeplabcut_shuffles.get(region)}"
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
            str(self.labeled_video_confidence),
            str(self.fine_tune_epochs),
            *models,
        )
