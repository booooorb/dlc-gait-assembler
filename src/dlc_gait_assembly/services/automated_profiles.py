from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
from uuid import uuid4


PROFILE_FORMAT_VERSION = 2


def regions_from_processing_manifest(path: str | Path) -> tuple[str, ...]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        crop_regions = data["operations"]["crop_regions"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a valid video processing manifest.") from exc

    if not isinstance(crop_regions, list):
        raise ValueError("The video processing manifest has an invalid region list.")
    if not crop_regions:
        return ("Full frame",)

    regions: list[str] = []
    for index, item in enumerate(crop_regions, start=1):
        if not isinstance(item, dict):
            raise ValueError("The video processing manifest has an invalid region entry.")
        name = str(item.get("name", "")).strip() or f"Region {index}"
        if name in regions:
            raise ValueError(f'The video processing manifest contains duplicate region name "{name}".')
        regions.append(name)
    return tuple(regions)


@dataclass(frozen=True)
class AutomatedPipelineProfile:
    id: str
    name: str
    processing_manifest: Path
    calibration_map: Path
    deeplabcut_models: dict[str, Path]
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
        calibration_map: str | Path,
        deeplabcut_models: dict[str, str | Path],
        profile_id: str | None = None,
    ) -> AutomatedPipelineProfile:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Enter a profile name.")

        manifest_source = Path(processing_manifest).expanduser().resolve()
        calibration_source = Path(calibration_map).expanduser().resolve()
        regions = regions_from_processing_manifest(manifest_source)
        if set(deeplabcut_models) != set(regions):
            raise ValueError("Choose exactly one DeepLabCut model for every region in the manifest.")
        model_sources = {
            region: Path(deeplabcut_models[region]).expanduser().resolve() for region in regions
        }
        source_paths = (manifest_source, calibration_source, *model_sources.values())
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
            stored_calibration = self._copy_asset(calibration_source, staging_dir / "calibration_map")
            stored_models: dict[str, Path] = {}
            for index, (region, source) in enumerate(model_sources.items(), start=1):
                stored_models[region] = self._copy_asset(
                    source,
                    staging_dir / "deeplabcut_models" / f"{index:02d}",
                )

            metadata = {
                "format_version": PROFILE_FORMAT_VERSION,
                "id": profile_id,
                "name": clean_name,
                "updated_at": datetime.now().astimezone().isoformat(),
                "assets": {
                    "processing_manifest": str(stored_manifest.relative_to(staging_dir)),
                    "calibration_map": str(stored_calibration.relative_to(staging_dir)),
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
        if format_version not in (1, PROFILE_FORMAT_VERSION):
            raise ValueError("Unsupported automated profile format.")
        profile_dir = metadata_path.parent.resolve()
        manifest = self._stored_path(profile_dir, data["assets"]["processing_manifest"])
        calibration = self._stored_path(profile_dir, data["assets"]["calibration_map"])
        if format_version == 1:
            legacy_model = self._stored_path(profile_dir, data["assets"]["deeplabcut_model"])
            models = {region: legacy_model for region in regions_from_processing_manifest(manifest)}
        else:
            models = {
                str(item["region"]): self._stored_path(profile_dir, item["path"])
                for item in data["deeplabcut_models"]
            }
        if not manifest.exists() or not calibration.exists() or not all(path.exists() for path in models.values()):
            raise FileNotFoundError("A stored profile asset is missing.")
        return AutomatedPipelineProfile(
            id=str(data["id"]),
            name=str(data["name"]),
            processing_manifest=manifest,
            calibration_map=calibration,
            deeplabcut_models=models,
            updated_at=str(data.get("updated_at", "")),
        )

    @staticmethod
    def _stored_path(profile_dir: Path, relative_path: str) -> Path:
        path = (profile_dir / relative_path).resolve()
        if profile_dir not in path.parents:
            raise ValueError("A profile asset points outside its profile folder.")
        return path
