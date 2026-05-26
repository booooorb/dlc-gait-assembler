from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.services.ffmpeg import ProcessingOptions, process_video


class VideoProcessingThread(QThread):
    file_started = Signal(int, int, str)
    file_finished = Signal(str, str)
    file_failed = Signal(str, str)
    completed = Signal(str)

    def __init__(self, video_paths: list[Path], session_dir: Path, options: ProcessingOptions, parent=None):
        super().__init__(parent)
        self._video_paths = video_paths
        self._session_dir = session_dir
        self._options = options

    def run(self) -> None:
        total = len(self._video_paths)
        for index, path in enumerate(self._video_paths, start=1):
            self.file_started.emit(index, total, path.name)
            try:
                result = process_video(path, self._session_dir, self._options)
            except Exception as exc:
                self.file_failed.emit(str(path), str(exc))
            else:
                self.file_finished.emit(str(path), str(result.output_path))

        self.completed.emit(str(self._session_dir))
