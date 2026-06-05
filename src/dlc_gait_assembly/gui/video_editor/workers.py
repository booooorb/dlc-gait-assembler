from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.services.domain.trimming import TrimRange
from dlc_gait_assembly.services.video_processing import ProcessingOptions, process_video_outputs


class VideoProcessingThread(QThread):
    file_started = Signal(int, int, str)
    file_finished = Signal(str, object)
    file_failed = Signal(str, str)
    completed = Signal(str)

    def __init__(
        self,
        video_paths: list[Path],
        session_dir: Path,
        options: ProcessingOptions,
        trim_ranges_by_path: dict[str, tuple[TrimRange, ...]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._video_paths = video_paths
        self._session_dir = session_dir
        self._options = options
        self._trim_ranges_by_path = trim_ranges_by_path or {}

    def run(self) -> None:
        total = len(self._video_paths)
        for index, path in enumerate(self._video_paths, start=1):
            self.file_started.emit(index, total, path.name)
            try:
                options = replace(self._options, trim_ranges=self._trim_ranges_by_path.get(str(path), ()))
                results = process_video_outputs(path, self._session_dir, options)
            except Exception as exc:
                self.file_failed.emit(str(path), str(exc))
            else:
                self.file_finished.emit(str(path), [str(result.output_path) for result in results])

        self.completed.emit(str(self._session_dir))
