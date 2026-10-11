"""Probe media dimensions, frame rate, duration, and stream metadata."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS, VideoInfo


def is_supported_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def probe_video(path: str | Path) -> VideoInfo:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to inspect video metadata. Install opencv from conda-forge.") from exc
    video_path = Path(path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        capture.release()
    duration = frame_count / fps if fps > 0 else 0.0
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Video has invalid dimensions: {video_path}")
    return VideoInfo(width=width, height=height, fps=fps, frame_count=frame_count, duration_seconds=duration)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def find_ffprobe(ffmpeg_path: str | None = None) -> str | None:
    if ffmpeg_path:
        sibling = Path(ffmpeg_path).with_name("ffprobe")
        if sibling.exists():
            return str(sibling)
    return shutil.which("ffprobe")


def has_audio_stream(input_path: Path, ffmpeg_path: str | None = None) -> bool:
    ffprobe_path = find_ffprobe(ffmpeg_path)
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
