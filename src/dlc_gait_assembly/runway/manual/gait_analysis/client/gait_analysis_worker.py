"""Bridge ALMA and standalone RustLab1 analysis progress, outputs, and errors into Qt signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)


class AlmaAnalysisThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    results_ready = Signal(object)
    analysis_completed = Signal(bool, str)

    def __init__(self, files: list[Path | AlmaViewCsvSet], output_folder: Path, settings: AlmaSettings, *, analyze):
        super().__init__()
        self.setStackSize(8 * 1024 * 1024)
        self.analyze = analyze
        self._files = files
        self._output_folder = output_folder
        self._settings = settings

    def run(self) -> None:
        try:
            self.log_message.emit(f"Output folder: {self._output_folder}")
            self.log_message.emit(f"Setup: {self._settings.analysis_type}")
            self.log_message.emit(f"Frame rate: {self._settings.frame_rate:g} fps")
            self.log_message.emit(f"Calibration method: {self._settings.calibration_method}")
            if self._settings.calibration_method == "manual":
                self.log_message.emit(
                    f"Pixels per CM: {self._settings.pixels_per_cm if self._settings.pixels_per_cm is not None else 'from calibration map'}"
                )
                if self._settings.calibration_map_path is not None:
                    self.log_message.emit(f"Calibration map: {self._settings.calibration_map_path}")
            if self._settings.custom_bodypart_mapping:
                self.log_message.emit(f"Body part mapping: {self._settings.custom_bodypart_mapping}")

            def progress(index: int, total: int, message: str) -> None:
                value = 10 + int((index - 1) * 80 / max(1, total))
                self.progress_updated.emit(value, message)
                self.log_message.emit(message)

            results = self.analyze(self._files, self._output_folder, self._settings, progress_callback=progress)
            for result in results:
                self.log_message.emit(f"{result.input_file.name}:")
                for output in result.output_files:
                    self.log_message.emit(f"  {output}")
                for message in result.messages:
                    self.log_message.emit(f"  {message}")
            self.results_ready.emit(tuple(results))
            self.progress_updated.emit(100, "ALMA gait analysis complete.")
            self.analysis_completed.emit(True, f"Analysis complete. Results saved to:\n{self._output_folder}")
        except Exception as exc:
            self.analysis_completed.emit(False, str(exc))


class RustLab1AnalysisThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    results_ready = Signal(object)
    analysis_completed = Signal(bool, str)

    def __init__(
        self, view_sets: list[AlmaViewCsvSet], output_folder: Path, settings: RustLab1StandaloneSettings, *, analyze
    ):
        super().__init__()
        self.setStackSize(8 * 1024 * 1024)
        self.analyze = analyze
        self._view_sets = list(view_sets)
        self._output_folder = Path(output_folder)
        self._settings = settings

    def run(self) -> None:
        try:
            self.log_message.emit("Workflow: standalone RustLab1 three-view analysis")
            self.log_message.emit(f"Output folder: {self._output_folder}")
            self.log_message.emit(f"Reference paw: {self._settings.reference_paw}")
            self.log_message.emit(f"Stance threshold: {self._settings.stance_speed_threshold_px_frame:g} px/frame")
            self.log_message.emit(
                f"Tracking-speed QC maximum: {self._settings.maximum_tracking_speed_px_frame:g} px/frame"
            )
            self.log_message.emit(f"Minimum complete strides: {self._settings.minimum_complete_strides}")

            def progress(index: int, total: int, message: str) -> None:
                value = 10 + int((index - 1) * 80 / max(1, total))
                self.progress_updated.emit(value, message)
                self.log_message.emit(message)

            results = self.analyze(self._view_sets, self._output_folder, self._settings, progress_callback=progress)
            for result in results:
                self.log_message.emit(f"{result.input_file.name}:")
                for output in result.output_files:
                    self.log_message.emit(f"  {output}")
                for message in result.messages:
                    self.log_message.emit(f"  {message}")
            self.results_ready.emit(tuple(results))
            self.progress_updated.emit(100, "RustLab1 analysis complete.")
            self.analysis_completed.emit(True, f"RustLab1 analysis complete. Results saved to:\n{self._output_folder}")
        except Exception as exc:
            self.analysis_completed.emit(False, str(exc))
