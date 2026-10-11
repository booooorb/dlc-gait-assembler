"""Connect detection requests, event selection, review edits, and Ladder export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import (
    DualLadderRunResult,
    LadderRunResult,
    LadderSettings,
)
from dlc_gait_assembly.ladder.client.ladder_detection_worker import DualLadderAnalysisThread, LadderAnalysisThread


class LadderAnalysisController:
    """LadderAnalysisController operates on its explicitly supplied LadderAnalysisWidget view."""

    def __init__(self, view):
        self.view = view

    def _connect_signals(self) -> None:
        self.view.mode_combo.currentTextChanged.connect(self._update_mode)
        self.view.csv_button.clicked.connect(self.view.inputs._choose_csv)
        self.view.right_csv_button.clicked.connect(self.view.inputs._choose_right_csv)
        self.view.video_button.clicked.connect(self.view.inputs._choose_video)
        self.view.right_video_button.clicked.connect(self.view.inputs._choose_right_video)
        self.view.output_button.clicked.connect(self._choose_output)
        self.view.method_combo.currentTextChanged.connect(self._update_method_controls)
        self.view.auto_threshold_checkbox.toggled.connect(self._update_method_controls)
        self.view.right_method_combo.currentTextChanged.connect(self._update_method_controls)
        self.view.right_auto_threshold_checkbox.toggled.connect(self._update_method_controls)
        self.view.run_button.clicked.connect(self._run_detection)
        self.view.events_table.currentCellChanged.connect(self.view.review._event_selected)
        self.view.frame_slider.valueChanged.connect(self.view.video_review._show_video_frame)
        self.view.save_button.clicked.connect(self.view.review._save_reviewed_results)
        self.view.output_edit.textChanged.connect(self._update_run_state)

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self.view, "Choose ladder output folder", self.view.output_edit.text()
        )
        if directory:
            self.view.output_edit.setText(directory)

    def _selected_bodyparts(self, view: str = "single") -> list[str]:
        bodyparts_list = self.view.right_bodyparts_list if view == "right" else self.view.bodyparts_list
        return [
            bodyparts_list.item(index).text()
            for index in range(bodyparts_list.count())
            if bodyparts_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _settings(self, view: str = "single") -> LadderSettings:
        if view == "right":
            return LadderSettings(
                method=self.view.right_method_combo.currentText(),
                frame_rate=self.view.right_frame_rate_spin.value(),
                likelihood_threshold=self.view.right_likelihood_spin.value(),
                depth_threshold=self.view.right_depth_spin.value(),
                threshold=None
                if self.view.right_auto_threshold_checkbox.isChecked()
                else self.view.right_threshold_spin.value(),
            )
        return LadderSettings(
            method=self.view.method_combo.currentText(),
            frame_rate=self.view.frame_rate_spin.value(),
            likelihood_threshold=self.view.likelihood_spin.value(),
            depth_threshold=self.view.depth_spin.value(),
            threshold=None if self.view.auto_threshold_checkbox.isChecked() else self.view.threshold_spin.value(),
        )

    def _run_detection(self) -> None:
        if self.view.state.csv_path is None:
            return
        left_bodyparts = self._selected_bodyparts("left")
        if self._is_dual_mode():
            right_bodyparts = self._selected_bodyparts("right")
            if self.view.state.right_csv_path is None:
                QMessageBox.information(self.view, "Right CSV required", "Choose the right-camera coordinate CSV.")
                return
            if len(left_bodyparts) != 2 or len(right_bodyparts) != 2:
                QMessageBox.information(
                    self.view,
                    "Select two paws per camera",
                    "Paired mode requires exactly two markers from the left CSV and two from the right CSV (front and hind paw).",
                )
                return
        elif not left_bodyparts:
            QMessageBox.information(self.view, "No paw markers selected", "Select at least one body part to analyze.")
            return
        output_folder = Path(self.view.output_edit.text()).expanduser().resolve()
        self.view.progress.setRange(0, 0)
        self.view.progress.set_active(True)
        if self._is_dual_mode():
            self.view.status_label.setText("Running paired left/right ALMA ladder detection…")
            self.view._worker = DualLadderAnalysisThread(
                self.view.state.csv_path,
                self.view.state.right_csv_path,
                output_folder,
                self._settings("left"),
                self._settings("right"),
                left_bodyparts,
                right_bodyparts,
                use_cases=self.view.use_cases,
            )
        else:
            self.view.status_label.setText("Running ALMA ladder-rung detection…")
            self.view._worker = LadderAnalysisThread(
                self.view.state.csv_path, output_folder, self._settings(), left_bodyparts, use_cases=self.view.use_cases
            )
        self.view._worker.completed.connect(self._detection_completed)
        self.view._worker.failed.connect(self._detection_failed)
        self.view._worker.finished.connect(self._worker_finished)
        self.view._worker.start()
        self._update_run_state()

    def _detection_completed(self, result: LadderRunResult | DualLadderRunResult) -> None:
        self.view.state.events = list(result.events)
        self.view.review._populate_event_table()
        self.view.progress.setRange(0, 100)
        self.view.progress.set_active(False)
        self.view.progress.setValue(100)
        self.view.status_label.setText(
            f"Detected {len(self.view.state.events)} event(s). {('Combined' if isinstance(result, DualLadderRunResult) else 'Raw ALMA')} output: {result.output_file.name}"
        )
        self.view.save_button.setEnabled(bool(self.view.state.events))
        if self.view.state.events:
            self.view.events_table.selectRow(0)

    def _detection_failed(self, message: str) -> None:
        self.view.progress.setRange(0, 100)
        self.view.progress.set_active(False)
        self.view.status_label.setText("Ladder detection failed.")
        QMessageBox.critical(self.view, "ALMA ladder analysis failed", message)

    def _worker_finished(self) -> None:
        self.view._worker = None
        self.view.progress.set_active(False)
        self._update_run_state()

    def _is_dual_mode(self) -> bool:
        return self.view.mode_combo.currentText() == "Paired left + right cameras"

    def _update_mode(self) -> None:
        dual = self._is_dual_mode()
        for widget in (
            self.view.right_csv_label,
            self.view.right_csv_edit,
            self.view.right_csv_button,
            self.view.right_video_label,
            self.view.right_video_edit,
            self.view.right_video_button,
        ):
            widget.setVisible(dual)
        self.view.settings_tabs.setTabVisible(1, dual)
        self.view.bodyparts_tabs.setTabVisible(1, dual)
        self.view.settings_tabs.setTabText(0, "Left camera" if dual else "Camera")
        self.view.bodyparts_tabs.setTabText(0, "Left camera" if dual else "Camera")
        self.view.left_csv_label.setText("Left coordinates" if dual else "Coordinates")
        self.view.left_video_label.setText("Left review video" if dual else "Review video")
        self.view.csv_button.setText("Choose left CSV…" if dual else "Choose DLC CSV…")
        self.view.video_button.setText("Choose left video…" if dual else "Choose video…")
        self.view.run_button.setText("Run paired ALMA ladder detection" if dual else "Run ALMA ladder detection")
        if dual:
            self.view.status_label.setText(
                "Choose left and right CSVs, then select exactly two paw markers in each tab."
            )
        elif self.view.state.csv_path is None:
            self.view.status_label.setText("Choose a DeepLabCut coordinate CSV to begin.")
        self._update_run_state()

    def _update_method_controls(self) -> None:
        threshold_method = self.view.method_combo.currentText() == "Threshold"
        self.view.auto_threshold_checkbox.setEnabled(threshold_method)
        self.view.threshold_spin.setEnabled(threshold_method and (not self.view.auto_threshold_checkbox.isChecked()))
        right_threshold_method = self.view.right_method_combo.currentText() == "Threshold"
        self.view.right_auto_threshold_checkbox.setEnabled(right_threshold_method)
        self.view.right_threshold_spin.setEnabled(
            right_threshold_method and (not self.view.right_auto_threshold_checkbox.isChecked())
        )

    def _update_run_state(self) -> None:
        running = self.view._worker is not None and self.view._worker.isRunning()
        has_inputs = self.view.state.csv_path is not None and (
            not self._is_dual_mode() or self.view.state.right_csv_path is not None
        )
        self.view.run_button.setEnabled(has_inputs and bool(self.view.output_edit.text().strip()) and (not running))
