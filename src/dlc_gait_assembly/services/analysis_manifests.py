"""Compatibility facade for workflow manifest serializers.

New code should import from :mod:`dlc_gait_assembly.services.manifests` or its
workflow-specific submodules.
"""

from dlc_gait_assembly.services.manifests import (
    ANALYSIS_MANIFEST_FORMAT_VERSION,
    ANALYSIS_MANIFEST_TYPE,
    KNEE_ANALYSIS_MANIFEST_FORMAT_VERSION,
    KNEE_ANALYSIS_MANIFEST_TYPE,
    VIDEO_SETTINGS_MANIFEST_FORMAT_VERSION,
    VIDEO_SETTINGS_MANIFEST_TYPE,
    alma_settings_from_manifest,
    analysis_manifest_data,
    knee_analysis_manifest_data,
    knee_settings_from_manifest,
    read_analysis_manifest,
    read_knee_analysis_manifest,
    read_video_settings_manifest,
    video_settings_from_manifest,
    video_settings_manifest_data,
    write_analysis_manifest,
    write_knee_analysis_manifest,
    write_video_settings_manifest,
)

__all__ = [
    "ANALYSIS_MANIFEST_FORMAT_VERSION",
    "ANALYSIS_MANIFEST_TYPE",
    "KNEE_ANALYSIS_MANIFEST_FORMAT_VERSION",
    "KNEE_ANALYSIS_MANIFEST_TYPE",
    "VIDEO_SETTINGS_MANIFEST_FORMAT_VERSION",
    "VIDEO_SETTINGS_MANIFEST_TYPE",
    "alma_settings_from_manifest",
    "analysis_manifest_data",
    "knee_analysis_manifest_data",
    "knee_settings_from_manifest",
    "read_analysis_manifest",
    "read_knee_analysis_manifest",
    "read_video_settings_manifest",
    "video_settings_from_manifest",
    "video_settings_manifest_data",
    "write_analysis_manifest",
    "write_knee_analysis_manifest",
    "write_video_settings_manifest",
]
