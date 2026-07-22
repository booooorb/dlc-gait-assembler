"""Serialization for knee-correction settings."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.services.knee_correction import KneeCorrectionSettings

KNEE_ANALYSIS_MANIFEST_TYPE = "dlc-gait-assembler.knee-analysis"
KNEE_ANALYSIS_MANIFEST_FORMAT_VERSION = 1
_REQUIRED_KNEE_SETTINGS = {
    "hip_knee_length_cm",
    "knee_ankle_length_cm",
    "pixels_per_cm",
    "likelihood_threshold",
}


def knee_analysis_manifest_data(settings: KneeCorrectionSettings) -> dict:
    """Build a portable record of Knee Correction settings for automation."""

    return {
        "manifest_type": KNEE_ANALYSIS_MANIFEST_TYPE,
        "format_version": KNEE_ANALYSIS_MANIFEST_FORMAT_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "knee_settings": asdict(settings),
    }


def write_knee_analysis_manifest(path: str | Path, settings: KneeCorrectionSettings) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(knee_analysis_manifest_data(settings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def read_knee_analysis_manifest(path: str | Path) -> dict:
    manifest_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a valid knee analysis manifest.") from exc
    if not isinstance(data, dict):
        raise ValueError("This is not a valid knee analysis manifest.")
    if data.get("manifest_type") != KNEE_ANALYSIS_MANIFEST_TYPE:
        raise ValueError("This JSON file is not a knee analysis manifest.")
    if data.get("format_version") != KNEE_ANALYSIS_MANIFEST_FORMAT_VERSION:
        raise ValueError("This knee analysis manifest version is not supported.")
    settings = data.get("knee_settings")
    if not isinstance(settings, dict) or not _REQUIRED_KNEE_SETTINGS.issubset(settings):
        raise ValueError("The knee analysis manifest is missing required settings.")
    return data


def knee_settings_from_manifest(path: str | Path) -> KneeCorrectionSettings:
    data = read_knee_analysis_manifest(path)
    settings = data["knee_settings"]
    field_names = {field.name for field in fields(KneeCorrectionSettings)}
    values = {key: value for key, value in settings.items() if key in field_names}
    knee_bodyparts = values.get("knee_bodyparts")
    if knee_bodyparts is not None:
        values["knee_bodyparts"] = tuple(str(item) for item in knee_bodyparts)
    return KneeCorrectionSettings(**values)
