"""Select analysis output destinations, figure options, and reusable settings exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitOutputPanel:
    """GaitOutputPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _select_output_folder(self) -> None:
        title = "Choose folder for analysis results"
        directory = QFileDialog.getExistingDirectory(self.view, title, self.view.output_folder_edit.text())
        if directory:
            self.view.output_folder_edit.setText(directory)
            self.view.controller._update_run_state()

    def _export_analysis_manifest(self) -> None:
        output_text = self.view.output_folder_edit.text().strip()
        output_folder = Path(output_text).expanduser() if output_text else self.view._default_output_root()
        (filename, _) = QFileDialog.getSaveFileName(
            self.view,
            "Export gait analysis manifest",
            str(output_folder / "analysis_manifest.json"),
            "Analysis manifest (analysis_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")
        try:
            exported = self.view.analysis.settings.write(destination, self.view.setup._collect_settings())
        except OSError as exc:
            QMessageBox.critical(self.view, "Could not export analysis manifest", str(exc))
            return
        self.view.state.profile_analysis_manifest_path = Path(exported).expanduser().resolve()
        self.view.status_label.setText("Analysis manifest exported.")
        self.view.controller._append_log(f"Analysis manifest exported to {exported}")
        QMessageBox.information(
            self.view, "Analysis manifest exported", f"Saved the current gait-analysis settings to:\n{exported}"
        )

    def _import_analysis_manifest(self) -> None:
        if self.view.controller._processing_running():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.view,
            "Import gait analysis manifest",
            self.view.output_folder_edit.text(),
            "Gait analysis manifest (*.json)",
        )
        if not filename:
            return
        from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_manifest_import import (
            apply_manifest_settings,
        )

        try:
            settings = self.view.analysis.settings.load_settings(filename)
            apply_manifest_settings(self.view, settings)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            QMessageBox.warning(self.view, "Could not import analysis manifest", str(exc))
            return
        self.view.state.profile_analysis_manifest_path = Path(filename).expanduser().resolve()
        self.view.status_label.setText(f"Imported {Path(filename).name}. Generate a new stick-plot preview.")
        self.view.controller._append_log(
            f"Analysis settings imported from {filename}. Input CSVs and output folder retained."
        )


def build_gait_output_settings(self, output_tab_layout):
    destination_box = QGroupBox("Save results to")
    destination_layout = QGridLayout(destination_box)
    self.export_folder_edit = QLineEdit(self.output_folder_edit.text())
    self.export_folder_edit.setPlaceholderText("Choose a folder for the CSV and figures")
    self.export_folder_button = QPushButton("Choose folder…")
    self.export_folder_button.clicked.connect(self.outputs._select_output_folder)
    self.export_folder_edit.textChanged.connect(self.output_folder_edit.setText)
    self.output_folder_edit.textChanged.connect(self.export_folder_edit.setText)
    destination_layout.addWidget(self.export_folder_edit, 0, 0)
    destination_layout.addWidget(self.export_folder_button, 0, 1)
    self.export_summary_label = QLabel(
        "Choose a folder, review the stick plots, then select “Analyze and save outputs”."
    )
    self.export_summary_label.setWordWrap(True)
    destination_layout.addWidget(self.export_summary_label, 1, 0, 1, 2)
    self.open_results_button = QPushButton("Open saved results folder")
    self.open_results_button.setEnabled(False)
    self.open_results_button.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._saved_results_folder)))
    )
    destination_layout.addWidget(self.open_results_button, 2, 0, 1, 2)
    output_tab_layout.addWidget(destination_box)
    output_options_box = QGroupBox("Files to save")
    self.output_options_box = output_options_box
    output_options_layout = QVBoxLayout(output_options_box)
    explanation = QLabel(
        "Each recording gets left_stride_parameters.csv, right_stride_parameters.csv, and general_parameters/general_parameters.csv. Each side uses its own strides and matching bottom timestamps. General measurements describe the whole recording. Standard deviations are retained; ALMA variability across 5 or 10 strides is excluded."
    )
    explanation.setWordWrap(True)
    output_options_layout.addWidget(explanation)
    self.stickplot_checkbox = QCheckBox("Left and right stick plots (SVG)")
    self.stickplot_checkbox.setChecked(True)
    self.alma_representations_checkbox = QCheckBox("ALMA figures for each side (SVG)")
    self.alma_representations_checkbox.setChecked(True)
    self.rustlab1_checkbox = QCheckBox("RustLab1 figures from the paired views (SVG)")
    self.rustlab1_checkbox.setChecked(True)
    for control in (self.stickplot_checkbox, self.alma_representations_checkbox, self.rustlab1_checkbox):
        output_options_layout.addWidget(control)
    set_tooltip(
        self.stickplot_checkbox,
        "Save full-recording stick plots using the same detector and coordinates as the preview.",
    )
    set_tooltip(
        self.alma_representations_checkbox,
        "Save seven ALMA diagnostic figures per side. Removed multi-stride variability is excluded.",
    )
    set_tooltip(
        self.rustlab1_checkbox,
        "Save 16 hindlimb figure categories, with two additional side-view joint figures when forelimbs are included. No tail-base or bottom-center markers are required.",
    )
    self.stroke_analysis_checkbox = QCheckBox("Synchronized stroke outputs")
    self.stroke_analysis_checkbox.setChecked(False)
    self.stroke_analysis_checkbox.hide()
    self.parameter_figures_button = QPushButton("View all parameter figures…")
    self.parameter_figures_button.setEnabled(False)
    output_options_layout.addWidget(self.parameter_figures_button)
    output_tab_layout.addWidget(output_options_box)
    rustlab_box = QGroupBox("Standalone RustLab1 outputs")
    self.rustlab_box = rustlab_box
    rustlab_layout = QVBoxLayout(rustlab_box)
    self.rustlab_standalone_figures_checkbox = QCheckBox("Save RustLab1 figures")
    self.rustlab_standalone_figures_checkbox.setChecked(True)
    rustlab_layout.addWidget(self.rustlab_standalone_figures_checkbox)
    self.rustlab_status_label = QLabel(
        "Standalone RustLab1 uses bottom-paw timing. Choose ALMA + post-ALMA features for the combined ALMA and RustLab1 export."
    )
    self.rustlab_status_label.setWordWrap(True)
    rustlab_layout.addWidget(self.rustlab_status_label)
    output_tab_layout.addWidget(rustlab_box)
    output_tab_layout.addStretch(1)
