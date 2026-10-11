"""Validate profile assets and source videos before allocating a run."""

from __future__ import annotations

from pathlib import Path


def preflight_automatic_run(profile, video_paths, storage, enable_knee_correction=True, enable_gait_analysis=True):
    video_paths = tuple(Path(path) for path in video_paths)
    if not video_paths:
        raise ValueError("Add at least one source video before running the pipeline.")
    if len(set(video_paths)) != len(video_paths):
        raise ValueError("Each source video may only be added to a pipeline run once.")
    missing = [path for path in video_paths if not storage.is_file(path)]
    if missing:
        raise FileNotFoundError(f"Source video no longer exists: {missing[0]}")
    if profile.processing_manifest is None:
        raise ValueError("The selected profile needs a video settings manifest.")
    if not storage.is_file(Path(profile.processing_manifest)):
        raise FileNotFoundError(f"Video settings manifest no longer exists: {profile.processing_manifest}")
    gait_requested = enable_gait_analysis and profile.gait_analysis_enabled
    if gait_requested and profile.analysis_manifest is None:
        raise ValueError("The selected profile needs a gait analysis manifest.")
    if gait_requested and profile.calibration_map is None:
        raise ValueError("The selected profile needs a calibration map for gait analysis.")
    if gait_requested and (not storage.is_file(Path(profile.analysis_manifest))):
        raise FileNotFoundError(f"Gait analysis manifest no longer exists: {profile.analysis_manifest}")
    if gait_requested and (not storage.is_file(Path(profile.calibration_map))):
        raise FileNotFoundError(f"Calibration map no longer exists: {profile.calibration_map}")
    knee_requested = enable_knee_correction and profile.knee_correction_enabled
    if knee_requested and profile.knee_manifest is None:
        raise ValueError("The selected profile needs a knee correction manifest.")
    if knee_requested and (not storage.is_file(Path(profile.knee_manifest))):
        raise FileNotFoundError(f"Knee correction manifest no longer exists: {profile.knee_manifest}")
    return video_paths
