"""Automatic stickplot stage: invoke the owning manual stage and collect artifacts."""

from __future__ import annotations

from dataclasses import replace

from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import ProgressCallback


def execute_stickplot(run, progress_callback: ProgressCallback | None) -> None:
    settings = run.storage.gait_settings(run.profile.analysis_manifest, run.profile.calibration_map)
    inputs = run._alma_inputs(settings.input_mode)
    run.stickplot_results = run.operations.stickplots(
        inputs,
        run.stickplots_folder,
        replace(
            settings,
            generate_stickplot=True,
            generate_alma_representations=False,
            generate_rustlab1_parameters=False,
            stroke_analysis_enabled=False,
        ),
        progress_callback,
    )
    run._validate_alma_results(run.stickplot_results, inputs, require_stickplot=True)
