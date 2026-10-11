"""Automatic labeled video stage: invoke the owning manual stage and collect artifacts."""

from __future__ import annotations

from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import ProgressCallback


def execute_labeled_video(run, progress_callback: ProgressCallback | None) -> None:
    coordinate_paths = {result.region: (result.csv_paths, result.h5_paths) for result in run.dlc_results}
    labeled_results = run.operations.labeled_videos(
        run.dlc_jobs, run.dlc_results, run.deeplabcut_folder, progress_callback
    )
    run.dlc_results = run._validate_dlc_results(labeled_results, require_labeled_videos=True)
    for result in run.dlc_results:
        if (result.csv_paths, result.h5_paths) != coordinate_paths[result.region]:
            raise RuntimeError(f'DeepLabCut labeled-video creation changed the coordinate files for "{result.region}".')
