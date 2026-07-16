from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.project_paths import ManualPipelineOutputFolders


_ANALYZED_FILE_EXTENSIONS = {".csv", ".h5", ".hdf5", ".pickle", ".pkl"}


@dataclass(frozen=True)
class OrganizedManualOutputs:
    analyzed_files: tuple[Path, ...]
    labeled_videos: tuple[Path, ...]


def organize_manual_deeplabcut_outputs(
    folders: ManualPipelineOutputFolders,
) -> OrganizedManualOutputs:
    """Move DLC artifacts out of processed-video folders into stable result folders."""
    analyzed_files: list[Path] = []
    labeled_videos: list[Path] = []
    scan_roots = (folders.processed_videos, folders.analyzed_videos)
    candidates = [
        (path, scan_root)
        for scan_root in scan_roots
        for path in scan_root.rglob("*")
        if path.is_file()
    ]
    for path, scan_root in candidates:
        suffix = path.suffix.casefold()
        stem = path.stem.casefold()
        relative_path = path.relative_to(scan_root)
        if suffix in VIDEO_EXTENSIONS and ("labeled" in stem or "labelled" in stem):
            destination = folders.labeled_videos / relative_path
            moved = _move_if_available(path, destination)
            if moved is not None:
                labeled_videos.append(moved)
            continue
        if suffix in _ANALYZED_FILE_EXTENSIONS and "dlc" in stem:
            destination = folders.analyzed_videos / relative_path
            moved = _move_if_available(path, destination)
            if moved is not None:
                analyzed_files.append(moved)

    return OrganizedManualOutputs(
        analyzed_files=tuple(analyzed_files),
        labeled_videos=tuple(labeled_videos),
    )


def _move_if_available(source: Path, destination: Path) -> Path | None:
    if source.resolve() == destination.resolve():
        return None
    if destination.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(str(source), str(destination))).resolve()
