"""Background workers for gait-analysis preview and full runs."""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.gui.gait_analysis.settings import read_dlc_bodyparts
from dlc_gait_assembly.services.pipeline.alma import (
    AlmaSettings,
    AlmaViewCsvSet,
    run_alma_gait_analysis,
)


class StickPlotPreviewThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    preview_ready = Signal(object, str)
    preview_failed = Signal(str)

    def __init__(
        self,
        csv_files: tuple[tuple[str, Path], ...],
        settings: AlmaSettings,
        alma_root: Path,
    ):
        super().__init__()
        self._csv_files = tuple((label, Path(csv_file)) for label, csv_file in csv_files)
        self._settings = settings
        self._alma_root = alma_root

    def run(self) -> None:
        try:
            source_name = ", ".join(csv_file.name for _label, csv_file in self._csv_files)
            self.log_message.emit(f"Generating preview from {source_name}")

            def progress(index: int, total: int, message: str) -> None:
                value = 10 + int(index * 75 / max(1, total))
                self.progress_updated.emit(value, message)
                self.log_message.emit(message)

            temp_root = Path("/private/tmp") if Path("/private/tmp").is_dir() else None
            with tempfile.TemporaryDirectory(
                prefix="dlc-gait-stickplot-",
                dir=temp_root,
            ) as temp_dir:
                plots: list[tuple[str, bytes]] = []
                for input_index, (label, csv_file) in enumerate(self._csv_files, start=1):
                    side_mapping = None
                    if self._settings.view_bodypart_mapping:
                        side_mapping = self._settings.view_bodypart_mapping.get(label.lower())
                    side_settings = replace(
                        self._settings,
                        custom_bodypart_mapping=(
                            side_mapping or self._settings.custom_bodypart_mapping
                        ),
                        view_bodypart_mapping=None,
                    )

                    def side_progress(
                        index: int,
                        total: int,
                        message: str,
                        source_index: int = input_index,
                    ) -> None:
                        overall_index = ((source_index - 1) * max(1, total)) + index
                        overall_total = max(1, len(self._csv_files) * max(1, total))
                        progress(overall_index, overall_total, message)

                    results = run_alma_gait_analysis(
                        [csv_file],
                        Path(temp_dir),
                        side_settings,
                        self._alma_root,
                        progress_callback=side_progress,
                    )
                    for result in results:
                        for message in result.messages:
                            self.log_message.emit(message)
                    svg_path = next(
                        (
                            path
                            for result in results
                            for path in result.output_files
                            if path.suffix.lower() == ".svg" and path.exists()
                        ),
                        None,
                    )
                    if svg_path is not None:
                        plots.append((label, svg_path.read_bytes()))
                if not plots:
                    raise RuntimeError(
                        "ALMA did not find a valid stride for the stick plot. Check "
                        "body-part mapping, walking direction, calibration, and stride filters."
                    )
            self.preview_ready.emit(tuple(plots), source_name)
        except Exception as exc:
            csv_file = self._csv_files[0][1] if self._csv_files else Path("")
            self.preview_failed.emit(format_stickplot_failure(exc, csv_file, self._settings))


class AlmaAnalysisThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    analysis_completed = Signal(bool, str)

    def __init__(
        self,
        files: list[Path | AlmaViewCsvSet],
        output_folder: Path,
        settings: AlmaSettings,
        alma_root: Path,
    ):
        super().__init__()
        self._files = files
        self._output_folder = output_folder
        self._settings = settings
        self._alma_root = alma_root

    def run(self) -> None:
        try:
            self.log_message.emit(f"ALMA root: {self._alma_root}")
            self.log_message.emit(f"Output folder: {self._output_folder}")
            self.log_message.emit(f"Setup: {self._settings.analysis_type}")
            self.log_message.emit(f"Frame rate: {self._settings.frame_rate:g} fps")
            self.log_message.emit(f"Calibration method: {self._settings.calibration_method}")
            if self._settings.calibration_method == "manual":
                self.log_message.emit(f"Pixels per CM: {self._settings.pixels_per_cm:g}")
                if self._settings.calibration_map_path is not None:
                    self.log_message.emit(f"Calibration map: {self._settings.calibration_map_path}")
            if self._settings.custom_bodypart_mapping:
                self.log_message.emit(
                    f"Body part mapping: {self._settings.custom_bodypart_mapping}"
                )

            def progress(index: int, total: int, message: str) -> None:
                value = 10 + int((index - 1) * 80 / max(1, total))
                self.progress_updated.emit(value, message)
                self.log_message.emit(message)

            results = run_alma_gait_analysis(
                self._files,
                self._output_folder,
                self._settings,
                self._alma_root,
                progress_callback=progress,
            )
            for result in results:
                self.log_message.emit(f"{result.input_file.name}:")
                for output in result.output_files:
                    self.log_message.emit(f"  {output}")
                for message in result.messages:
                    self.log_message.emit(f"  {message}")
            self.progress_updated.emit(100, "ALMA gait analysis complete.")
            self.analysis_completed.emit(
                True,
                f"Analysis complete. Results saved to:\n{self._output_folder}",
            )
        except Exception as exc:
            self.analysis_completed.emit(False, str(exc))


def format_stickplot_failure(
    exc: Exception,
    csv_file: Path,
    settings: AlmaSettings,
) -> str:
    message = str(exc)
    try:
        bodyparts = ", ".join(read_dlc_bodyparts(csv_file))
    except Exception:
        bodyparts = "could not read body-part labels"
    hints = [
        f"Input CSV: {csv_file.name}",
        f"Detected body parts: {bodyparts}",
        f"Likelihood min: {settings.likelihood_threshold:.2f}",
        "Check Label matching for three-view sets, or the Mapping tab in single-side ALMA mode.",
        "If the confidence cutoff is too strict, lower Likelihood min or set it to 0.",
        "If no stride is found, try Auto-detect direction or relax stride height/length filters.",
    ]
    return message + "\n\n" + "\n".join(hints)
