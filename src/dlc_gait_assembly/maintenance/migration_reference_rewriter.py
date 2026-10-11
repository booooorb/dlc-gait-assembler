"""Rewrite recognized internal metadata paths and report links, retaining external inputs."""

import json
from pathlib import Path
from urllib.parse import quote

_PATH_FIELDS = {
    "input",
    "output",
    "outputs",
    "source_file",
    "source_csv",
    "source_h5",
    "source_video",
    "csv",
    "h5",
    "video",
    "input_file",
    "output_file",
    "output_files",
    "output_folder",
    "path",
    "csv_file",
    "csv_path",
    "h5_path",
    "video_path",
    "video_paths",
    "csv_paths",
    "h5_paths",
    "analyzed_videos",
    "labeled_videos",
    "coordinate_csvs",
    "processed_videos",
    "stickplots",
    "gait_analysis",
    "knee_correction",
    "calibration_map",
    "calibration_map_path",
    "processing_manifest",
    "analysis_manifest",
    "knee_manifest",
    "flip_horizontal_video_paths",
    "left_csv",
    "right_csv",
    "bottom_csv",
    "project_path",
    "destfolder",
    "source",
    "destination",
}
_PATH_CONTAINERS = {"folders", "artifacts", "video_sets", "trim_ranges_by_path", "deeplabcut_models"}


def rewrite_metadata_bytes(path, original, mapping, profile_id=None):
    suffix = Path(path).suffix.lower()
    text = original.decode("utf-8")

    def remap(value):
        if value in mapping:
            return mapping[value]
        prefix = value.rstrip("/") + "/"
        matches = [(old, new) for (old, new) in mapping.items() if old.startswith(prefix)]
        if matches:
            destinations = {new[: -len(old[len(prefix) :])].rstrip("/") for (old, new) in matches}
            if len(destinations) == 1:
                return destinations.pop()
        return value

    def visit(value, field="", path_context=False):
        if isinstance(value, str):
            return remap(value) if path_context or field in _PATH_FIELDS else value
        if isinstance(value, list):
            return [visit(item, field, path_context) for item in value]
        if isinstance(value, dict):
            return {
                remap(key) if field in {"video_sets", "trim_ranges_by_path"} else key: visit(
                    item, key, path_context or field in _PATH_CONTAINERS
                )
                for (key, item) in value.items()
            }
        return value

    if suffix == ".json":
        payload = visit(json.loads(text))
        if profile_id is not None and Path(path).name == "profile.json":
            payload["id"] = profile_id
        result = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    elif suffix in {".yaml", ".yml"}:
        import yaml

        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(str(exc)) from exc
        revised = visit(payload)
        if revised == payload:
            return original
        result = yaml.safe_dump(revised, sort_keys=False, allow_unicode=True)
    elif suffix in {".md", ".html", ".htm"}:
        result = text
        for old, new in sorted(mapping.items(), key=lambda pair: len(pair[0]), reverse=True):
            result = result.replace(old, new).replace(quote(old), quote(new))
    else:
        return original
    if suffix == ".json" and json.loads(text) == json.loads(result):
        return original
    return result.encode("utf-8")
