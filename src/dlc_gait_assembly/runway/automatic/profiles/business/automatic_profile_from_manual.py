"""Construct profile requests from typed snapshots of open manual workspaces."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
from pathlib import Path

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import (
    CalibrationSettingsSnapshot,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import VideoSettingsSnapshot


@dataclass(frozen=True)
class ManualProfileSnapshot:
    """Values and previously exported fallbacks; no widget references or file access."""

    video: VideoSettingsSnapshot | None = None
    calibration: CalibrationSettingsSnapshot | None = None
    gait: AlmaSettings | None = None
    knee: KneeCorrectionSettings | None = None
    processing_manifest: Path | None = None
    calibration_map: Path | None = None
    analysis_manifest: Path | None = None
    knee_manifest: Path | None = None


@dataclass(frozen=True)
class ManualProfileAssets:
    processing_manifest: Path | None = None
    calibration_map: Path | None = None
    analysis_manifest: Path | None = None
    knee_manifest: Path | None = None

    def present_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in fields(self) if getattr(self, field.name) is not None)


def combine_manual_snapshots(snapshots: Iterable[ManualProfileSnapshot]) -> ManualProfileSnapshot:
    """Take the first available value in application stage order for each field."""
    ordered = tuple(snapshots)
    return ManualProfileSnapshot(
        **{
            field.name: next(
                (getattr(snapshot, field.name) for snapshot in ordered if getattr(snapshot, field.name) is not None),
                None,
            )
            for field in fields(ManualProfileSnapshot)
        }
    )
