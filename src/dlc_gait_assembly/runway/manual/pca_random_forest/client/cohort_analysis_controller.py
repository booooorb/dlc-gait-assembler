"""Coordinate cohort selection, analysis requests, progress, and returned results."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_worker import CohortAnalysisThread


class CohortAnalysisController:
    """CohortAnalysisController operates on its explicitly supplied PcaRandomForestWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self.view, "Select cohort-analysis output folder", self.view.output_edit.text()
        )
        if selected:
            self.view.output_edit.setText(selected)

    def _run_analysis(self) -> None:
        if not self.view._files:
            return
        if not any(
            (
                self.view.pca_checkbox.isChecked(),
                self.view.random_forest_checkbox.isChecked(),
                self.view.mixed_effects_checkbox.isChecked(),
            )
        ):
            QMessageBox.warning(self.view, "No analysis selected", "Select at least one analysis.")
            return
        output_folder = Path(self.view.output_edit.text()).expanduser().resolve()
        self.view.log.clear()
        self.view.status_label.setText("Running animal-grouped cohort analysis...")
        self.view.run_button.setEnabled(False)
        self.view._worker = CohortAnalysisThread(
            self.view._files,
            output_folder,
            self.view.pca_checkbox.isChecked(),
            self.view.random_forest_checkbox.isChecked(),
            self.view.mixed_effects_checkbox.isChecked(),
            outputs=self.view.outputs,
        )
        self.view._worker.log_message.connect(self.view.log.append)
        self.view._worker.completed.connect(self._analysis_completed)
        self.view._worker.finished.connect(self._worker_finished)
        self.view._worker.start()

    def _analysis_completed(self, success: bool, message: str) -> None:
        self.view.status_label.setText("Analysis complete." if success else "Analysis failed.")
        if success:
            QMessageBox.information(self.view, "Cohort analysis complete", message)
        else:
            self.view.log.append(message)
            QMessageBox.critical(self.view, "Cohort analysis failed", message)

    def _worker_finished(self) -> None:
        if self.view._worker is not None:
            self.view._worker.deleteLater()
            self.view._worker = None
        self._update_run_state()

    def _update_run_state(self) -> None:
        running = self.view._worker is not None and self.view._worker.isRunning()
        self.view.run_button.setEnabled(bool(self.view._files) and (not running))
        if not running and self.view._files:
            self.view.status_label.setText(f"Ready: {len(self.view._files)} animal-session summary file(s).")
