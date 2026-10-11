"""Inspect, copy, and normalize profile-owned manifests and model assets."""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import ProfileDraft
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_from_manual import (
    ManualProfileAssets,
    ManualProfileSnapshot,
)
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_validation import (
    regions_from_processing_data,
    validate_profile_draft,
)
from dlc_gait_assembly.runway.manual.calibration.infrastructure.calibration_export_writer import (
    write_calibration_conversion_export,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_project_reader import (
    DLC_MODEL_FOLDER_NAMES,
    DLC_TRAINING_DATASET_FOLDER_NAME,
    validate_deeplabcut_project,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    read_analysis_manifest,
    write_analysis_manifest,
)
from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
    read_knee_analysis_manifest,
    write_knee_analysis_manifest,
)
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    write_video_settings_manifest,
)


def regions_from_processing_manifest(path):
    return regions_from_processing_data(json.loads(Path(path).read_text(encoding="utf-8")))


def inspect_profile_draft(draft):

    def normalized(path):
        return Path(path).expanduser().resolve() if path is not None else None

    draft = replace(
        draft,
        processing_manifest=normalized(draft.processing_manifest),
        calibration_map=normalized(draft.calibration_map),
        analysis_manifest=normalized(draft.analysis_manifest),
        knee_manifest=normalized(draft.knee_manifest),
        deeplabcut_models={region: normalized(path) for (region, path) in draft.deeplabcut_models.items()},
    )
    if draft.processing_manifest is None:
        return validate_profile_draft(draft, regions=())
    regions = regions_from_processing_manifest(draft.processing_manifest)
    draft = validate_profile_draft(draft, regions=regions)
    if draft.analysis_manifest is not None:
        read_analysis_manifest(draft.analysis_manifest)
    if draft.knee_manifest is not None:
        read_knee_analysis_manifest(draft.knee_manifest)
    sources = (
        draft.processing_manifest,
        draft.calibration_map,
        draft.analysis_manifest,
        draft.knee_manifest,
        *draft.deeplabcut_models.values(),
    )
    for path in sources:
        if path is not None and (not path.exists()):
            raise FileNotFoundError(f"The selected file or folder no longer exists: {path}")
    return draft


def normalize_incomplete_profile_draft(draft: ProfileDraft) -> ProfileDraft:
    clean_name = draft.name.strip()
    if not clean_name:
        raise ValueError("Enter a profile name.")
    manifest = draft.processing_manifest.expanduser().resolve() if draft.processing_manifest else None
    calibration = draft.calibration_map.expanduser().resolve() if draft.calibration_map else None
    analysis = draft.analysis_manifest.expanduser().resolve() if draft.analysis_manifest else None
    knee = draft.knee_manifest.expanduser().resolve() if draft.knee_manifest else None
    models = {region: path.expanduser().resolve() for (region, path) in draft.deeplabcut_models.items()}
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


def copy_profile_asset(source: Path, asset_dir: Path) -> Path:
    asset_dir.mkdir(parents=True)
    destination = asset_dir / source.name
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return destination


def copy_profile_deeplabcut_project(source: Path, destination: Path) -> Path:
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


class AutomaticManualAssetWriter:
    """Serialize typed snapshots temporarily until the profile repository owns copies."""

    @contextmanager
    def materialize(self, snapshot: ManualProfileSnapshot):
        with TemporaryDirectory(prefix="dlc-gait-profile-") as temporary:
            root = Path(temporary)
            paths = {
                name: path if path is not None and path.is_file() else None
                for name in ("processing_manifest", "calibration_map", "analysis_manifest", "knee_manifest")
                for path in (getattr(snapshot, name),)
            }
            if snapshot.video is not None:
                paths["processing_manifest"] = write_video_settings_manifest(
                    root / "video_settings_manifest.json", snapshot.video.options, snapshot.video.trim_ranges_by_path
                )
            if snapshot.calibration is not None:
                paths["calibration_map"] = write_calibration_conversion_export(
                    root / "calibration", list(snapshot.calibration.sticks), snapshot.calibration.report
                )["map"]
            if snapshot.gait is not None:
                paths["analysis_manifest"] = write_analysis_manifest(root / "analysis_manifest.json", snapshot.gait)
            if snapshot.knee is not None:
                paths["knee_manifest"] = write_knee_analysis_manifest(
                    root / "knee_analysis_manifest.json", snapshot.knee
                )
            yield ManualProfileAssets(**paths)


class AutomaticProfileAssetReader:
    regions = staticmethod(regions_from_processing_manifest)
    gait_settings = staticmethod(read_analysis_manifest)
    knee_settings = staticmethod(read_knee_analysis_manifest)
