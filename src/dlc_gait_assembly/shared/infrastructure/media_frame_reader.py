"""Decode RGB image/video frames and own the lifetime of OpenCV captures."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from dlc_gait_assembly.shared.business.media_access_contracts import VideoInfo
from dlc_gait_assembly.shared.infrastructure.media_metadata_reader import probe_video


class OpenCVFrameSession:
    """A video capture that avoids redundant seeks during sequential playback."""

    def __init__(self, path: Path):
        self._capture = cv2.VideoCapture(str(path))
        if not self._capture.isOpened():
            self.close()
            raise OSError(f"Could not open video: {path}")

        def value(property_id: int) -> float:
            result = float(self._capture.get(property_id))
            return result if math.isfinite(result) and result > 0 else 0.0

        fps = value(cv2.CAP_PROP_FPS)
        count = int(value(cv2.CAP_PROP_FRAME_COUNT))
        self.info = VideoInfo(
            int(value(cv2.CAP_PROP_FRAME_WIDTH)),
            int(value(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps,
            count,
            count / fps if fps else 0.0,
        )
        self._next_index = 0

    def read_next(self) -> np.ndarray | None:
        if self._capture is None:
            return None
        (success, frame) = self._capture.read()
        self._next_index += 1
        if not success or frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def read_frame(self, index: int) -> np.ndarray | None:
        if self._capture is None:
            return None
        index = max(0, int(index))
        if self.info.frame_count:
            index = min(index, self.info.frame_count - 1)
        if self._next_index != index:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            self._next_index = index
        return self.read_next()

    def read_timestamp(self, milliseconds: int) -> np.ndarray | None:
        if self._capture is None:
            return None
        if self.info.fps > 0 and self.info.frame_count > 0:
            frame = self.read_frame(round(milliseconds / 1000 * self.info.fps))
        else:
            self._capture.set(cv2.CAP_PROP_POS_MSEC, float(milliseconds))
            self._next_index = -1
            frame = self.read_next()
        if frame is None and self.info.frame_count > 0:
            return self.read_frame(self.info.frame_count - 1)
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class MediaFrameReader:
    """Shared media access adapter. Each caller owns and closes its session."""

    def open_video(self, path: Path) -> OpenCVFrameSession:
        return OpenCVFrameSession(path)

    def read_image(self, path: Path) -> np.ndarray:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise OSError(f"Could not open image: {path}")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def file_size(self, path: Path) -> int:
        return path.stat().st_size

    def files_in_directory(self, directory, recursive=True):
        root = Path(directory).expanduser().resolve()
        return tuple(path for path in sorted(root.rglob("*") if recursive else root.glob("*")) if path.is_file())

    def is_file(self, path):
        return Path(path).is_file()

    probe = staticmethod(probe_video)
