from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
from pathlib import Path

from dlc_gait_assembly.services.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.services.domain.regions import CropRegion, NormalizedRect
from dlc_gait_assembly.services.domain.trimming import TrimRange
from dlc_gait_assembly.services.knee_correction import KneeCorrectionSettings
from dlc_gait_assembly.services.pipeline.alma import AlmaSettings
from dlc_gait_assembly.services.video_processing import ProcessingOptions


ANALYSIS_MANIFEST_TYPE = "dlc-gait-assembler.gait-analysis"
VIDEO_SETTINGS_MANIFEST_TYPE = "dlc-gait-assembler.video-settings"
KNEE_ANALYSIS_MANIFEST_TYPE = "dlc-gait-assembler.knee-analysis"
ANALYSIS_MANIFEST_FORMAT_VERSION = 1
VIDEO_SETTINGS_MANIFEST_FORMAT_VERSION = 1
KNEE_ANALYSIS_MANIFEST_FORMAT_VERSION = 1
_REQUIRED_SETTINGS = {"analysis_type", "frame_rate", "calibration_method"}
_REQUIRED_KNEE_SETTINGS = {
    "hip_knee_length_cm",
    "knee_ankle_length_cm",
    "pixels_per_cm",
    "likelihood_threshold",
}


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


def video_settings_manifest_data(
    options: ProcessingOptions,
    trim_ranges_by_video: dict[str, tuple[TrimRange, ...]] | None = None,
) -> dict:
    """Build a portable record of Video tool settings without source videos."""
    crop_regions = options.effective_crop_regions()
    invert_regions = options.effective_invert_rects()
    trim_ranges_by_video = trim_ranges_by_video or {}
    return {
        "manifest_type": VIDEO_SETTINGS_MANIFEST_TYPE,
        "format_version": VIDEO_SETTINGS_MANIFEST_FORMAT_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "format": {
            "container": "mp4",
            "video_codec": "H.264",
            "crf": options.crf,
            "preset": options.preset,
        },
        "operations": {
            "crop": _rect_to_dict(crop_regions[0].rect) if crop_regions else None,
            "crop_regions": [_crop_region_to_dict(region) for region in crop_regions],
            "invert_regions": [_rect_to_dict(rect) for rect in invert_regions]
            if options.invert_enabled or invert_regions
            else [],
            "enhancements": _enhancements_to_dict(options.enhancements),
            "trim": "per-video",
            "trim_ranges_by_video": {
                str(key): [_trim_to_dict(trim) for trim in trims]
                for key, trims in sorted(trim_ranges_by_video.items())
            },
        },
    }


def write_video_settings_manifest(
    path: str | Path,
    options: ProcessingOptions,
    trim_ranges_by_video: dict[str, tuple[TrimRange, ...]] | None = None,
) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            video_settings_manifest_data(options, trim_ranges_by_video),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def read_video_settings_manifest(path: str | Path) -> dict:
    manifest_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a valid video settings manifest.") from exc

    if not isinstance(data, dict):
        raise ValueError("This is not a valid video settings manifest.")
    if data.get("manifest_type") != VIDEO_SETTINGS_MANIFEST_TYPE:
        raise ValueError("This JSON file is not a video settings manifest.")
    if data.get("format_version") != VIDEO_SETTINGS_MANIFEST_FORMAT_VERSION:
        raise ValueError("This video settings manifest version is not supported.")
    operations = data.get("operations")
    if not isinstance(operations, dict):
        raise ValueError("The video settings manifest is missing operation settings.")
    if not isinstance(operations.get("crop_regions", []), list):
        raise ValueError("The video settings manifest has an invalid crop-region list.")
    if not isinstance(operations.get("invert_regions", []), list):
        raise ValueError("The video settings manifest has an invalid invert-region list.")
    return data


def video_settings_from_manifest(path: str | Path) -> tuple[ProcessingOptions, dict[str, tuple[TrimRange, ...]]]:
    try:
        data = read_video_settings_manifest(path)
    except ValueError as original_exc:
        manifest_path = Path(path).expanduser().resolve()
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise original_exc
        if not isinstance(data, dict) or not isinstance(data.get("operations"), dict):
            raise original_exc
    operations = data["operations"]
    format_settings = data.get("format", {})
    if not isinstance(format_settings, dict):
        format_settings = {}
    crop_regions = tuple(
        _crop_region_from_dict(item, index)
        for index, item in enumerate(operations.get("crop_regions", []), start=1)
    )
    invert_regions = tuple(
        _rect_from_dict(item)
        for item in operations.get("invert_regions", [])
        if isinstance(item, dict)
    )
    enhancements = _enhancements_from_dict(operations.get("enhancements", {}))
    trims = _trim_ranges_by_video_from_dict(operations.get("trim_ranges_by_video", {}))
    if not trims:
        trims = _trim_ranges_by_video_from_files(data.get("files", []))
    options = ProcessingOptions(
        crop_enabled=bool(crop_regions),
        crop_regions=crop_regions,
        invert_enabled=bool(invert_regions),
        invert_rects=invert_regions,
        enhancements=enhancements,
        crf=int(format_settings.get("crf", 18) or 18),
        preset=str(format_settings.get("preset", "slow") or "slow"),
    )
    return options, trims


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


