"""Resolve the configured, source-checkout, or home workspace independently of the current directory."""

import os
from pathlib import Path

from dlc_gait_assembly.shared.business.workspace_path_contracts import ManualPipelineOutputFolders, WorkspacePaths


def source_checkout_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "dlc_gait_assembly").is_dir():
            return parent
    return None


def find_project_root(start=None):
    """Return the application home, without using a caller's working directory."""
    return source_checkout_root() or Path.home() / "DLC-Gait-Assembler"


def resolve_workspace(project_root=None):
    configured = os.environ.get("DLC_GAIT_WORKSPACE")
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = (
            Path(project_root).expanduser().resolve() if project_root is not None else find_project_root()
        ) / "workspace"
    return WorkspacePaths(root)


def manual_pipeline_output_folders(project_root=None):
    root = resolve_workspace(project_root).manual
    folders = ManualPipelineOutputFolders(
        root=root,
        processed_videos=root / "video_processing",
        analyzed_videos=root / "deeplabcut" / "analyzed_videos",
        labeled_videos=root / "deeplabcut" / "labeled_videos",
        knee_correction=root / "knee_correction",
        gait_analysis=root / "gait_analysis",
    )
    for path in (
        folders.processed_videos,
        folders.analyzed_videos,
        folders.labeled_videos,
        folders.knee_correction,
        folders.gait_analysis,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return folders
