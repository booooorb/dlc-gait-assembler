"""Bridge cohort analysis messages, errors, and completion into Qt signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_use_cases import (
    run_stroke_cohort_analysis,
)


class CohortAnalysisThread(QThread):
    completed = Signal(bool, str)
    log_message = Signal(str)

    def __init__(self, files, output_folder, run_pca, run_random_forest, run_mixed_effects, *, outputs):
        super().__init__()
        self.setStackSize(8 * 1024 * 1024)
        self.outputs = outputs
        self._files = tuple(files)
        self._output_folder = Path(output_folder)
        self._run_pca = run_pca
        self._run_random_forest = run_random_forest
        self._run_mixed_effects = run_mixed_effects

    def run(self) -> None:
        try:
            result = run_stroke_cohort_analysis(
                self._files,
                self._output_folder,
                run_pca=self._run_pca,
                run_random_forest=self._run_random_forest,
                run_mixed_effects=self._run_mixed_effects,
                outputs=self.outputs,
            )
            for message in result.messages:
                self.log_message.emit(message)
            for path in result.output_files:
                self.log_message.emit(str(path))
            self.completed.emit(True, f"Analysis complete. Results saved to:\n{self._output_folder}")
        except Exception as exc:
            self.completed.emit(False, str(exc))
