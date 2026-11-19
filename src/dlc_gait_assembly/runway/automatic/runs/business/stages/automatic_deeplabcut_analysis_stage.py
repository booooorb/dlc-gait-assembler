"""Automatic deeplabcut analysis stage: invoke the owning manual stage and collect artifacts."""

from __future__ import annotations

from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import ProgressCallback


def execute_deeplabcut_analysis(run, progress_callback: ProgressCallback | None) -> None:
    missing_models = set(run.processed_by_region) - set(run.profile.deeplabcut_models)
    if missing_models:
        names = ", ".join(sorted(missing_models))
        raise ValueError(f"The profile has no DeepLabCut model assigned for: {names}.")
    run.dlc_jobs = run.build_dlc_jobs()
    results = run.operations.deeplabcut_analysis(run.dlc_jobs, run.deeplabcut_folder, progress_callback)
    run.dlc_results = run._validate_dlc_results(results)
    run.analysis_csvs_by_region = {result.region: list(result.csv_paths) for result in run.dlc_results}
