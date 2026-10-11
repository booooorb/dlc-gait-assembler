"""Automatic knee correction stage: invoke the owning manual stage and collect artifacts."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.automatic.runs.business.automatic_recording_pairing import pair_dlc_result, view_role
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import ProgressCallback


def execute_knee_correction(run, progress_callback: ProgressCallback | None) -> None:
    if run.profile.knee_manifest is None:
        if progress_callback is not None:
            progress_callback(1, 1, "No knee manifest; using DeepLabCut coordinates")
        return
    settings = run.storage.knee_settings(run.profile.knee_manifest)
    pair_jobs = []
    corrected: dict[str, list[Path]] = {}
    region_roles = {result.region: view_role(result.region) for result in run.dlc_results}
    three_view = set(region_roles.values()) >= {"left", "right", "bottom"}
    for result in run.dlc_results:
        if three_view and region_roles[result.region] == "bottom":
            corrected[result.region] = list(result.csv_paths)
            continue
        pairs = pair_dlc_result(result)
        incomplete = [pair for pair in pairs if not pair.is_paired]
        if incomplete:
            details = ", ".join(f"{pair.stem}: {pair.status}" for pair in incomplete)
            raise ValueError(f"Could not pair DeepLabCut outputs for {result.region}: {details}")
        pair_jobs.extend((result.region, pair) for pair in pairs)
    if not pair_jobs:
        raise RuntimeError("No DeepLabCut coordinate sets were available for knee correction.")
    run.analysis_csvs_by_region = run.storage.persist_knee_replacements(
        run, pair_jobs, settings, corrected, progress_callback
    )
