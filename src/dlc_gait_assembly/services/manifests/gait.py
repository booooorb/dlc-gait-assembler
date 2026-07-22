"""Serialization for gait-analysis settings."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.services.pipeline.alma import AlmaSettings

ANALYSIS_MANIFEST_TYPE = "dlc-gait-assembler.gait-analysis"
ANALYSIS_MANIFEST_FORMAT_VERSION = 1
_REQUIRED_SETTINGS = {"analysis_type", "frame_rate", "calibration_method"}


def analysis_manifest_data(settings: AlmaSettings) -> dict:
    """Build a portable record of the settings selected in Manual Gait Analysis."""

    values = asdict(settings)
    calibration_map_path = values.pop("calibration_map_path", None)
    values["calibration_map_filename"] = (
        Path(calibration_map_path).name if calibration_map_path is not None else None
    )
    return {
        "manifest_type": ANALYSIS_MANIFEST_TYPE,
        "format_version": ANALYSIS_MANIFEST_FORMAT_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "analysis_settings": values,
    }


def write_analysis_manifest(path: str | Path, settings: AlmaSettings) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(analysis_manifest_data(settings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def read_analysis_manifest(path: str | Path) -> dict:
    manifest_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a valid gait analysis manifest.") from exc
    if not isinstance(data, dict):
        raise ValueError("This is not a valid gait analysis manifest.")
    if data.get("manifest_type") != ANALYSIS_MANIFEST_TYPE:
        raise ValueError("This JSON file is not a gait analysis manifest.")
    if data.get("format_version") != ANALYSIS_MANIFEST_FORMAT_VERSION:
        raise ValueError("This gait analysis manifest version is not supported.")
    settings = data.get("analysis_settings")
    if not isinstance(settings, dict) or not _REQUIRED_SETTINGS.issubset(settings):
        raise ValueError("The gait analysis manifest is missing required settings.")
    return data


def alma_settings_from_manifest(
    path: str | Path,
    calibration_map_path: str | Path | None = None,
) -> AlmaSettings:
    """Rebuild ALMA settings and bind them to the selected calibration map."""

    data = read_analysis_manifest(path)
    raw_settings = data["analysis_settings"]
    field_names = {field.name for field in fields(AlmaSettings)}
    values = {
        key: value
        for key, value in raw_settings.items()
        if key in field_names and key != "calibration_map_path"
    }
    values["calibration_map_path"] = (
        Path(calibration_map_path).expanduser().resolve()
        if calibration_map_path is not None
        else None
    )
    return AlmaSettings(**values)
