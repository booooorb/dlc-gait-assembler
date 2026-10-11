"""Automatic gait analysis stage: invoke the owning manual stage and collect artifacts."""

from __future__ import annotations

from dataclasses import replace

from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import ProgressCallback


def execute_gait_analysis(run, progress_callback: ProgressCallback | None) -> None:
    settings = run.storage.gait_settings(run.profile.analysis_manifest, run.profile.calibration_map)
    inputs = run._alma_inputs(settings.input_mode)
    run.gait_results = run.operations.gait(
        inputs, run.gait_analysis_folder, replace(settings, generate_stickplot=False), progress_callback
    )
    run._validate_alma_results(run.gait_results, inputs)
