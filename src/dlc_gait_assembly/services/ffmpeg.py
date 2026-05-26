from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from dlc_gait_assembly.domain.regions import NormalizedRect, PixelRect
from dlc_gait_assembly.services.video_io import probe_video


@dataclass(frozen=True)
class ProcessingOptions:
    crop_enabled: bool = False
    crop_rect: NormalizedRect | None = None
    invert_enabled: bool = False
    invert_rect: NormalizedRect | None = None
    invert_rects: tuple[NormalizedRect, ...] = ()
    crf: int = 18
    preset: str = "veryfast"

    def has_work(self) -> bool:
        has_crop = self.crop_enabled and self.crop_rect is not None and self.crop_rect.is_usable()
        has_invert = self.invert_enabled and any(rect.is_usable() for rect in self.effective_invert_rects())
        return has_crop or has_invert

    def effective_invert_rects(self) -> tuple[NormalizedRect, ...]:
        if self.invert_rects:
            return self.invert_rects
        if self.invert_rect is not None:
            return (self.invert_rect,)
        return ()


@dataclass(frozen=True)
class ProcessingResult:
    input_path: Path
    output_path: Path
    command: list[str]


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def process_video(input_path: str | Path, output_dir: str | Path, options: ProcessingOptions) -> ProcessingResult:
    if not options.has_work():
        raise ValueError("Enable crop, invert, or both before processing.")

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError("ffmpeg was not found. Install it with conda-forge before processing videos.")

    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    info = probe_video(input_path)
    filter_graph = build_filter_graph(info.width, info.height, options)
    output_path = _unique_output_path(output_dir / f"{input_path.stem}_processed.mp4")

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
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        options.preset,
        "-crf",
        str(options.crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "ffmpeg failed without an error message."
        raise RuntimeError(stderr[-3000:])

    return ProcessingResult(input_path=input_path, output_path=output_path, command=command)


def build_filter_graph(source_width: int, source_height: int, options: ProcessingOptions) -> str:
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

    if options.crop_enabled and options.crop_rect is not None and options.crop_rect.is_usable():
        crop = normalized_to_pixel_rect(options.crop_rect, source_width, source_height)
        parts.append(f"{current}crop={crop.width}:{crop.height}:{crop.x}:{crop.y},format=yuv420p[vout]")
    elif current != "[0:v]":
        parts.append(f"{current}format=yuv420p[vout]")
    else:
        raise ValueError("No video filters were enabled.")

    return ";".join(parts)


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


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _even(value: int) -> int:
    return value if value % 2 == 0 else value - 1
