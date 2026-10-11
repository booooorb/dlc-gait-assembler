"""Bridge scientific stickplot and parameter-figure preparation into Qt signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)


class ScientificPreviewThread(QThread):
    def __init__(self):
        super().__init__()
        # NumPy/Matplotlib native routines exceed macOS's default worker stack.
        self.setStackSize(8 * 1024 * 1024)


class StickPlotPreviewThread(ScientificPreviewThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    preview_ready = Signal(object, str)
    preview_failed = Signal(str)

    def __init__(self, csv_files: tuple[tuple[str, Path], ...], settings: AlmaSettings, *, preview):
        super().__init__()
        self._csv_files = tuple((label, Path(csv_file)) for (label, csv_file) in csv_files)
        self._settings = settings
        self._preview = preview

    def run(self) -> None:
        try:

            def progress(index, total, message):
                self.progress_updated.emit(10 + int(index * 75 / max(1, total)), message)
                self.log_message.emit(message)

            (plots, source, messages) = self._preview.prepare(self._csv_files, self._settings, progress)
            for message in messages:
                self.log_message.emit(message)
            self.preview_ready.emit(plots, source)
        except Exception as exc:
            self.preview_failed.emit(str(exc))


class RustLab1PreviewThread(ScientificPreviewThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    preview_ready = Signal(object, str)
    preview_failed = Signal(str)

    def __init__(self, view_set: AlmaViewCsvSet, settings: RustLab1StandaloneSettings, *, preview):
        super().__init__()
        self.preview = preview
        self._view_set = view_set
        self._settings = settings

    def run(self) -> None:
        try:
            self.progress_updated.emit(10, f"RustLab1: detecting strides for {self._view_set.name}")
            (plots, source, messages) = self.preview.prepare_rustlab1(self._view_set, self._settings)
            for message in messages:
                self.log_message.emit(message)
            self.preview_ready.emit(plots, source)
        except Exception as exc:
            self.preview_failed.emit(str(exc))


class StrideComparisonThread(ScientificPreviewThread):
    progress_updated = Signal(int, str)
    comparison_ready = Signal(object)
    preview_failed = Signal(str)

    def __init__(self, inputs, settings, *, preview):
        super().__init__()
        self.inputs, self.settings, self.preview = inputs, settings, preview

    def run(self):
        try:

            def progress(index, total, message):
                self.progress_updated.emit(int(100 * index / total), message)

            self.comparison_ready.emit(self.preview.compare(self.inputs, self.settings, progress))
        except Exception as exc:
            self.preview_failed.emit(str(exc))


class ParameterFiguresThread(ScientificPreviewThread):
    """Render complete parameter pages without blocking the Qt event loop."""

    progress_updated = Signal(int, str)
    figures_ready = Signal(object)
    figures_failed = Signal(str)

    def __init__(self, path, *, reader):
        super().__init__()
        self.path = path
        self.reader = reader

    def run(self):
        try:

            def progress(index, total):
                self.progress_updated.emit(
                    int(100 * (index - 1) / total), f"Rendering parameter figures {index} of {total}…"
                )

            self.figures_ready.emit(self.reader.parameter_figures(self.path, progress))
        except Exception as exc:
            self.figures_failed.emit(str(exc))
