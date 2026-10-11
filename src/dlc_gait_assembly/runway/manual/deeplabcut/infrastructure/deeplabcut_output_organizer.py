"""Collect and place DeepLabCut coordinate and labeled-video artifacts in their owning folders."""

from __future__ import annotations

import shutil
from pathlib import Path

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_artifact_rules import (
    classify_deeplabcut_artifact,
    deeplabcut_region_directory,
)
from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import OrganizedManualOutputs
from dlc_gait_assembly.shared.business.workspace_path_contracts import ManualPipelineOutputFolders


def organize_manual_deeplabcut_outputs(folders: ManualPipelineOutputFolders) -> OrganizedManualOutputs:
    """Move DLC artifacts out of processed-video folders into stable result folders."""
    analyzed_files: list[Path] = []
    labeled_videos: list[Path] = []
    scan_roots = (folders.processed_videos, folders.analyzed_videos)
    candidates = [(path, scan_root) for scan_root in scan_roots for path in scan_root.rglob("*") if path.is_file()]
    for path, scan_root in candidates:
        kind = classify_deeplabcut_artifact(path)
        relative_path = path.relative_to(scan_root)
        if kind == "labeled_video":
            destination = folders.labeled_videos / relative_path
            moved = move_if_available(path, destination)
            if moved is not None:
                labeled_videos.append(moved)
            continue
        if kind == "coordinates":
            destination = folders.analyzed_videos / relative_path
            moved = move_if_available(path, destination)
            if moved is not None:
                analyzed_files.append(moved)
    return OrganizedManualOutputs(analyzed_files=tuple(analyzed_files), labeled_videos=tuple(labeled_videos))


def move_if_available(source: Path, destination: Path) -> Path | None:
    if source.resolve() == destination.resolve():
        return None
    if destination.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(str(source), str(destination))).resolve()


class DeepLabCutArtifactStore:
    """Allocate stage directories and normalize external artifact locations."""

    def resolve(self, path):
        return Path(path).expanduser().resolve()

    def analysis_folder(self, destination, region):
        folder = self.resolve(destination) / "analyzed_videos" / deeplabcut_region_directory(region)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def labeled_folder(self, destination, region):
        folder = self.resolve(destination) / "labeled_videos" / deeplabcut_region_directory(region)
        folder.mkdir(parents=True, exist_ok=True)
        return folder
