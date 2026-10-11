"""Allocate self-contained automatic sessions and numbered stage output directories."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.runway.automatic.runs.business.automatic_recording_pairing import safe_name
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


def unique_run_folder(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    suffix = 2
    while (numbered := candidate.with_name(f"{candidate.name}_{suffix}")).exists():
        suffix += 1
    return numbered


def allocate_run_output(run, project_root, output_root, profile):
    run.project_root = Path(project_root).expanduser().resolve()
    base = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else resolve_workspace(run.project_root).automatic_runs
    )
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run.output_folder = unique_run_folder(base / f"{timestamp}_{safe_name(profile.name)}")
    run.output_folder.mkdir(parents=True, exist_ok=True)
    run.processed_videos_folder = run.output_folder / "01_processed_videos"
    run.deeplabcut_folder = run.output_folder / "02_deeplabcut"
    run.analyzed_videos_folder = run.deeplabcut_folder / "analyzed_videos"
    run.labeled_videos_folder = run.deeplabcut_folder / "labeled_videos"
    run.knee_correction_folder = run.output_folder / "03_knee_correction"
    run.stickplots_folder = run.output_folder / "04_stickplots"
    run.gait_analysis_folder = run.output_folder / "05_gait_analysis"
    for folder in (
        run.processed_videos_folder,
        run.analyzed_videos_folder,
        run.labeled_videos_folder,
        run.knee_correction_folder,
        run.stickplots_folder,
        run.gait_analysis_folder,
    ):
        folder.mkdir(parents=True, exist_ok=True)
