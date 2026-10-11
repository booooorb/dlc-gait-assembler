"""Persist automatic profiles and delegate legacy-format interpretation to the format reader."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import (
    AutomatedPipelineProfile,
    ProfileDraft,
)
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_asset_store import (
    copy_profile_asset,
    copy_profile_deeplabcut_project,
    inspect_profile_draft,
    normalize_incomplete_profile_draft,
)
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_format_reader import (
    read_profile_metadata,
)

PROFILE_FORMAT_VERSION = 5


class AutomatedProfileStore:
    """Owns profile inputs without interpreting or running the pipeline."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def list_profiles(self) -> list[AutomatedPipelineProfile]:
        if not self.root.exists():
            return []
        profiles = []
        for metadata_path in self.root.glob("*/profile.json"):
            try:
                profiles.append(read_profile_metadata(metadata_path))
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(profiles, key=lambda profile: profile.name.casefold())

    def load(self, profile_id: str) -> AutomatedPipelineProfile:
        return read_profile_metadata(self._profile_dir(profile_id) / "profile.json")

    def save(
        self,
        name: str,
        processing_manifest: str | Path | None,
        calibration_map: str | Path | None,
        deeplabcut_models: dict[str, str | Path],
        profile_id: str | None = None,
        analysis_manifest: str | Path | None = None,
        knee_manifest: str | Path | None = None,
        gait_analysis_enabled: bool = True,
        knee_correction_enabled: bool | None = None,
        *,
        allow_incomplete: bool = False,
    ) -> AutomatedPipelineProfile:
        draft = ProfileDraft(
            name=name,
            processing_manifest=Path(processing_manifest) if processing_manifest is not None else None,
            calibration_map=Path(calibration_map) if calibration_map is not None else None,
            deeplabcut_models={region: Path(path) for (region, path) in deeplabcut_models.items()},
            analysis_manifest=Path(analysis_manifest) if analysis_manifest is not None else None,
            knee_manifest=Path(knee_manifest) if knee_manifest is not None else None,
            gait_analysis_enabled=bool(gait_analysis_enabled),
            knee_correction_enabled=knee_manifest is not None
            if knee_correction_enabled is None
            else bool(knee_correction_enabled),
        )
        draft = normalize_incomplete_profile_draft(draft) if allow_incomplete else inspect_profile_draft(draft)
        clean_name = draft.name
        manifest_source = draft.processing_manifest
        calibration_source = draft.calibration_map
        analysis_source = draft.analysis_manifest
        knee_source = draft.knee_manifest
        gait_analysis_enabled = draft.gait_analysis_enabled
        knee_correction_enabled = draft.knee_correction_enabled
        model_sources = draft.deeplabcut_models
        for existing in self.list_profiles():
            if existing.name.casefold() == clean_name.casefold() and existing.id != profile_id:
                raise ValueError(f'A profile named "{clean_name}" already exists.')
        profile_id = profile_id or uuid4().hex
        target_dir = self._profile_dir(profile_id)
        self.root.mkdir(parents=True, exist_ok=True)
        staging_dir = self.root / f".{profile_id}.{uuid4().hex}.staging"
        backup_dir = self.root / f".{profile_id}.{uuid4().hex}.backup"
        try:
            staging_dir.mkdir(parents=False, exist_ok=False)
            stored_manifest = (
                copy_profile_asset(manifest_source, staging_dir / "processing_manifest")
                if manifest_source is not None
                else None
            )
            stored_calibration = (
                copy_profile_asset(calibration_source, staging_dir / "calibration_map")
                if calibration_source is not None
                else None
            )
            stored_analysis = (
                copy_profile_asset(analysis_source, staging_dir / "analysis_manifest")
                if analysis_source is not None
                else None
            )
            stored_knee = (
                copy_profile_asset(knee_source, staging_dir / "knee_manifest") if knee_source is not None else None
            )
            stored_models: dict[str, Path] = {}
            for index, (region, source) in enumerate(model_sources.items(), start=1):
                stored_models[region] = copy_profile_deeplabcut_project(
                    source, staging_dir / "deeplabcut_models" / f"{index:02d}"
                )
            assets = {}
            if stored_manifest is not None:
                assets["processing_manifest"] = str(stored_manifest.relative_to(staging_dir))
            if stored_calibration is not None:
                assets["calibration_map"] = str(stored_calibration.relative_to(staging_dir))
            if stored_analysis is not None:
                assets["analysis_manifest"] = str(stored_analysis.relative_to(staging_dir))
            if stored_knee is not None:
                assets["knee_manifest"] = str(stored_knee.relative_to(staging_dir))
            metadata = {
                "format_version": PROFILE_FORMAT_VERSION,
                "id": profile_id,
                "name": clean_name,
                "updated_at": datetime.now().astimezone().isoformat(),
                "assets": assets,
                "pipeline_options": {
                    "gait_analysis_enabled": bool(gait_analysis_enabled),
                    "knee_correction_enabled": bool(knee_correction_enabled),
                },
                "deeplabcut_models": [
                    {"region": region, "path": str(path.relative_to(staging_dir))}
                    for (region, path) in stored_models.items()
                ],
            }
            (staging_dir / "profile.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if target_dir.exists():
                target_dir.rename(backup_dir)
            try:
                staging_dir.rename(target_dir)
            except Exception:
                if backup_dir.exists() and (not target_dir.exists()):
                    backup_dir.rename(target_dir)
                raise
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise
        return self.load(profile_id)

    def delete(self, profile_id: str) -> None:
        profile_dir = self._profile_dir(profile_id)
        if not profile_dir.exists():
            raise FileNotFoundError(f"Profile not found: {profile_id}")
        shutil.rmtree(profile_dir)

    def _profile_dir(self, profile_id: str) -> Path:
        if not profile_id or any(character not in "0123456789abcdef" for character in profile_id.lower()):
            raise ValueError("Invalid profile identifier.")
        profile_dir = (self.root / profile_id).resolve()
        if profile_dir.parent != self.root:
            raise ValueError("Invalid profile identifier.")
        return profile_dir
