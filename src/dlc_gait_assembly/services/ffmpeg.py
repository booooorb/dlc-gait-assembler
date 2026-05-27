from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess

from dlc_gait_assembly.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.domain.regions import NormalizedRect, PixelRect
from dlc_gait_assembly.domain.trimming import TrimRange
from dlc_gait_assembly.services.video_io import probe_video


@dataclass(frozen=True)
class ProcessingOptions:
    crop_enabled: bool = False
    crop_rect: NormalizedRect | None = None
    invert_enabled: bool = False
    invert_rect: NormalizedRect | None = None
    invert_rects: tuple[NormalizedRect, ...] = ()
    enhancements: EnhancementSettings = field(default_factory=EnhancementSettings)
    trim_ranges: tuple[TrimRange, ...] = ()
    crf: int = 18
    preset: str = "slow"

    def has_work(self) -> bool:
        has_crop = self.crop_enabled and self.crop_rect is not None and self.crop_rect.is_usable()
        has_invert = self.invert_enabled and any(rect.is_usable() for rect in self.effective_invert_rects())
        return has_crop or has_invert or self.enhancements.is_enabled() or self.has_trim()

    def effective_invert_rects(self) -> tuple[NormalizedRect, ...]:
        if self.invert_rects:
            return self.invert_rects
        if self.invert_rect is not None:
            return (self.invert_rect,)
        return ()

    def has_trim(self) -> bool:
        return any(trim.is_usable() for trim in self.trim_ranges)


@dataclass(frozen=True)
class ProcessingResult:
    input_path: Path
    output_path: Path
    command: list[str]


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _find_ffprobe(ffmpeg_path: str | None = None) -> str | None:
    if ffmpeg_path:
        sibling = Path(ffmpeg_path).with_name("ffprobe")
        if sibling.exists():
            return str(sibling)
    return shutil.which("ffprobe")


