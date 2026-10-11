"""Connect reference-media selection, measurement edits, assessments, and calibration exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox, QToolButton

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick
from dlc_gait_assembly.runway.manual.calibration.client.calibration_results_panel import (
    failed_location_marker_indices,
    report_to_html,
    stick_key,
)
from dlc_gait_assembly.shared.client.qt_input_behaviors import add_shortcut, animate_button_emphasis


class CalibrationController:
    """CalibrationController operates on its explicitly supplied ManualCalibrationWidget view."""

    def __init__(self, view):
        self.view = view

    def _install_shortcuts(self) -> None:
        self.view._shortcuts = [
            add_shortcut(self.view, "Ctrl+O", self.view.media_panel._open_media),
            add_shortcut(self.view, "Ctrl+Backspace", self.view.media_panel._remove_selected_media),
            add_shortcut(self.view, "Ctrl+L", self._clear_calibration),
            add_shortcut(self.view, "Ctrl+1", lambda: self._activate_tool_button(self.view.x_tool_button, "x")),
            add_shortcut(self.view, "Ctrl+2", lambda: self._activate_tool_button(self.view.y_tool_button, "y")),
            add_shortcut(self.view, "Ctrl+3", lambda: self._activate_tool_button(self.view.cm_tool_button, "cm")),
            add_shortcut(self.view, "Ctrl+E", self.view.euclidean_lengths_checkbox.toggle),
        ]

    def _connect_signals(self) -> None:
        self.view.open_media_button.clicked.connect(self.view.media_panel._open_media)
        self.view.remove_media_button.clicked.connect(self.view.media_panel._remove_selected_media)
        self.view.clear_calibration_button.clicked.connect(self._clear_calibration)
        self.view.media_list.currentItemChanged.connect(self.view.media_panel._media_selection_changed)
        self.view.x_tool_button.clicked.connect(lambda: self._set_active_tool("x"))
        self.view.y_tool_button.clicked.connect(lambda: self._set_active_tool("y"))
        self.view.cm_tool_button.clicked.connect(lambda: self._set_active_tool("cm"))
        self.view.tau_spin.valueChanged.connect(self._update_calibration_results)
        self.view.euclidean_lengths_checkbox.toggled.connect(self._update_calibration_results)
        self.view.marker_interval_spin.valueChanged.connect(self._update_calibration_results)
        self.view.marker_unit_combo.currentTextChanged.connect(self._update_calibration_results)
        self.view.preview.sticks_changed.connect(self._on_preview_sticks_changed)
        self.view.preview.stick_delete_requested.connect(self._confirm_delete_calibration_stick)
        self.view.timeline.valueChanged.connect(self.view.media_panel._timeline_changed)
        self.view.timeline.sliderReleased.connect(self.view.media_panel._flush_pending_frame)
        self.view.export_conversion_button.clicked.connect(self._export_conversion_map)

    def _clear_calibration(self) -> None:
        if not self.view.preview.calibration_sticks():
            return
        if (
            QMessageBox.question(
                self.view,
                "Clear calibration?",
                "Remove all calibration sticks and markers from this frame?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.view.preview.clear_calibration()
        if self.view.state.current_media is not None:
            self.view.state.calibration_sticks_by_media[str(self.view.state.current_media)] = ()

    def _confirm_delete_calibration_stick(self, key: str, label: str) -> None:
        if (
            QMessageBox.question(
                self.view,
                "Delete calibration stick?",
                f"Delete {label} and all of its markers?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.view.preview.delete_stick(key)

    def _set_active_tool(self, name: str) -> None:
        self.view.preview.set_mode(name)
        self._emphasize_calibration_tool(name)

    def _emphasize_calibration_tool(self, active_name: str) -> None:
        for name, button in (
            ("x", self.view.x_tool_button),
            ("y", self.view.y_tool_button),
            ("cm", self.view.cm_tool_button),
        ):
            animate_button_emphasis(button, name == active_name, resting_height=30, emphasized_height=40)

    def _activate_tool_button(self, button: QToolButton, name: str) -> None:
        button.setChecked(True)
        self._set_active_tool(name)

    def _on_preview_sticks_changed(self) -> None:
        if self.view.state.loading_media:
            return
        self._save_media_state()
        self._update_calibration_results()
        self.view.media_panel._update_media_summary()

    def _update_calibration_results(self) -> None:
        sticks = self._all_calibration_sticks() if hasattr(self.view, "preview") else []
        report = self.view.use_cases.assess(
            sticks,
            self.view.tau_spin.value() if hasattr(self.view, "tau_spin") else 2.0,
            self.view.euclidean_lengths_checkbox.isChecked()
            if hasattr(self.view, "euclidean_lengths_checkbox")
            else False,
            self.view.marker_interval_spin.value() if hasattr(self.view, "marker_interval_spin") else 1.0,
            self.view.marker_unit_combo.currentText() if hasattr(self.view, "marker_unit_combo") else "cm",
        )
        if hasattr(self.view, "preview") and (not self.view.state.loading_media):
            self._update_location_failure_highlights(report)
        self.view.results_label.setText(report_to_html(report))
        if hasattr(self.view, "export_conversion_button"):
            self.view.export_conversion_button.setEnabled(bool(report.view_axis))

    def _export_conversion_map(self) -> None:
        sticks = self._all_calibration_sticks()
        report = self.view.use_cases.assess(
            sticks,
            self.view.tau_spin.value(),
            self.view.euclidean_lengths_checkbox.isChecked(),
            self.view.marker_interval_spin.value(),
            self.view.marker_unit_combo.currentText(),
        )
        if not report.view_axis:
            QMessageBox.information(
                self.view, "No calibration data", "Create calibration sticks before exporting a conversion map."
            )
            return
        output_root = self.view._default_output_root()
        directory = QFileDialog.getExistingDirectory(self.view, "Choose calibration output folder", str(output_root))
        if not directory:
            return
        try:
            paths = self.view.use_cases.export_session(directory, sticks, report)
            session_dir = paths["map"].parent
        except Exception as exc:
            QMessageBox.critical(self.view, "Export failed", str(exc))
            return
        self.view.state.profile_calibration_map_path = Path(paths["map"]).expanduser().resolve()
        QMessageBox.information(
            self.view,
            "Conversion map exported",
            f"Output folder:\n{session_dir}\n\nMap:\n{paths['map'].name}\nReport:\n{paths['report'].name}",
        )

    def _save_media_state(self, item: QListWidgetItem | None = None) -> None:
        if self.view.state.loading_media or not hasattr(self.view, "preview"):
            return
        path_key = (
            item.data(Qt.UserRole)
            if item is not None
            else str(self.view.state.current_media)
            if self.view.state.current_media is not None
            else None
        )
        if not path_key:
            return
        self.view.state.calibration_sticks_by_media[path_key] = tuple(self.view.preview.calibration_sticks())
        if self.view._capture is not None:
            self.view.state.timeline_ms_by_media[path_key] = int(self.view.timeline.value())

    def _all_calibration_sticks(self) -> list[CalibrationStick]:
        if not self.view.state.loading_media:
            self._save_media_state()
        sticks = []
        for index in range(self.view.media_list.count()):
            item = self.view.media_list.item(index)
            sticks.extend(self.view.state.calibration_sticks_by_media.get(item.data(Qt.UserRole), ()))
        return sticks

    def _update_location_failure_highlights(self, report: CalibrationReport) -> None:
        if self.view.state.current_media is None:
            self.view.preview.set_location_failure_markers({})
            return
        stats_by_stick = {(stat.view_index, stat.axis): stat for stat in report.view_axis}
        markers_by_stick: dict[str, set[int]] = {}
        tau_percent = self.view.tau_spin.value()
        use_euclidean = self.view.euclidean_lengths_checkbox.isChecked()
        centimeters_per_marker_interval = self.view.marker_interval_spin.value() * (
            2.54 if self.view.marker_unit_combo.currentText().lower().startswith("inch") else 1.0
        )
        for stick in self.view.preview.calibration_sticks():
            stat = stats_by_stick.get((stick.view_index, stick.axis))
            if stat is None or stat.location_passed is not False or stat.mean_conversion_factor is None:
                continue
            failed_markers = failed_location_marker_indices(
                stick, stat.mean_conversion_factor, tau_percent, use_euclidean, centimeters_per_marker_interval
            )
            if failed_markers:
                markers_by_stick[stick_key(stick.axis, stick.view_index)] = failed_markers
        self.view.preview.set_location_failure_markers(markers_by_stick)