def _rect_to_dict(rect: NormalizedRect | None) -> dict | None:
    if rect is None:
        return None
    rect = rect.clamped()
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _rect_from_dict(data: dict) -> NormalizedRect:
    try:
        return NormalizedRect(
            float(data["x"]),
            float(data["y"]),
            float(data["width"]),
            float(data["height"]),
        ).clamped()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("The video settings manifest has an invalid rectangle.") from exc


def _crop_region_to_dict(region: CropRegion) -> dict:
    return {
        "name": region.name,
        "rect": _rect_to_dict(region.rect),
        "flip_horizontal": region.flip_horizontal,
        "flip_vertical": region.flip_vertical,
        "flip_horizontal_video_paths": sorted(region.flip_horizontal_video_paths)
        if region.flip_horizontal_video_paths is not None
        else None,
    }


def _crop_region_from_dict(data: dict, index: int) -> CropRegion:
    if not isinstance(data, dict):
        raise ValueError("The video settings manifest has an invalid crop-region entry.")
    paths = data.get("flip_horizontal_video_paths")
    if paths is not None:
        if not isinstance(paths, list):
            raise ValueError("The video settings manifest has an invalid region flip list.")
        paths = frozenset(str(path) for path in paths)
    name = str(data.get("name", "")).strip() or f"Region {index}"
    return CropRegion(
        name,
        _rect_from_dict(data.get("rect") or {}),
        flip_horizontal=bool(data.get("flip_horizontal", False)),
        flip_vertical=bool(data.get("flip_vertical", False)),
        flip_horizontal_video_paths=paths,
    )


def _trim_to_dict(trim: TrimRange) -> dict:
    return {"start_ms": int(trim.start_ms), "end_ms": int(trim.end_ms)}


def _trim_from_dict(data: dict) -> TrimRange:
    try:
        return TrimRange(int(data["start_ms"]), int(data["end_ms"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("The video settings manifest has an invalid trim range.") from exc


def _trim_ranges_by_video_from_dict(data: object) -> dict[str, tuple[TrimRange, ...]]:
    if data in (None, {}):
        return {}
    if not isinstance(data, dict):
        raise ValueError("The video settings manifest has an invalid trim map.")
    trims_by_video: dict[str, tuple[TrimRange, ...]] = {}
    for key, raw_trims in data.items():
        if not isinstance(raw_trims, list):
            raise ValueError("The video settings manifest has an invalid trim list.")
        trims = tuple(trim for trim in (_trim_from_dict(item) for item in raw_trims) if trim.is_usable())
        if trims:
            trims_by_video[str(key)] = trims
    return trims_by_video


def _trim_ranges_by_video_from_files(data: object) -> dict[str, tuple[TrimRange, ...]]:
    if not isinstance(data, list):
        return {}
    trims_by_video: dict[str, tuple[TrimRange, ...]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        input_path = item.get("input")
        if not input_path:
            continue
        raw_trims = item.get("trim_ranges", [])
        if not isinstance(raw_trims, list):
            continue
        trims = tuple(trim for trim in (_trim_from_dict(trim) for trim in raw_trims) if trim.is_usable())
        if not trims:
            continue
        path = Path(str(input_path))
        trims_by_video[str(path)] = trims
        trims_by_video.setdefault(path.name, trims)
    return trims_by_video


def _enhancements_to_dict(settings: EnhancementSettings) -> dict:
    values = asdict(settings)
    values["enabled"] = settings.is_enabled()
    return values


def _enhancements_from_dict(data: object) -> EnhancementSettings:
    if data in (None, {}):
        return EnhancementSettings()
    if not isinstance(data, dict):
        raise ValueError("The video settings manifest has invalid enhancement settings.")
    field_names = {field.name for field in fields(EnhancementSettings)}
    values = {}
    for name in field_names:
        if name in data:
            try:
                values[name] = float(data[name])
            except (TypeError, ValueError) as exc:
                raise ValueError("The video settings manifest has invalid enhancement settings.") from exc
    return EnhancementSettings(**values)
