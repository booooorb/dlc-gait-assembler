"""Compatibility exports for the original video_processing module."""

from dlc_gait_assembly.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.domain.regions import NormalizedRect, PixelRect
from dlc_gait_assembly.domain.trimming import TrimRange
from dlc_gait_assembly.domain.videos import VIDEO_EXTENSIONS, VideoInfo
from dlc_gait_assembly.services.ffmpeg import (
    ProcessingOptions,
    ProcessingResult,
    build_enhancement_filters,
    build_filter_graph,
    ffmpeg_available,
    normalized_to_pixel_rect,
    process_video,
)
from dlc_gait_assembly.services.project_paths import make_session_output_dir
from dlc_gait_assembly.services.video_io import is_supported_video, probe_video

__all__ = [
    "NormalizedRect",
    "PixelRect",
    "EnhancementSettings",
    "TrimRange",
    "ProcessingOptions",
    "ProcessingResult",
    "VIDEO_EXTENSIONS",
    "VideoInfo",
    "build_enhancement_filters",
    "build_filter_graph",
    "ffmpeg_available",
    "is_supported_video",
    "make_session_output_dir",
    "normalized_to_pixel_rect",
    "probe_video",
    "process_video",
]
