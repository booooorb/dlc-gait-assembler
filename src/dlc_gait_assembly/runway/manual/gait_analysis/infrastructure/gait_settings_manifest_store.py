"""Read and write gait settings manifests and inspect imported calibration-map settings."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.shared.infrastructure.calibration_map_codec import pixels_per_cm_from_calibration_map

ANALYSIS_MANIFEST_TYPE = "dlc-gait-assembler.gait-analysis"
ANALYSIS_MANIFEST_FORMAT_VERSION = 1
REQUIRED_SETTINGS = {"analysis_type", "frame_rate", "calibration_method"}


def analysis_manifest_data(settings: AlmaSettings) -> dict:
    """Build a portable record of the settings selected in Manual Gait Analysis."""
    values = asdict(settings)
    calibration_map_path = values.pop("calibration_map_path", None)
    values["calibration_map_filename"] = Path(calibration_map_path).name if calibration_map_path is not None else None
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
        json.dumps(analysis_manifest_data(settings), indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
    if not isinstance(settings, dict) or not REQUIRED_SETTINGS.issubset(settings):
        raise ValueError("The gait analysis manifest is missing required settings.")
    return data


def alma_settings_from_manifest(path: str | Path, calibration_map_path: str | Path | None = None) -> AlmaSettings:
    """Rebuild ALMA settings and bind them to the selected calibration map."""
    data = read_analysis_manifest(path)
    raw_settings = data["analysis_settings"]
    field_names = {field.name for field in fields(AlmaSettings)}
    values = {
        key: value for (key, value) in raw_settings.items() if key in field_names and key != "calibration_map_path"
    }
    values["calibration_map_path"] = (
        Path(calibration_map_path).expanduser().resolve() if calibration_map_path is not None else None
    )
    if calibration_map_path is not None:
        # An explicitly selected replacement map overrides the manifest's shared snapshot.
        values.update(pixels_per_cm=None, calibration_method="manual")
    return AlmaSettings(**values)


class GaitSettingsManifestStore:
    read = staticmethod(read_analysis_manifest)
    write = staticmethod(write_analysis_manifest)
    calibration_scale = staticmethod(pixels_per_cm_from_calibration_map)
    load_settings = staticmethod(alma_settings_from_manifest)

    def camera_map_views(self, path):
        return read_camera_map_views(path)

    def camera_map_scales(self, path, view_index=None):
        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
            camera_map_scales,
        )

        return camera_map_scales(path, view_index)


def read_camera_map_views(path):
    from dlc_gait_assembly.shared.infrastructure.calibration_map_codec import read_calibration_map

    payload = read_calibration_map(path)
    return tuple(payload.get("conversion_factor_map", payload).get("views", {}))