def _has_audio_stream(input_path: Path, ffmpeg_path: str | None = None) -> bool:
    ffprobe_path = _find_ffprobe(ffmpeg_path)
    if ffprobe_path is None:
        return False

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(input_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode == 0 and bool(completed.stdout.strip())


def process_video(input_path: str | Path, output_dir: str | Path, options: ProcessingOptions) -> ProcessingResult:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError("ffmpeg was not found. Install it with conda-forge before processing videos.")

    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    info = probe_video(input_path)
    include_trim_audio = options.has_trim() and _has_audio_stream(input_path, ffmpeg_path)
    filter_graph = build_filter_graph(
        info.width,
        info.height,
        options,
        include_audio=include_trim_audio,
    )
    output_path = output_path_for_input(input_path, output_dir)

    command = build_processing_command(
        ffmpeg_path=ffmpeg_path,
        input_path=input_path,
        output_path=output_path,
        filter_graph=filter_graph,
        options=options,
        has_trim=options.has_trim(),
        include_trim_audio=include_trim_audio,
    )

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "ffmpeg failed without an error message."
        raise RuntimeError(stderr[-3000:])

    return ProcessingResult(input_path=input_path, output_path=output_path, command=command)


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


def build_filter_graph(
    source_width: int,
    source_height: int,
    options: ProcessingOptions,
    include_audio: bool = False,
    source_fps: float | None = None,
) -> str:
    parts: list[str] = []
    current = "[0:v]"

    if options.invert_enabled:
        for index, invert_norm in enumerate(rect for rect in options.effective_invert_rects() if rect.is_usable()):
            invert = normalized_to_pixel_rect(invert_norm, source_width, source_height)
            base = f"[base_{index}]"
            region = f"[region_{index}]"
            flipped = f"[flipped_{index}]"
            inverted = f"[v_inverted_{index}]"
            parts.append(f"{current}split=2{base}{region}")
            parts.append(f"{region}crop={invert.width}:{invert.height}:{invert.x}:{invert.y},vflip{flipped}")
            parts.append(f"{base}{flipped}overlay={invert.x}:{invert.y}{inverted}")
            current = inverted

    enhancement_filters = build_enhancement_filters(options.enhancements)
    if enhancement_filters:
        enhanced = "[v_enhanced]"
        parts.append(f"{current}{','.join(enhancement_filters)}{enhanced}")
        current = enhanced

    trim_ranges = _normalized_trim_ranges(options.trim_ranges)

    if options.crop_enabled and options.crop_rect is not None and options.crop_rect.is_usable():
        crop = normalized_to_pixel_rect(options.crop_rect, source_width, source_height)
        if trim_ranges:
            cropped = "[v_cropped]"
            parts.append(f"{current}crop={crop.width}:{crop.height}:{crop.x}:{crop.y}{cropped}")
            current = cropped
        else:
            parts.append(f"{current}crop={crop.width}:{crop.height}:{crop.x}:{crop.y},format=yuv420p[vout]")
            return ";".join(parts)

    if trim_ranges:
        parts.extend(_build_trim_filters(current, trim_ranges, include_audio))
    elif current != "[0:v]":
        parts.append(f"{current}format=yuv420p[vout]")
    else:
        parts.append("[0:v]format=yuv420p[vout]")

    return ";".join(parts)


def _build_trim_filters(
    current: str,
    trim_ranges: tuple[TrimRange, ...],
    include_audio: bool,
) -> list[str]:
    parts: list[str] = []
    if len(trim_ranges) == 1:
        trim = trim_ranges[0]
        parts.append(f"{current}{_video_trim_filter(trim)},format=yuv420p[vout]")
        if include_audio:
            parts.append(
                f"[0:a]atrim=start={_fmt_float(trim.start_seconds())}:"
                f"end={_fmt_float(trim.end_seconds())},asetpts=PTS-STARTPTS[aout]"
            )
        return parts

    video_sources = "".join(f"[trim_src_{index}]" for index in range(len(trim_ranges)))
    parts.append(f"{current}split={len(trim_ranges)}{video_sources}")

    if include_audio:
        audio_sources = "".join(f"[atrim_src_{index}]" for index in range(len(trim_ranges)))
        parts.append(f"[0:a]asplit={len(trim_ranges)}{audio_sources}")

    concat_inputs = []
    for index, trim in enumerate(trim_ranges):
        parts.append(f"[trim_src_{index}]{_video_trim_filter(trim)}[vtrim_{index}]")
        concat_inputs.append(f"[vtrim_{index}]")
        if include_audio:
            parts.append(
                f"[atrim_src_{index}]atrim=start={_fmt_float(trim.start_seconds())}:"
                f"end={_fmt_float(trim.end_seconds())},asetpts=PTS-STARTPTS[atrim_{index}]"
            )
            concat_inputs.append(f"[atrim_{index}]")

    if include_audio:
        parts.append(f"{''.join(concat_inputs)}concat=n={len(trim_ranges)}:v=1:a=1[vconcat][aout]")
        parts.append("[vconcat]format=yuv420p[vout]")
    else:
        parts.append(f"{''.join(concat_inputs)}concat=n={len(trim_ranges)}:v=1:a=0,format=yuv420p[vout]")

    return parts


def _video_trim_filter(trim: TrimRange) -> str:
    return (
        f"trim=start={_fmt_float(trim.start_seconds())}:"
        f"end={_fmt_float(trim.end_seconds())},setpts=PTS-STARTPTS"
    )


def _trim_sort_key(trim: TrimRange) -> tuple[int, int]:
    return trim.start_ms, trim.end_ms


def _normalized_trim_ranges(trim_ranges: tuple[TrimRange, ...]) -> tuple[TrimRange, ...]:
    sorted_ranges = sorted((trim for trim in trim_ranges if trim.is_usable()), key=_trim_sort_key)
    merged: list[TrimRange] = []

    for trim in sorted_ranges:
        if not merged or trim.start_ms > merged[-1].end_ms:
            merged.append(trim)
            continue

        previous = merged[-1]
        merged[-1] = TrimRange(previous.start_ms, max(previous.end_ms, trim.end_ms))

    return tuple(merged)


def build_enhancement_filters(settings: EnhancementSettings) -> list[str]:
    filters: list[str] = []
    if not settings.is_enabled():
        return filters

    if abs(settings.exposure) > 0.001 or abs(settings.black_level) > 0.001:
        filters.append(f"exposure=exposure={_fmt_float(settings.exposure)}:black={_fmt_float(settings.black_level)}")

    if _levels_enabled(settings):
        input_black = _clamp_float(settings.input_black, 0.0, 0.99)
        input_white = _clamp_float(settings.input_white, input_black + 0.01, 1.0)
        output_black = _clamp_float(settings.output_black, 0.0, 0.99)
        output_white = _clamp_float(settings.output_white, output_black + 0.01, 1.0)
        filters.append(
            "colorlevels="
            f"rimin={_fmt_float(input_black)}:"
            f"gimin={_fmt_float(input_black)}:"
            f"bimin={_fmt_float(input_black)}:"
            f"rimax={_fmt_float(input_white)}:"
            f"gimax={_fmt_float(input_white)}:"
            f"bimax={_fmt_float(input_white)}:"
            f"romin={_fmt_float(output_black)}:"
            f"gomin={_fmt_float(output_black)}:"
            f"bomin={_fmt_float(output_black)}:"
            f"romax={_fmt_float(output_white)}:"
            f"gomax={_fmt_float(output_white)}:"
            f"bomax={_fmt_float(output_white)}"
        )

    effective_gamma = 1.0 / settings.tone_scale
    if (
        abs(settings.brightness) > 0.001
        or abs(settings.contrast - 1.0) > 0.001
        or abs(effective_gamma - 1.0) > 0.001
    ):
        filters.append(
            "eq="
            f"brightness={_fmt_float(settings.brightness)}:"
            f"contrast={_fmt_float(settings.contrast)}:"
            f"gamma={_fmt_float(effective_gamma)}"
        )

    if settings.sharpening > 0.001:
        filters.append(f"unsharp=5:5:{_fmt_float(settings.sharpening)}:5:5:0")

    if settings.cas > 0.001:
        filters.append(f"cas=strength={_fmt_float(settings.cas)}")

    return filters


def normalized_to_pixel_rect(rect: NormalizedRect, source_width: int, source_height: int) -> PixelRect:
    rect = rect.clamped()
    left = int(round(rect.x * source_width))
    top = int(round(rect.y * source_height))
    right = int(round((rect.x + rect.width) * source_width))
    bottom = int(round((rect.y + rect.height) * source_height))

    left = _even(_clamp_int(left, 0, max(0, source_width - 2)))
    top = _even(_clamp_int(top, 0, max(0, source_height - 2)))
    right = _even(_clamp_int(right, left + 2, source_width))
    bottom = _even(_clamp_int(bottom, top + 2, source_height))

    if right <= left:
        right = min(source_width, left + 2)
    if bottom <= top:
        bottom = min(source_height, top + 2)

    width = right - left
    height = bottom - top
    if width % 2:
        width -= 1
    if height % 2:
        height -= 1
    width = max(2, min(width, source_width - left))
    height = max(2, min(height, source_height - top))

    return PixelRect(x=left, y=top, width=width, height=height)


def _unique_output_path(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index:02d}{path.suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not create a unique output path for {path}")


def output_path_for_input(input_path: str | Path, output_dir: str | Path) -> Path:
    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_path = _unique_output_path(output_dir / f"{input_path.stem}_processed.mp4")
    if output_path == input_path:
        raise RuntimeError("Refusing to overwrite the original input video.")
    return output_path


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def _levels_enabled(settings: EnhancementSettings) -> bool:
    return any(
        (
            abs(settings.input_black) > 0.001,
            abs(settings.input_white - 1.0) > 0.001,
            abs(settings.output_black) > 0.001,
            abs(settings.output_white - 1.0) > 0.001,
        )
    )


def _fmt_float(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")
