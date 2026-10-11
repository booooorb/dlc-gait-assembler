"""Assemble encoding, audio, and filter arguments for one FFmpeg export."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions


def build_processing_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    filter_graph: str,
    options: ProcessingOptions,
    has_trim: bool,
    include_trim_audio: bool,
) -> list[str]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[vout]",
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-tag:v",
        "avc1",
        "-preset",
        options.preset,
        "-crf",
        str(options.crf),
        "-pix_fmt",
        "yuv420p",
        "-fps_mode",
        "passthrough",
    ]
    if has_trim:
        if include_trim_audio:
            command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
        else:
            command.append("-an")
    else:
        command.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", "-f", "mp4", str(output_path)])
    return command
