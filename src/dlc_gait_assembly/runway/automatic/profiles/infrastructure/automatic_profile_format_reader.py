"""Read saved workflow profiles and validate owned asset references."""

from __future__ import annotations

import json
from pathlib import Path

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_asset_store import (
    regions_from_processing_manifest,
)

PROFILE_FORMAT_VERSION = 6


def read_profile_metadata(metadata_path: Path) -> AutomatedPipelineProfile:
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    format_version = data.get("format_version")
    if format_version not in (1, 2, 3, 4, 5, PROFILE_FORMAT_VERSION):
        raise ValueError("Unsupported automated profile format.")
    profile_dir = metadata_path.parent.resolve()
    manifest_relative = data["assets"].get("processing_manifest")
    manifest = resolve_stored_profile_path(profile_dir, manifest_relative) if manifest_relative else None
    calibration_relative = data["assets"].get("calibration_map")
    calibration = resolve_stored_profile_path(profile_dir, calibration_relative) if calibration_relative else None
    analysis_relative = data["assets"].get("analysis_manifest")
    analysis_manifest = resolve_stored_profile_path(profile_dir, analysis_relative) if analysis_relative else None
    knee_relative = data["assets"].get("knee_manifest")
    knee_manifest = resolve_stored_profile_path(profile_dir, knee_relative) if knee_relative else None
    if format_version == 1:
        legacy_model = resolve_stored_profile_path(profile_dir, data["assets"]["deeplabcut_model"])
        models = {region: legacy_model for region in regions_from_processing_manifest(manifest)}
    else:
        models = {
            str(item["region"]): resolve_stored_profile_path(profile_dir, item["path"])
            for item in data["deeplabcut_models"]
        }
    if (
        manifest is not None
        and (not manifest.exists())
        or (calibration is not None and (not calibration.exists()))
        or (analysis_manifest is not None and (not analysis_manifest.exists()))
        or (knee_manifest is not None and (not knee_manifest.exists()))
        or (not all(path.exists() for path in models.values()))
    ):
        raise FileNotFoundError("A stored profile asset is missing.")
    pipeline_options = data.get("pipeline_options", {})
    if not isinstance(pipeline_options, dict):
        pipeline_options = {}
    gait_analysis_enabled = bool(pipeline_options.get("gait_analysis_enabled", analysis_manifest is not None))
    knee_correction_enabled = bool(pipeline_options.get("knee_correction_enabled", knee_manifest is not None))
    workspace_state = validate_workspace_state(data.get("workspace_state", {}))
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
        workspace_state=workspace_state,
    )


def validate_workspace_state(workspace_state):
    if not isinstance(workspace_state, dict):
        raise ValueError("Invalid workflow workspace settings.")
    if workspace_state and workspace_state.get("version") != 1:
        raise ValueError("Unsupported workflow workspace format.")
    pages = workspace_state.get("pages", {})
    if not isinstance(pages, dict) or any(
        not isinstance(page, dict) or any(not isinstance(page.get(key, {}), dict) for key in ("controls", "data", "inputs"))
        for page in pages.values()
    ):
        raise ValueError("Invalid workflow page settings.")
    videos = workspace_state.get("automation_videos", [])
    if not isinstance(videos, list) or any(not isinstance(path, str) for path in videos):
        raise ValueError("Invalid workflow video selections.")
    return workspace_state


def resolve_stored_profile_path(profile_dir: Path, relative_path: str) -> Path:
    path = (profile_dir / relative_path).resolve()
    if profile_dir not in path.parents:
        raise ValueError("A profile asset points outside its profile folder.")
    return path
