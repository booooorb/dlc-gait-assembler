"""Bridge single/dual-view Ladder execution, errors, and results into Qt signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderSettings
from dlc_gait_assembly.ladder.business.ladder_dual_view_analysis import run_dual_view_ladder_analysis


class LadderAnalysisThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self, csv_file: Path, output_folder: Path, settings: LadderSettings, bodyparts: list[str], *, use_cases
    ):
        super().__init__()
        self.setStackSize(8 * 1024 * 1024)
        self.use_cases = use_cases
        self._csv_file = csv_file
        self._output_folder = output_folder
        self._settings = settings
        self._bodyparts = bodyparts

    def run(self) -> None:
        try:
            result = self.use_cases.run(self._csv_file, self._output_folder, self._settings, self._bodyparts)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)


class DualLadderAnalysisThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        left_csv_file: Path,
        right_csv_file: Path,
        output_folder: Path,
        left_settings: LadderSettings,
        right_settings: LadderSettings,
        left_bodyparts: list[str],
        right_bodyparts: list[str],
        *,
        use_cases,
    ):
        super().__init__()
        self.setStackSize(8 * 1024 * 1024)
        self.use_cases = use_cases
        self._left_csv_file = left_csv_file
        self._right_csv_file = right_csv_file
        self._output_folder = output_folder
        self._left_settings = left_settings
        self._right_settings = right_settings
        self._left_bodyparts = left_bodyparts
        self._right_bodyparts = right_bodyparts

    def run(self) -> None:
        try:
            result = run_dual_view_ladder_analysis(
                self._left_csv_file,
                self._right_csv_file,
                self._output_folder,
                self._left_settings,
                self._right_settings,
                self._left_bodyparts,
                self._right_bodyparts,
                use_cases=self.use_cases,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)
