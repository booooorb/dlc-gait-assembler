"""Read and write gait settings manifests and inspect imported calibration-map settings."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
    resolve_calibration_settings,
)
from dlc_gait_assembly.shared.infrastructure.calibration_map_codec import pixels_per_cm_from_calibration_map

ANALYSIS_MANIFEST_TYPE = "dlc-gait-assembler.gait-analysis"
ANALYSIS_MANIFEST_FORMAT_VERSION = 2
REQUIRED_SETTINGS = {"analysis_type", "frame_rate", "calibration_method"}


def analysis_manifest_data(settings: AlmaSettings) -> dict:
    """Build a portable record of the settings selected in Manual Gait Analysis."""
    values = asdict(resolve_calibration_settings(settings))
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
    if data.get("format_version") not in {1, ANALYSIS_MANIFEST_FORMAT_VERSION}:
        raise ValueError("This gait analysis manifest version is not supported.")
    settings = data.get("analysis_settings")
    if not isinstance(settings, dict) or not REQUIRED_SETTINGS.issubset(settings):
        raise ValueError("The gait analysis manifest is missing required settings.")
    return data


def alma_settings_from_manifest(path: str | Path, calibration_map_path: str | Path | None = None) -> AlmaSettings:
    """Restore the saved mode; a profile map replaces only a shared-map calibration."""
    data = read_analysis_manifest(path)
    raw_settings = data["analysis_settings"]
    field_names = {field.name for field in fields(AlmaSettings)}
    values = {
        key: value for (key, value) in raw_settings.items() if key in field_names and key != "calibration_map_path"
    }
    method = values.get("calibration_method", "reference")
    if data["format_version"] == 1:
        # Older manifests had overlapping modes and treadmill calibration was implicit.
        if values.get("view_calibration"):
            method = "per_view"
        elif method == "reference" and values.get("analysis_type") == "Treadmill":
            method = "treadmill"
        elif method == "manual" and values.get("pixels_per_cm") is None:
            method = "map"
    values["calibration_method"] = method
    values["calibration_map_path"] = None
    if method == "map":
        if calibration_map_path is not None:
            values.update(pixels_per_cm=None, calibration_map_path=Path(calibration_map_path).expanduser().resolve())
        elif values.get("pixels_per_cm") is None and raw_settings.get("calibration_map_filename"):
            values["calibration_map_path"] = Path(path).resolve().parent / raw_settings["calibration_map_filename"]
    for node in (values.get("view_calibration") or {}).values():
        if isinstance(node, dict) and node.get("map_path") and not Path(node["map_path"]).is_absolute():
            node["map_path"] = str((Path(path).resolve().parent / node["map_path"]).resolve())
    return AlmaSettings(**values)


class GaitSettingsManifestStore:
    read = staticmethod(read_analysis_manifest)
    write = staticmethod(write_analysis_manifest)
    calibration_scale = staticmethod(pixels_per_cm_from_calibration_map)
    load_settings = staticmethod(alma_settings_from_manifest)
    resolve_calibration = staticmethod(resolve_calibration_settings)

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
