"""Select processing, calibration, knee, and gait manifests for a profile draft."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path


class AutomaticProfileAssetsPanel:
    """AutomaticProfileAssetsPanel operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_processing_manifest(self) -> None:
        (path, _) = QFileDialog.getOpenFileName(
            self.view,
            "Choose video settings or processing manifest",
            str(self.view.workspace.manual / "video_processing"),
            "Video manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_manifest_source(Path(path))

    def _set_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            regions = self.view.profile_use_cases.processing_regions(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not read regions", str(exc))
            return False
        previous_models = self.view.profile_state.model_sources
        self.view.profile_state.manifest_source = path
        self.view.profile_state.regions = regions
        self.view.profile_state.model_sources = {region: previous_models.get(region) for region in regions}
        self._refresh_paths()
        self.view.profile_models._render_model_rows()
        self.view.status_label.setText(f"Detected {len(regions)} region(s). Assign one model per region below.")
        return True

    def _choose_calibration_map(self) -> None:
        (path, _) = QFileDialog.getOpenFileName(
            self.view,
            "Choose calibration map",
            str(self.view.workspace.manual / "calibration"),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self.view.profile_state.calibration_source = Path(path).expanduser().resolve()
            self._refresh_paths()
            self.view.status_label.setText(
                "Calibration selected. Add the gait manifest and optional knee manifest below it."
            )

    def _profile_stage_options_changed(self, _checked: bool = False) -> None:
        self._apply_profile_stage_option_state()
        self.view.profile_readiness._refresh_profile_readiness()
        included = []
        if self.view.include_gait_analysis_button.isChecked():
            included.append("gait analysis")
        if self.view.include_knee_correction_button.isChecked():
            included.append("knee correction")
        self.view.status_label.setText(
            "Included: " + (", ".join(included) if included else "video processing and DLC only")
        )
        workflow = getattr(self.view, "workflow_controller", None)
        if workflow is not None and not workflow.loading:
            workflow.save()

    def _apply_profile_stage_option_state(self) -> None:
        gait_enabled = self.view.include_gait_analysis_button.isChecked()
        knee_enabled = self.view.include_knee_correction_button.isChecked()
        for widget in (
            self.view.calibration_path_label,
            self.view.open_calibration_settings_button,
            self.view.calibration_upload_button,
            self.view.analysis_manifest_path_label,
            self.view.open_gait_settings_button,
            self.view.analysis_manifest_upload_button,
        ):
            widget.setEnabled(gait_enabled)
        for widget in (
            self.view.knee_manifest_path_label,
            self.view.open_knee_settings_button,
            self.view.knee_manifest_upload_button,
        ):
            widget.setEnabled(knee_enabled)

    def _choose_analysis_manifest(self) -> None:
        (path, _) = QFileDialog.getOpenFileName(
            self.view,
            "Choose gait analysis manifest",
            str(self.view.workspace.manual / "gait_analysis"),
            "Analysis manifest (analysis_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_analysis_manifest_source(Path(path))

    def _set_analysis_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            self.view.profile_use_cases.inspect_gait_settings(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not read analysis manifest", str(exc))
            return False
        self.view.profile_state.analysis_manifest_source = path
        self.view.include_gait_analysis_button.setChecked(True)
        self._refresh_paths()
        self.view.status_label.setText("Gait analysis settings selected. Save the profile when ready.")
        return True

    def _choose_knee_manifest(self) -> None:
        (path, _) = QFileDialog.getOpenFileName(
            self.view,
            "Choose knee analysis manifest",
            str(self.view.workspace.manual / "knee_correction"),
            "Knee analysis manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_knee_manifest_source(Path(path))

    def _set_knee_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            self.view.profile_use_cases.inspect_knee_settings(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not read knee manifest", str(exc))
            return False
        self.view.profile_state.knee_manifest_source = path
        self.view.include_knee_correction_button.setChecked(True)
        self._refresh_paths()
        self.view.status_label.setText("Knee analysis settings selected. Save the profile when ready.")
        return True

    def _refresh_paths(self) -> None:
        self._set_path_label(self.view.manifest_path_label, self.view.profile_state.manifest_source)
        self._set_path_label(self.view.calibration_path_label, self.view.profile_state.calibration_source)
        self._set_path_label(self.view.analysis_manifest_path_label, self.view.profile_state.analysis_manifest_source)
        self._set_path_label(self.view.knee_manifest_path_label, self.view.profile_state.knee_manifest_source)
        if getattr(self.view, "workflow_controller", None) is not None:
            for label, path in (
                (self.view.manifest_path_label, self.view.profile_state.manifest_source),
                (self.view.calibration_path_label, self.view.profile_state.calibration_source),
                (self.view.analysis_manifest_path_label, self.view.profile_state.analysis_manifest_source),
                (self.view.knee_manifest_path_label, self.view.profile_state.knee_manifest_source),
            ):
                label.setText("Saved in this workflow" if path else "Open settings, then save the workflow")
                label.setToolTip("")
        if self.view.profile_state.regions:
            self.view.regions_label.setText("Detected regions: " + " → ".join(self.view.profile_state.regions))
        else:
            self.view.regions_label.setText("No regions detected yet.")
        self.view.profile_readiness._refresh_profile_readiness()

    @staticmethod
    def _set_path_label(label: QLabel, path: Path | None) -> None:
        label.setText(str(path) if path is not None else "Not selected")
        label.setToolTip(str(path) if path is not None else "")


def build_automatic_stage_switches(self, calibration_content):
    calibration_content.addWidget(self._field_label("Included analysis stages"))
    self.include_gait_analysis_button = QCheckBox("Gait analysis")
    self.include_gait_analysis_button.setObjectName("ProfileStageToggle")
    self.include_gait_analysis_button.setChecked(True)
    set_tooltip(self.include_gait_analysis_button, 'Include stickplot generation and final gait parameter extraction in this profile.')
    self.include_knee_correction_button = QCheckBox("Knee correction")
    self.include_knee_correction_button.setObjectName("ProfileStageToggle")
    self.include_knee_correction_button.setChecked(False)
    set_tooltip(self.include_knee_correction_button, 'Include knee-coordinate correction before stickplot or gait analysis.')
    off_icon = resource_path("icons", "stage-switch-off.svg").as_posix()
    on_icon = resource_path("icons", "stage-switch-on.svg").as_posix()
    for switch in (self.include_gait_analysis_button, self.include_knee_correction_button):
        switch.setStyleSheet(f"""
            QCheckBox {{ spacing: 8px; padding: 5px 0; }}
            QCheckBox::indicator {{ width: 34px; height: 18px; image: url("{off_icon}"); }}
            QCheckBox::indicator:checked {{ image: url("{on_icon}"); }}
        """)
        calibration_content.addWidget(switch, alignment=Qt.AlignLeft)


def build_automatic_analysis_assets(self, calibration_content):
    calibration_content.addWidget(self._field_label("Shared calibration map (optional)"))
    calibration_row = QHBoxLayout()
    self.calibration_path_label = self._path_label()
    calibration_row.addWidget(self.calibration_path_label, 1)
    self.open_calibration_settings_button = QPushButton("Open Calibration tool")
    self.open_calibration_settings_button.setObjectName("OpenManualToolButton")
    self.open_calibration_settings_button.setToolTip("Open Calibration to create or update the calibration map.")
    calibration_row.addWidget(self.open_calibration_settings_button)
    self.calibration_upload_button = QPushButton("Upload calibration map")
    self.calibration_upload_button.setObjectName("ProfileUploadButton")
    self.calibration_upload_button.setToolTip(
        "Choose a replacement map for Shared calibration map mode. Other calibration modes use their saved gait settings."
    )
    calibration_row.addWidget(self.calibration_upload_button)
    calibration_content.addLayout(calibration_row)
    calibration_content.addSpacing(10)
    calibration_content.addWidget(self._field_label("Gait analysis manifest"))
    analysis_row = QHBoxLayout()
    self.analysis_manifest_path_label = self._path_label()
    analysis_row.addWidget(self.analysis_manifest_path_label, 1)
    self.open_gait_settings_button = QPushButton("Open Gait tool")
    self.open_gait_settings_button.setObjectName("OpenManualToolButton")
    self.open_gait_settings_button.setToolTip("Open Gait Analysis to create or update its analysis manifest.")
    analysis_row.addWidget(self.open_gait_settings_button)
    self.analysis_manifest_upload_button = QPushButton("Upload analysis manifest")
    self.analysis_manifest_upload_button.setObjectName("ProfileUploadButton")
    self.analysis_manifest_upload_button.setToolTip(
        "Choose the gait-analysis manifest exported by the Gait tool. It stores the analysis settings that will be reused for this profile."
    )
    analysis_row.addWidget(self.analysis_manifest_upload_button)
    calibration_content.addLayout(analysis_row)
    calibration_content.addSpacing(10)
    calibration_content.addWidget(self._field_label("Knee analysis manifest"))
    knee_row = QHBoxLayout()
    self.knee_manifest_path_label = self._path_label()
    knee_row.addWidget(self.knee_manifest_path_label, 1)
    self.open_knee_settings_button = QPushButton("Open Knee tool")
    self.open_knee_settings_button.setObjectName("OpenManualToolButton")
    self.open_knee_settings_button.setToolTip("Open Knee Correction to create or update its knee-analysis manifest.")
    knee_row.addWidget(self.open_knee_settings_button)
    self.knee_manifest_upload_button = QPushButton("Upload knee manifest")
    self.knee_manifest_upload_button.setObjectName("ProfileUploadButton")
    self.knee_manifest_upload_button.setToolTip(
        "Choose the knee-analysis manifest exported by the Knee tool. It stores the knee lengths, label choices, confidence cutoff, and correction direction."
    )
    knee_row.addWidget(self.knee_manifest_upload_button)
    calibration_content.addLayout(knee_row)



def build_automatic_processing_asset(self, manifest_content):
    manifest_content.addWidget(self._field_label("Video settings"))
    manifest_row = QHBoxLayout()
    self.manifest_path_label = self._path_label()
    manifest_row.addWidget(self.manifest_path_label, 1)
    self.open_video_settings_button = QPushButton("Open Video tool")
    self.open_video_settings_button.setObjectName("OpenManualToolButton")
    self.open_video_settings_button.setToolTip("Open Video Processing to create or update the video settings manifest.")
    manifest_row.addWidget(self.open_video_settings_button)
    self.manifest_upload_button = QPushButton("Upload manifest")
    self.manifest_upload_button.setObjectName("ProfileUploadButton")
    self.manifest_upload_button.setToolTip(
        "Choose a video settings or processing manifest JSON file. Its crop-region names create the model slots below."
    )
    manifest_row.addWidget(self.manifest_upload_button)
    manifest_content.addLayout(manifest_row)
    self.regions_label = QLabel("No regions detected yet.")
    self.regions_label.setObjectName("DetectedRegionsLabel")
    self.regions_label.setWordWrap(True)
    manifest_content.addWidget(self.regions_label)
