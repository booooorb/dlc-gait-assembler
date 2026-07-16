from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    current = Path(start).resolve() if start is not None else Path.cwd().resolve()
    if current.is_file():
        current = current.parent

    for parent in [current, *current.parents]:
        if (parent / "outputs").exists() or (parent / "pyproject.toml").exists():
            return parent

    return Path.cwd().resolve()


def make_session_output_dir(output_root: str | Path, now: datetime | None = None) -> Path:
    root = Path(output_root).expanduser().resolve()
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = root / stamp
    if not session_dir.exists():
        session_dir.mkdir(parents=True, exist_ok=False)
        return session_dir

    for index in range(2, 1000):
        candidate = root / f"{stamp}_{index:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate

    raise RuntimeError(f"Could not create a unique output folder under {root}")


@dataclass(frozen=True)
class ManualPipelineOutputFolders:
    root: Path
    processed_videos: Path
    analyzed_videos: Path
    labeled_videos: Path
    knee_correction: Path
    gait_analysis: Path


def manual_pipeline_output_folders(
    project_root: str | Path,
) -> ManualPipelineOutputFolders:
    root = Path(project_root).expanduser().resolve() / "outputs" / "manual_pipeline"
    folders = ManualPipelineOutputFolders(
        root=root,
        processed_videos=root / "processed_videos",
        analyzed_videos=root / "analyzed_videos",
        labeled_videos=root / "labeled_videos",
        knee_correction=root / "knee_correction",
        gait_analysis=root / "gait_analysis",
    )
    for folder in (
        folders.processed_videos,
        folders.analyzed_videos,
        folders.labeled_videos,
        folders.knee_correction,
        folders.gait_analysis,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    return folders
