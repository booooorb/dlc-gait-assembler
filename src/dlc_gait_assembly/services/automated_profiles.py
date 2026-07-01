from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
from uuid import uuid4


PROFILE_FORMAT_VERSION = 1
ASSET_KEYS = ("calibration_map", "deeplabcut_model", "processing_manifest")


@dataclass(frozen=True)
class AutomatedPipelineProfile:
    id: str
    name: str
    calibration_map: Path
    deeplabcut_model: Path
    processing_manifest: Path
    updated_at: str = ""

    def asset_paths(self) -> dict[str, Path]:
        return {
            "calibration_map": self.calibration_map,
            "deeplabcut_model": self.deeplabcut_model,
            "processing_manifest": self.processing_manifest,
        }


class AutomatedProfileStore:
    """Owns the files selected for automated-pipeline profiles.

    This store intentionally does not interpret the assets or run any pipeline
    work. It only copies them into a durable, app-managed profile folder.
    """

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
                # A partially written or manually edited folder should not make
                # the entire profile picker unusable.
                continue
        return sorted(profiles, key=lambda profile: profile.name.casefold())

    def load(self, profile_id: str) -> AutomatedPipelineProfile:
        profile_dir = self._profile_dir(profile_id)
        return self._load_metadata(profile_dir / "profile.json")

    def save(
        self,
        name: str,
        assets: dict[str, str | Path],
        profile_id: str | None = None,
    ) -> AutomatedPipelineProfile:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Enter a profile name.")

        missing_keys = [key for key in ASSET_KEYS if key not in assets]
        if missing_keys:
            raise ValueError(f"Missing profile asset: {missing_keys[0].replace('_', ' ')}.")

        source_paths = {key: Path(assets[key]).expanduser().resolve() for key in ASSET_KEYS}
        missing_paths = [path for path in source_paths.values() if not path.exists()]
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
            stored_paths: dict[str, Path] = {}
            for key, source in source_paths.items():
                asset_dir = staging_dir / key
                asset_dir.mkdir()
                destination = asset_dir / source.name
                if source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
                stored_paths[key] = destination

            updated_at = datetime.now().astimezone().isoformat()
            metadata = {
                "format_version": PROFILE_FORMAT_VERSION,
                "id": profile_id,
                "name": clean_name,
                "updated_at": updated_at,
                "assets": {
                    key: str(path.relative_to(staging_dir)) for key, path in stored_paths.items()
                },
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

    def _profile_dir(self, profile_id: str) -> Path:
        if not profile_id or any(character not in "0123456789abcdef" for character in profile_id.lower()):
            raise ValueError("Invalid profile identifier.")
        profile_dir = (self.root / profile_id).resolve()
        if profile_dir.parent != self.root:
            raise ValueError("Invalid profile identifier.")
        return profile_dir

    def _load_metadata(self, metadata_path: Path) -> AutomatedPipelineProfile:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        if data.get("format_version") != PROFILE_FORMAT_VERSION:
            raise ValueError("Unsupported automated profile format.")
        profile_dir = metadata_path.parent.resolve()
        asset_paths = {
            key: (profile_dir / data["assets"][key]).resolve()
            for key in ASSET_KEYS
        }
        if any(profile_dir not in path.parents for path in asset_paths.values()):
            raise ValueError("A profile asset points outside its profile folder.")
        if not all(path.exists() for path in asset_paths.values()):
            raise FileNotFoundError("A stored profile asset is missing.")
        return AutomatedPipelineProfile(
            id=str(data["id"]),
            name=str(data["name"]),
            calibration_map=asset_paths["calibration_map"],
            deeplabcut_model=asset_paths["deeplabcut_model"],
            processing_manifest=asset_paths["processing_manifest"],
            updated_at=str(data.get("updated_at", "")),
        )
