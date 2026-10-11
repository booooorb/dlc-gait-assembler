"""Connect dataset pairing, knee settings, preview requests, and corrected-output execution."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog, QMessageBox

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_worker import KneeCorrectionThread
from dlc_gait_assembly.shared.client.qt_input_behaviors import animate_button_emphasis
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class KneeCorrectionController:
    """KneeCorrectionController operates on its explicitly supplied KneeCorrectionWidget view."""

    def __init__(self, view):
        self.view = view

    def _connect_signals(self) -> None:
        self.view.add_files_button.clicked.connect(self.view.inputs._choose_files)
        self.view.add_folder_button.clicked.connect(self.view.inputs._choose_folder)
        self.view.pair_table.itemSelectionChanged.connect(self.view.preview_controller._show_selected_preview)
        self.view.remove_button.clicked.connect(self.view.inputs._remove_selected)
        self.view.clear_button.clicked.connect(self.view.inputs._clear)
        self.view.output_folder_button.clicked.connect(self._choose_output_folder)
        self.view.output_folder_edit.textChanged.connect(self._update_run_state)
        self.view.calibration_map_button.clicked.connect(self._choose_calibration_map)
        self.view.previous_frame_button.clicked.connect(lambda: self.view.preview_controller._step_preview_frame(-1))
        self.view.next_frame_button.clicked.connect(lambda: self.view.preview_controller._step_preview_frame(1))
        self.view.preview_slider.valueChanged.connect(self.view.preview_controller._show_preview_frame)
        self.view.knee_label_combo.currentIndexChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.generated_knee_label_edit.textChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.hip_label_combo.currentIndexChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.ankle_label_combo.currentIndexChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.knee_direction_combo.currentIndexChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.hip_knee_length.valueChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.knee_ankle_length.valueChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.likelihood_threshold.valueChanged.connect(self.view.preview_controller._preview_inputs_changed)
        self.view.export_manifest_button.clicked.connect(self._export_manifest)
        self.view.run_button.clicked.connect(self._run)
        self.view.previous_frame_shortcut = QShortcut(QKeySequence(Qt.Key_Left), self.view.knee_preview)
        self.view.previous_frame_shortcut.setContext(Qt.WidgetShortcut)
        self.view.previous_frame_shortcut.activated.connect(
            lambda: self.view.preview_controller._step_preview_frame(-1)
        )
        self.view.next_frame_shortcut = QShortcut(QKeySequence(Qt.Key_Right), self.view.knee_preview)
        self.view.next_frame_shortcut.setContext(Qt.WidgetShortcut)
        self.view.next_frame_shortcut.activated.connect(lambda: self.view.preview_controller._step_preview_frame(1))

    def _choose_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self.view, "Choose corrected-label output folder", self.view.output_folder_edit.text()
        )
        if folder:
            self.view.output_folder_edit.setText(folder)

    def _choose_calibration_map(self) -> None:
        default_folder = self.view.workspace.manual / "calibration"
        (filename, _) = QFileDialog.getOpenFileName(
            self.view,
            "Import calibration conversion map",
            str(default_folder),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if filename:
            self._set_calibration_map(Path(filename))

    def _set_calibration_map(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        try:
            (pixels_per_cm, source) = self.view.use_cases.calibration_scale(resolved)
        except Exception as exc:
            QMessageBox.critical(self.view, "Could not import calibration map", str(exc))
            return False
        self.view.state.calibration_map_path = resolved
        self.view.state.pixels_per_cm = pixels_per_cm
        self.view.calibration_map_label.setText(f"{resolved.name} • {source}: {pixels_per_cm:.3f} px/cm")
        self.view.calibration_map_label.setToolTip(str(resolved))
        self.view.preview_controller._invalidate_preview()
        self._update_run_state()
        self.view.preview_controller._maybe_generate_previews()
        return True

    def _update_run_state(self) -> None:
        running = self.view._worker is not None and self.view._worker.isRunning()
        complete_pairs = bool(self.view.state.pairs) and all(pair.is_paired for pair in self.view.state.pairs)
        has_output = bool(self.view.output_folder_edit.text().strip())
        has_calibration = self.view.state.pixels_per_cm is not None
        self.view.run_button.setEnabled(complete_pairs and has_output and has_calibration and (not running))
        if not self.view.state.pairs:
            self.view.status_label.setText("Add matching CSV, H5, and video files.")
        elif not complete_pairs:
            self.view.status_label.setText("Red datasets are missing a matching CSV, H5, or video.")
        elif not has_calibration:
            self.view.status_label.setText("Import a calibration map to convert centimeters to pixels.")
        else:
            self.view.status_label.setText(
                f"{len(self.view.state.pairs)} paired dataset(s) ready • {self.view.state.pixels_per_cm:.3f} px/cm."
            )

    def _settings(self) -> KneeCorrectionSettings:
        selected_label = self.view.knee_label_combo.currentData()
        selected_hip = self.view.hip_label_combo.currentData()
        selected_ankle = self.view.ankle_label_combo.currentData()
        return KneeCorrectionSettings(
            hip_knee_length_cm=self.view.hip_knee_length.value(),
            knee_ankle_length_cm=self.view.knee_ankle_length.value(),
            pixels_per_cm=float(self.view.state.pixels_per_cm or 0),
            likelihood_threshold=self.view.likelihood_threshold.value(),
            knee_bodyparts=(str(selected_label),) if selected_label else None,
            hip_bodypart=str(selected_hip) if selected_hip else None,
            ankle_bodypart=str(selected_ankle) if selected_ankle else None,
            output_knee_bodypart=self.view.generated_knee_label_edit.text().strip() or "knee",
            knee_direction=str(self.view.knee_direction_combo.currentData() or "auto"),
        )

    def _export_manifest(self) -> None:
        if self.view.state.pixels_per_cm is None:
            QMessageBox.warning(
                self.view, "Calibration required", "Import a calibration map before exporting a knee analysis manifest."
            )
            return
        (destination, _) = QFileDialog.getSaveFileName(
            self.view,
            "Export knee analysis manifest",
            str(self.view._default_output_folder() / "knee_analysis_manifest.json"),
            "Knee analysis manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if not destination:
            return
        path = Path(destination).expanduser()
        if not path.suffix:
            path = path.with_suffix(".json")
        try:
            saved = self.view.use_cases.save_settings(path, self._settings())
        except OSError as exc:
            QMessageBox.critical(self.view, "Could not export knee analysis manifest", str(exc))
            return
        self.view.state.profile_knee_manifest_path = Path(saved).expanduser().resolve()
        self.view.log.appendPlainText(f"[Manifest] Exported {saved}")
        QMessageBox.information(self.view, "Knee analysis manifest exported", f"Saved:\n{saved}")

    def _run(self) -> None:
        if not self.view.state.pairs or not all(pair.is_paired for pair in self.view.state.pairs):
            QMessageBox.warning(self.view, "Pairs required", "Pair every CSV with one matching H5 and video file.")
            return
        if self.view.state.pixels_per_cm is None:
            QMessageBox.warning(
                self.view, "Calibration required", "Import a calibration map before correcting knee labels."
            )
            return
        output_folder = Path(self.view.output_folder_edit.text()).expanduser().resolve()
        existing = self.view.use_cases.existing_outputs(output_folder, self.view.state.pairs)
        if (
            existing
            and QMessageBox.question(
                self.view,
                "Replace corrected outputs?",
                "Corrected output files already exist and will be replaced. Keep a backup. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.view.progress.setValue(0)
        self.view.progress.set_active(True)
        self.view.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        animate_button_emphasis(self.view.run_button, True)
        self.view.log.clear()
        self.view._worker = KneeCorrectionThread(
            tuple(self.view.state.pairs), output_folder, self._settings(), use_cases=self.view.use_cases
        )
        self.view._worker.progress_updated.connect(self._progress_updated)
        self.view._worker.completed.connect(self._completed)
        self.view._worker.finished.connect(self._worker_finished)
        self.view._worker.start()
        self._update_run_state()

    def _progress_updated(self, value: int, message: str) -> None:
        self.view.progress.setValue(value)
        self.view.status_label.setText(message)
        self.view.log.appendPlainText(message)

    def _completed(self, success: bool, message: str) -> None:
        self.view.status_label.setText(message)
        self.view.progress.set_active(False)
        animate_button_emphasis(self.view.run_button, False)
        if success:
            self.view.progress.setValue(100)
            self.view.run_button.setIcon(interface_icon("check", theme.PRIMARY_TEXT))
            QMessageBox.information(self.view, "Knee correction complete", message)
        else:
            self.view.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
            QMessageBox.critical(self.view, "Knee correction failed", message)

    def _worker_finished(self) -> None:
        self.view._worker = None
        self.view.progress.set_active(False)
        self._update_run_state()
