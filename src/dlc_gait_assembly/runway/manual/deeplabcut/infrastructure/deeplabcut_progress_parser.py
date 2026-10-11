"""Interpret DeepLabCut command output as analysis progress events."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

DLC_PROGRESS_SCALE = 1000
TQDM_PERCENT_PATTERN = re.compile("(?<!\\d)(\\d{1,3})%\\|")


class DlcProgressParser:
    """Translate DLC/tqdm process output into monotonic pipeline progress."""

    def __init__(
        self, total_videos: int, progress_callback: Callable[[int, int, str], None] | None, phase: str = "analysis"
    ):
        if phase not in {"analysis", "labels"}:
            raise ValueError(f"Unsupported DeepLabCut progress phase: {phase}")
        self.total_videos = max(1, total_videos)
        self.progress_callback = progress_callback
        self.expected_phase = phase
        self.phase = phase
        self.phase_index = 0
        self.video_name = ""
        self.last_value = -1
        self.analysis_step_offset = 0.0
        self.analysis_step_weight = 1.0
        self.detector_started = False

    def feed(self, output_line: str) -> None:
        line = output_line.strip()
        analysis_marker = "Starting to analyze "
        labels_marker = "Starting to process video:"
        if self.expected_phase == "analysis" and analysis_marker in line:
            video_path = line.split(analysis_marker, 1)[1].strip()
            self._begin_video("analysis", video_path)
            return
        if self.expected_phase == "labels" and labels_marker in line:
            video_path = line.split(labels_marker, 1)[1].strip()
            self._begin_video("labels", video_path)
            return
        if self.phase == "analysis" and "Running detector with batch size" in line:
            self.detector_started = True
            self.analysis_step_offset = 0.0
            self.analysis_step_weight = 0.3
            return
        if self.phase == "analysis" and "Running pose prediction with batch size" in line:
            self.analysis_step_offset = 0.3 if self.detector_started else 0.0
            self.analysis_step_weight = 0.7 if self.detector_started else 1.0
            return
        match = TQDM_PERCENT_PATTERN.search(line)
        if match is not None and self.phase:
            video_percent = min(100, int(match.group(1)))
            if self.phase == "analysis":
                video_percent = round(
                    100 * (self.analysis_step_offset + self.analysis_step_weight * video_percent / 100.0)
                )
            self._emit(video_percent)

    def finish(self) -> None:
        self.phase = self.expected_phase
        self.phase_index = self.total_videos
        self._emit(100, force=True)

    def _begin_video(self, phase: str, video_path: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self.phase_index = 0
        self.phase_index = min(self.total_videos, self.phase_index + 1)
        self.video_name = Path(video_path).name
        self.analysis_step_offset = 0.0
        self.analysis_step_weight = 1.0
        self.detector_started = False
        self._emit(0, force=True)

    def _emit(self, video_percent: int, force: bool = False) -> None:
        if self.progress_callback is None:
            return
        completed_fraction = (self.phase_index - 1 + video_percent / 100.0) / self.total_videos
        overall_fraction = completed_fraction
        action = "Creating labeled" if self.phase == "labels" else "Analyzing"
        value = round(max(0.0, min(1.0, overall_fraction)) * DLC_PROGRESS_SCALE)
        if value < self.last_value:
            return
        if not force and value == self.last_value:
            return
        self.last_value = value
        message = f"{action} video {self.phase_index} of {self.total_videos}"
        if self.video_name:
            message += f": {self.video_name}"
        self.progress_callback(value, DLC_PROGRESS_SCALE, message)
