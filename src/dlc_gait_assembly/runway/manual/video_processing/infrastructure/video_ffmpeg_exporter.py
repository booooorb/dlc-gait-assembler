"""Execute planned video jobs through the cancellable shared command adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import (
    ProcessingOptions,
    ProcessingResult,
)
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_ffmpeg_command import (
    build_processing_command,
)
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_ffmpeg_filters import build_filter_graph
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_output_allocator import output_path_for_input
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_output_allocator import (
    sanitize_output_suffix as _sanitize_output_suffix,
)
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession
from dlc_gait_assembly.shared.infrastructure.media_metadata_reader import ffmpeg_available, probe_video
from dlc_gait_assembly.shared.infrastructure.media_metadata_reader import has_audio_stream as _has_audio_stream


def process_video_output(
    ffmpeg_path: str,
    input_path: Path,
    output_dir: Path,
    source_width: int,
    source_height: int,
    options: ProcessingOptions,
    include_trim_audio: bool,
    crop_region_name: str | None,
    include_crop_region_name: bool,
    *,
    feedback=None,
) -> ProcessingResult:
    filter_graph = build_filter_graph(source_width, source_height, options, include_audio=include_trim_audio)
    output_path = output_path_for_input(input_path, output_dir, crop_region_name, include_crop_region_name)
    command = build_processing_command(
        ffmpeg_path=ffmpeg_path,
        input_path=input_path,
        output_path=output_path,
        filter_graph=filter_graph,
        options=options,
        has_trim=options.has_trim(),
        include_trim_audio=include_trim_audio,
    )
    completed = ExternalProcessSession().run(
        ExternalCommand(tuple(command)), checkpoint=feedback.checkpoint if feedback else None
    )
    if completed.returncode != 0:
        stderr = completed.output.strip() or "ffmpeg failed without an error message."
        raise RuntimeError(stderr[-3000:])
    return ProcessingResult(
        input_path=input_path, output_path=output_path, command=command, crop_region_name=crop_region_name
    )


class VideoFFmpegExporter:
    """Translate one planned job to FFmpeg and return the produced artifact."""

    def export(self, input_path, output_dir, options, crop_region_name, use_crop_region_folder, *, feedback=None):
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            raise RuntimeError("ffmpeg was not found. Install it with conda-forge before processing videos.")
        input_path = Path(input_path).expanduser().resolve()
        output_dir = Path(output_dir).expanduser().resolve()
        if use_crop_region_folder:
            output_dir = output_dir / _sanitize_output_suffix(crop_region_name or "crop")
        output_dir.mkdir(parents=True, exist_ok=True)
        info = probe_video(input_path)
        include_audio = options.has_trim() and _has_audio_stream(input_path, ffmpeg_path)
        return process_video_output(
            ffmpeg_path,
            input_path,
            output_dir,
            info.width,
            info.height,
            options,
            include_audio,
            crop_region_name,
            False,
            feedback=feedback,
        )

    available = staticmethod(ffmpeg_available)
