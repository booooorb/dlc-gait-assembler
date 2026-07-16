from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
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


PROFILE_FORMAT_VERSION = 5


def regions_from_processing_manifest(path: str | Path) -> tuple[str, ...]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        crop_regions = data["operations"]["crop_regions"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a valid video settings or processing manifest.") from exc

    if not isinstance(crop_regions, list):
        raise ValueError("The video manifest has an invalid region list.")
    if not crop_regions:
        return ("Full frame",)

    regions: list[str] = []
    for index, item in enumerate(crop_regions, start=1):
        if not isinstance(item, dict):
            raise ValueError("The video manifest has an invalid region entry.")
        name = str(item.get("name", "")).strip() or f"Region {index}"
        if name in regions:
            raise ValueError(f'The video manifest contains duplicate region name "{name}".')
        regions.append(name)
    return tuple(regions)


@dataclass(frozen=True)
class AutomatedPipelineProfile:
    id: str
    name: str
    processing_manifest: Path
    calibration_map: Path | None
    deeplabcut_models: dict[str, Path]
    analysis_manifest: Path | None = None
    knee_manifest: Path | None = None
    gait_analysis_enabled: bool = True
    knee_correction_enabled: bool = False
    updated_at: str = ""


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
        processing_manifest: str | Path,
        calibration_map: str | Path | None,
        deeplabcut_models: dict[str, str | Path],
        profile_id: str | None = None,
        analysis_manifest: str | Path | None = None,
        knee_manifest: str | Path | None = None,
        gait_analysis_enabled: bool = True,
        knee_correction_enabled: bool | None = None,
    ) -> AutomatedPipelineProfile:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Enter a profile name.")

        manifest_source = Path(processing_manifest).expanduser().resolve()
        calibration_source = (
            Path(calibration_map).expanduser().resolve()
            if calibration_map is not None
            else None
        )
        analysis_source = (
            Path(analysis_manifest).expanduser().resolve()
            if analysis_manifest is not None
            else None
        )
        knee_source = (
            Path(knee_manifest).expanduser().resolve()
            if knee_manifest is not None
            else None
        )
        if knee_correction_enabled is None:
            knee_correction_enabled = knee_source is not None
        if gait_analysis_enabled and analysis_source is None:
            raise ValueError("Gait analysis is enabled but no gait analysis manifest was selected.")
        if gait_analysis_enabled and calibration_source is None:
            raise ValueError("Gait analysis is enabled but no calibration map was selected.")
        if knee_correction_enabled and knee_source is None:
            raise ValueError("Knee correction is enabled but no knee analysis manifest was selected.")
        if not gait_analysis_enabled:
            calibration_source = None
            analysis_source = None
        if not knee_correction_enabled:
            knee_source = None
        if analysis_source is not None:
            read_analysis_manifest(analysis_source)
        if knee_source is not None:
            read_knee_analysis_manifest(knee_source)
        regions = regions_from_processing_manifest(manifest_source)
        if set(deeplabcut_models) != set(regions):
            raise ValueError("Choose exactly one DeepLabCut model for every region in the manifest.")
        model_sources = {
            region: Path(deeplabcut_models[region]).expanduser().resolve() for region in regions
        }
        source_paths = (
            manifest_source,
            *((calibration_source,) if calibration_source is not None else ()),
            *model_sources.values(),
            *((analysis_source,) if analysis_source is not None else ()),
            *((knee_source,) if knee_source is not None else ()),
        )
        missing_paths = [path for path in source_paths if not path.exists()]
        if missing_paths:
            raise FileNotFoundError(f"The selected file or folder no longer exists: {missing_paths[0]}")

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
            stored_manifest = self._copy_asset(manifest_source, staging_dir / "processing_manifest")
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

            assets = {
                "processing_manifest": str(stored_manifest.relative_to(staging_dir)),
            }
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
        manifest = self._stored_path(profile_dir, data["assets"]["processing_manifest"])
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
            not manifest.exists()
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
