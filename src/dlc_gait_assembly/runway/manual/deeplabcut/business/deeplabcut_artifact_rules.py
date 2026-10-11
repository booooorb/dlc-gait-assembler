"""Classify coordinate tables, labeled videos, and their owning region directories."""

from pathlib import Path

from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS

ANALYZED_FILE_EXTENSIONS = {".csv", ".h5", ".hdf5", ".pickle", ".pkl"}


def classify_deeplabcut_artifact(path: Path) -> str | None:
    suffix, stem = path.suffix.casefold(), path.stem.casefold()
    if suffix in VIDEO_EXTENSIONS and ("labeled" in stem or "labelled" in stem):
        return "labeled_video"
    if suffix in ANALYZED_FILE_EXTENSIONS and "dlc" in stem:
        return "coordinates"
    return None


def deeplabcut_region_directory(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    return safe.strip("_") or "region"
