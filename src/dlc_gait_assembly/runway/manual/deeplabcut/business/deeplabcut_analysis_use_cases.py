"""Coordinate validated pose-analysis and labeled-video jobs through project, bridge, and artifact ports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import (
    DlcAnalysisJob,
    DlcAnalysisResult,
)


def run_deeplabcut_analysis(
    jobs: list[DlcAnalysisJob],
    output_folder: str | Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
    *,
    ports,
) -> list[DlcAnalysisResult]:
    """Run DLC pose analysis without creating labeled review videos."""
    if not jobs:
        return []
    destination = ports.artifacts.resolve(output_folder)
    request_jobs = []
    total = len(jobs)
    total_videos = sum(len(job.video_paths) for job in jobs)
    for job in jobs:
        config_path = ports.projects.validate_project(job.model_path)
        analysis_folder = ports.artifacts.analysis_folder(destination, job.region)
        request_jobs.append(
            {
                "region": job.region,
                "config_path": str(config_path),
                "video_paths": [str(ports.artifacts.resolve(path)) for path in job.video_paths],
                "analysis_folder": str(analysis_folder),
            }
        )
        if progress_callback is not None:
            progress_callback(0, 1000, f"Validating DeepLabCut model for {job.region}")
    payload = ports.bridge.request(
        {"operation": "analyze", "jobs": request_jobs},
        total_videos,
        "analysis",
        "Initializing DeepLabCut model",
        "DeepLabCut analysis",
        progress_callback,
    )
    results = [ports.bridge.decode_result(item) for item in payload.get("results", [])]
    if len(results) != len(jobs):
        raise RuntimeError("DeepLabCut returned an incomplete set of region results.")
    if progress_callback is not None:
        progress_callback(total, total, "DeepLabCut analysis complete")
    return results


def run_deeplabcut_labeled_video_creation(
    jobs: list[DlcAnalysisJob],
    analysis_results: list[DlcAnalysisResult],
    output_folder: str | Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
    *,
    ports,
) -> list[DlcAnalysisResult]:
    """Create review videos from the current, potentially corrected, coordinates."""
    if not jobs:
        return []
    results_by_region = {result.region: result for result in analysis_results}
    if set(results_by_region) != {job.region for job in jobs}:
        raise ValueError("DeepLabCut analysis results do not match the configured regions.")
    destination = ports.artifacts.resolve(output_folder)
    request_jobs = []
    total_videos = sum(len(job.video_paths) for job in jobs)
    for job in jobs:
        result = results_by_region[job.region]
        coordinate_paths = (*result.csv_paths, *result.h5_paths)
        coordinate_folders = {ports.artifacts.resolve(path.parent) for path in coordinate_paths}
        if len(coordinate_folders) != 1:
            raise ValueError(f'Analyzed files for region "{job.region}" are not in one output folder.')
        config_path = ports.projects.validate_project(job.model_path)
        labeled_videos_folder = ports.artifacts.labeled_folder(destination, job.region)
        request_jobs.append(
            {
                "region": job.region,
                "config_path": str(config_path),
                "video_paths": [str(path) for path in job.video_paths],
                "analysis_folder": str(next(iter(coordinate_folders))),
                "labeled_videos_folder": str(labeled_videos_folder),
                "csv_paths": [str(path) for path in result.csv_paths],
                "h5_paths": [str(path) for path in result.h5_paths],
            }
        )
    payload = ports.bridge.request(
        {"operation": "create_labeled_videos", "jobs": request_jobs},
        total_videos,
        "labels",
        "Preparing corrected coordinates for labeled videos",
        "DeepLabCut labeled-video creation",
        progress_callback,
    )
    results = [ports.bridge.decode_result(item) for item in payload.get("results", [])]
    if len(results) != len(jobs):
        raise RuntimeError("DeepLabCut returned an incomplete set of labeled videos.")
    if progress_callback is not None:
        progress_callback(1, 1, "Labeled videos complete")
    return results


class DeepLabCutAnalysisUseCases:
    """Run both manual and automatic DeepLabCut jobs through the same validated handoffs."""

    def __init__(self, projects, bridge, artifacts):
        self.projects, self.bridge, self.artifacts = projects, bridge, artifacts

    def analyze(self, jobs, output_folder, progress_callback=None):
        return run_deeplabcut_analysis(jobs, output_folder, progress_callback, ports=self)

    def create_labeled_videos(self, jobs, results, output_folder, progress_callback=None):
        return run_deeplabcut_labeled_video_creation(jobs, results, output_folder, progress_callback, ports=self)
