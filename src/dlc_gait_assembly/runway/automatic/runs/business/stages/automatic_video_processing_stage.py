"""Automatic video processing stage: invoke the owning manual stage and collect artifacts."""

from __future__ import annotations

from dataclasses import replace

from dlc_gait_assembly.runway.automatic.runs.business.automatic_recording_pairing import trim_ranges_for_video
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import ProgressCallback
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionFeedback, ExecutionProgress


def execute_video_processing(run, progress_callback: ProgressCallback | None) -> None:
    (options, trim_ranges) = run.storage.video_settings(run.profile.processing_manifest)
    destination = run.processed_videos_folder
    total = len(run.video_paths)
    feedback = (
        ExecutionFeedback(cancellation_check=progress_callback.checkpoint)
        if isinstance(progress_callback, ExecutionProgress)
        else ExecutionFeedback()
    )
    for index, video_path in enumerate(run.video_paths, start=1):
        trims = trim_ranges_for_video(trim_ranges, video_path)
        results = run.operations.video.process_outputs(
            video_path, destination, replace(options, trim_ranges=trims), feedback=feedback
        )
        for result in results:
            region = result.crop_region_name or "Full frame"
            run.processed_by_region.setdefault(region, []).append(result.output_path)
        if progress_callback is not None:
            progress_callback(index, total, f"Processed {video_path.name}")
    if not run.processed_by_region:
        raise RuntimeError("Video processing did not produce any output videos.")
