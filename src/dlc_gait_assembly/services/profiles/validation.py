"""Pure validation and normalization for automated pipeline profiles."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from dlc_gait_assembly.services.analysis_manifests import (
    read_analysis_manifest,
    read_knee_analysis_manifest,
)
from dlc_gait_assembly.services.profiles.models import ProfileDraft


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


def validate_profile_draft(draft: ProfileDraft) -> ProfileDraft:
    """Return a normalized draft or raise a user-facing validation error."""

    clean_name = draft.name.strip()
    if not clean_name:
        raise ValueError("Enter a profile name.")

    if draft.processing_manifest is None:
        raise ValueError("Choose a video settings or processing manifest.")
    manifest = draft.processing_manifest.expanduser().resolve()
    calibration = (
        draft.calibration_map.expanduser().resolve()
        if draft.calibration_map is not None
        else None
    )
    analysis = (
        draft.analysis_manifest.expanduser().resolve()
        if draft.analysis_manifest is not None
        else None
    )
    knee = (
        draft.knee_manifest.expanduser().resolve()
        if draft.knee_manifest is not None
        else None
    )
    if draft.gait_analysis_enabled and analysis is None:
        raise ValueError("Gait analysis is enabled but no gait analysis manifest was selected.")
    if draft.gait_analysis_enabled and calibration is None:
        raise ValueError("Gait analysis is enabled but no calibration map was selected.")
    if draft.knee_correction_enabled and knee is None:
        raise ValueError("Knee correction is enabled but no knee analysis manifest was selected.")
    if not draft.gait_analysis_enabled:
        calibration = None
        analysis = None
    if not draft.knee_correction_enabled:
        knee = None
    if analysis is not None:
        read_analysis_manifest(analysis)
    if knee is not None:
        read_knee_analysis_manifest(knee)

    regions = regions_from_processing_manifest(manifest)
    models = {
        region: Path(draft.deeplabcut_models[region]).expanduser().resolve()
        for region in regions
        if region in draft.deeplabcut_models
    }
    if set(models) != set(regions) or set(draft.deeplabcut_models) != set(regions):
        raise ValueError("Choose exactly one DeepLabCut model for every region in the manifest.")

    sources = (
        manifest,
        *((calibration,) if calibration is not None else ()),
        *models.values(),
        *((analysis,) if analysis is not None else ()),
        *((knee,) if knee is not None else ()),
    )
    missing = [path for path in sources if not path.exists()]
    if missing:
        raise FileNotFoundError(f"The selected file or folder no longer exists: {missing[0]}")

    return replace(
        draft,
        name=clean_name,
        processing_manifest=manifest,
        calibration_map=calibration,
        deeplabcut_models=models,
        analysis_manifest=analysis,
        knee_manifest=knee,
    )
