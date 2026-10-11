"""Define decoded-frame, media-metadata, and preview-access interfaces shared across workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".mpg", ".mpeg"}


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class MediaFrameSession(Protocol):
    """Owned decoding session; frames use RGB channel order."""

    info: VideoInfo

    def read_frame(self, index: int) -> np.ndarray | None: ...

    def read_timestamp(self, milliseconds: int) -> np.ndarray | None: ...

    def read_next(self) -> np.ndarray | None: ...

    def close(self) -> None: ...


class MediaAccessPort(Protocol):
    """Read images and open independently owned video sessions."""

    def open_video(self, path: Path) -> MediaFrameSession: ...

    def read_image(self, path: Path) -> np.ndarray: ...

    def file_size(self, path: Path) -> int: ...


class MediaInputInspectionPort(Protocol):
    def files_in_directory(self, directory: Path, recursive: bool = True) -> tuple[Path, ...]: ...
    def is_file(self, path: Path) -> bool: ...
    def probe(self, path: Path): ...
