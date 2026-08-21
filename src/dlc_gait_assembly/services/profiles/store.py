from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dlc_gait_assembly.services.analysis_manifests import (
    read_analysis_manifest,
    read_knee_analysis_manifest,
)
from dlc_gait_assembly.services.pipeline.deeplabcut import (
    DLC_MODEL_FOLDER_NAMES,
    DLC_TRAINING_DATASET_FOLDER_NAME,
    validate_deeplabcut_project,
)
from dlc_gait_assembly.services.profiles.models import (
    AutomatedPipelineProfile,
    ProfileDraft,
)
from dlc_gait_assembly.services.profiles.validation import (
    regions_from_processing_manifest,
    validate_profile_draft,
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
                profiles.append(self._load_metadata(metadata_path))
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(profiles, key=lambda profile: profile.name.casefold())

    def load(self, profile_id: str) -> AutomatedPipelineProfile:
        return self._load_metadata(self._profile_dir(profile_id) / "profile.json")

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
            deeplabcut_models={region: Path(path) for region, path in deeplabcut_models.items()},
            analysis_manifest=Path(analysis_manifest) if analysis_manifest is not None else None,
            knee_manifest=Path(knee_manifest) if knee_manifest is not None else None,
            gait_analysis_enabled=bool(gait_analysis_enabled),
            knee_correction_enabled=(
                knee_manifest is not None if knee_correction_enabled is None else bool(knee_correction_enabled)
            ),
        )
        draft = self._normalize_incomplete_draft(draft) if allow_incomplete else validate_profile_draft(draft)
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
                self._copy_asset(manifest_source, staging_dir / "processing_manifest")
                if manifest_source is not None
                else None
            )
            stored_calibration = (
                self._copy_asset(calibration_source, staging_dir / "calibration_map")
                if calibration_source is not None
                else None
            )
            stored_analysis = (
                self._copy_asset(analysis_source, staging_dir / "analysis_manifest")
                if analysis_source is not None
                else None
            )
            stored_knee = (
                self._copy_asset(knee_source, staging_dir / "knee_manifest")
                if knee_source is not None
                else None
            )
            stored_models: dict[str, Path] = {}
            for index, (region, source) in enumerate(model_sources.items(), start=1):
                stored_models[region] = self._copy_deeplabcut_project(
                    source,
                    staging_dir / "deeplabcut_models" / f"{index:02d}",
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
                    for region, path in stored_models.items()
                ],
            }
            (staging_dir / "profile.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            if target_dir.exists():
                target_dir.rename(backup_dir)
            try:
                staging_dir.rename(target_dir)
            except Exception:
                if backup_dir.exists() and not target_dir.exists():
                    backup_dir.rename(target_dir)
                raise
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise

        return self.load(profile_id)

    def _normalize_incomplete_draft(self, draft: ProfileDraft) -> ProfileDraft:
        clean_name = draft.name.strip()
        if not clean_name:
            raise ValueError("Enter a profile name.")
        manifest = draft.processing_manifest.expanduser().resolve() if draft.processing_manifest else None
        calibration = draft.calibration_map.expanduser().resolve() if draft.calibration_map else None
        analysis = draft.analysis_manifest.expanduser().resolve() if draft.analysis_manifest else None
        knee = draft.knee_manifest.expanduser().resolve() if draft.knee_manifest else None
        models = {region: path.expanduser().resolve() for region, path in draft.deeplabcut_models.items()}
        sources = tuple(path for path in (manifest, calibration, analysis, knee, *models.values()) if path is not None)
        missing = [path for path in sources if not path.exists()]
        if missing:
            raise FileNotFoundError(f"The selected file or folder no longer exists: {missing[0]}")
        if manifest is not None:
            regions = regions_from_processing_manifest(manifest)
            if not set(models).issubset(regions):
                raise ValueError("A DeepLabCut model does not match a region in the video manifest.")
        elif models:
            raise ValueError("A video settings manifest is required before DeepLabCut models can be assigned.")
        if analysis is not None:
            read_analysis_manifest(analysis)
        if knee is not None:
            read_knee_analysis_manifest(knee)
        return ProfileDraft(
            name=clean_name,
            processing_manifest=manifest,
            calibration_map=calibration,
            deeplabcut_models=models,
            analysis_manifest=analysis,
            knee_manifest=knee,
            gait_analysis_enabled=bool(draft.gait_analysis_enabled),
            knee_correction_enabled=bool(draft.knee_correction_enabled),
        )

    def delete(self, profile_id: str) -> None:
        profile_dir = self._profile_dir(profile_id)
        if not profile_dir.exists():
            raise FileNotFoundError(f"Profile not found: {profile_id}")
        shutil.rmtree(profile_dir)

    @staticmethod
    def _copy_asset(source: Path, asset_dir: Path) -> Path:
        asset_dir.mkdir(parents=True)
        destination = asset_dir / source.name
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return destination

    @staticmethod
    def _copy_deeplabcut_project(source: Path, destination: Path) -> Path:
        config_path = validate_deeplabcut_project(source)
        project_root = config_path.parent
        destination.mkdir(parents=True)
        shutil.copy2(config_path, destination / "config.yaml")
        for folder_name in DLC_MODEL_FOLDER_NAMES:
            model_folder = project_root / folder_name
            if model_folder.is_dir():
                shutil.copytree(model_folder, destination / folder_name)
        source_training_folder = project_root / DLC_TRAINING_DATASET_FOLDER_NAME
        destination_training_folder = destination / DLC_TRAINING_DATASET_FOLDER_NAME
        for pattern in ("metadata.yaml", "Documentation_data-*.pickle"):
            for source_metadata in source_training_folder.rglob(pattern):
                relative_path = source_metadata.relative_to(source_training_folder)
                destination_metadata = destination_training_folder / relative_path
                destination_metadata.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_metadata, destination_metadata)
        return destination

    def _profile_dir(self, profile_id: str) -> Path:
        if not profile_id or any(character not in "0123456789abcdef" for character in profile_id.lower()):
            raise ValueError("Invalid profile identifier.")
        profile_dir = (self.root / profile_id).resolve()
        if profile_dir.parent != self.root:
            raise ValueError("Invalid profile identifier.")
        return profile_dir

    def _load_metadata(self, metadata_path: Path) -> AutomatedPipelineProfile:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        format_version = data.get("format_version")
        if format_version not in (1, 2, 3, 4, PROFILE_FORMAT_VERSION):
            raise ValueError("Unsupported automated profile format.")
        profile_dir = metadata_path.parent.resolve()
        manifest_relative = data["assets"].get("processing_manifest")
        manifest = self._stored_path(profile_dir, manifest_relative) if manifest_relative else None
        calibration_relative = data["assets"].get("calibration_map")
        calibration = (
            self._stored_path(profile_dir, calibration_relative)
            if calibration_relative
            else None
        )
        analysis_relative = data["assets"].get("analysis_manifest")
        analysis_manifest = (
            self._stored_path(profile_dir, analysis_relative) if analysis_relative else None
        )
        knee_relative = data["assets"].get("knee_manifest")
        knee_manifest = self._stored_path(profile_dir, knee_relative) if knee_relative else None
        if format_version == 1:
            legacy_model = self._stored_path(profile_dir, data["assets"]["deeplabcut_model"])
            models = {region: legacy_model for region in regions_from_processing_manifest(manifest)}
        else:
            models = {
                str(item["region"]): self._stored_path(profile_dir, item["path"])
                for item in data["deeplabcut_models"]
            }
        if (
            (manifest is not None and not manifest.exists())
            or (calibration is not None and not calibration.exists())
            or (analysis_manifest is not None and not analysis_manifest.exists())
            or (knee_manifest is not None and not knee_manifest.exists())
            or not all(path.exists() for path in models.values())
        ):
            raise FileNotFoundError("A stored profile asset is missing.")
        pipeline_options = data.get("pipeline_options", {})
        if not isinstance(pipeline_options, dict):
            pipeline_options = {}
        gait_analysis_enabled = bool(
            pipeline_options.get("gait_analysis_enabled", analysis_manifest is not None)
        )
        knee_correction_enabled = bool(
            pipeline_options.get("knee_correction_enabled", knee_manifest is not None)
        )
        return AutomatedPipelineProfile(
            id=str(data["id"]),
            name=str(data["name"]),
            processing_manifest=manifest,
            calibration_map=calibration,
            deeplabcut_models=models,
            analysis_manifest=analysis_manifest,
            knee_manifest=knee_manifest,
            gait_analysis_enabled=gait_analysis_enabled,
            knee_correction_enabled=knee_correction_enabled,
            updated_at=str(data.get("updated_at", "")),
        )

    @staticmethod
    def _stored_path(profile_dir: Path, relative_path: str) -> Path:
        path = (profile_dir / relative_path).resolve()
        if profile_dir not in path.parents:
            raise ValueError("A profile asset points outside its profile folder.")
        return path
