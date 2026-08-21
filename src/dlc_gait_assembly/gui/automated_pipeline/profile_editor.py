from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from dlc_gait_assembly.services.analysis_manifests import (
    read_analysis_manifest,
    read_knee_analysis_manifest,
)
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedPipelineProfile,
    ProfileDraft,
    regions_from_processing_manifest,
)

try:
    import cv2
except ImportError:
    cv2 = None


class ProfileEditorPage(QWidget):
    """Container for profile configuration controls."""


class ProfileEditorMixin:
    def create_profile_from_manual_presets(
        self,
        name: str,
        *,
        processing_manifest: Path | None = None,
        calibration_map: Path | None = None,
        analysis_manifest: Path | None = None,
        knee_manifest: Path | None = None,
    ) -> AutomatedPipelineProfile:
        """Save a named profile containing every available manual-workspace preset."""
        profile = self._store.save(
            name,
            processing_manifest,
            calibration_map,
            {},
            analysis_manifest=analysis_manifest,
            knee_manifest=knee_manifest,
            gait_analysis_enabled=analysis_manifest is not None,
            knee_correction_enabled=knee_manifest is not None,
            allow_incomplete=True,
        )
        self._refresh_profiles(profile.id)
        self._show_profile_configuration()
        self.status_label.setText(f'Profile "{profile.name}" created from the available manual settings.')
        return profile

    def _refresh_profiles(self, selected_id: str | None = None) -> None:
        profiles = self._store.list_profiles()
        self._profiles = {profile.id: profile for profile in profiles}
        selectors = (self.profile_selector, self.configuration_profile_selector)
        blockers = [QSignalBlocker(selector) for selector in selectors]
        for selector in selectors:
            selector.clear()
        if not profiles:
            for selector in selectors:
                selector.addItem("No saved profiles", None)
                selector.setEnabled(False)
            self.duplicate_profile_button.setEnabled(False)
            del blockers
            self._show_new_profile()
            return
        for selector in selectors:
            selector.setEnabled(True)
            for profile in profiles:
                selector.addItem(profile.name, profile.id)
        profile_ids = [profile.id for profile in profiles]
        selected_id = selected_id if selected_id in profile_ids else profile_ids[0]
        for selector in selectors:
            selector.setCurrentIndex(profile_ids.index(selected_id))
        del blockers
        self._load_profile(self._profiles[selected_id])

    def _profile_selection_changed(self, index: int) -> None:
        self._profile_id_selected(self.profile_selector.itemData(index))

    def _configuration_profile_selection_changed(self, index: int) -> None:
        self._profile_id_selected(self.configuration_profile_selector.itemData(index))

    def _profile_id_selected(self, profile_id: str | None) -> None:
        if not profile_id or profile_id == self._current_profile_id:
            return
        if not self._confirm_discard_changes():
            self._select_combo_id(self._current_profile_id)
            return
        self._load_profile(self._profiles[profile_id])
        self._select_combo_id(profile_id)

    def _new_profile(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._select_combo_id(None)
        self._show_new_profile()
        self.profile_name.setFocus()

    def _duplicate_profile(self) -> None:
        if self._current_profile_id is None or not self._confirm_discard_changes():
            return
        source = self._store.load(self._current_profile_id)
        duplicate_name, accepted = QInputDialog.getText(
            self,
            "Duplicate profile",
            "Name for the duplicated profile:",
            QLineEdit.Normal,
            f"{source.name} copy",
        )
        duplicate_name = duplicate_name.strip()
        if not accepted or not duplicate_name:
            return
        try:
            duplicate = self._store.save(
                duplicate_name,
                source.processing_manifest,
                source.calibration_map,
                source.deeplabcut_models,
                analysis_manifest=source.analysis_manifest,
                knee_manifest=source.knee_manifest,
                gait_analysis_enabled=source.gait_analysis_enabled,
                knee_correction_enabled=source.knee_correction_enabled,
                allow_incomplete=True,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not duplicate profile", str(exc))
            return
        self._refresh_profiles(duplicate.id)
        self.status_label.setText(f'Profile duplicated as "{duplicate.name}".')

    def _show_profile_configuration(self) -> None:
        self.workspace_stack.setCurrentWidget(self.configuration_page)
        self.workspace_changed.emit("profiles")

    def _show_automation_menu(self) -> None:
        self.workspace_stack.setCurrentWidget(self.automation_page)
        self.workspace_changed.emit("run")

    def _show_new_profile(self) -> None:
        self._current_profile_id = None
        self.profile_name.clear()
        self._manifest_source = None
        self._calibration_source = None
        self._analysis_manifest_source = None
        self._knee_manifest_source = None
        self._regions = ()
        self._model_sources = {}
        blockers = (
            QSignalBlocker(self.include_gait_analysis_button),
            QSignalBlocker(self.include_knee_correction_button),
        )
        self.include_gait_analysis_button.setChecked(True)
        self.include_knee_correction_button.setChecked(False)
        del blockers
        self._apply_profile_stage_option_state()
        self._refresh_paths()
        self._render_model_rows()
        self.delete_profile_button.setEnabled(False)
        self.duplicate_profile_button.setEnabled(False)
        self.save_profile_button.setText("Save new profile")
        self.status_label.setText("Start with the video processing manifest in step 1.")
        self._saved_snapshot = self._snapshot()

    def _load_profile(self, profile: AutomatedPipelineProfile) -> None:
        self._current_profile_id = profile.id
        self.profile_name.setText(profile.name)
        self._manifest_source = profile.processing_manifest
        self._calibration_source = profile.calibration_map
        self._analysis_manifest_source = profile.analysis_manifest
        self._knee_manifest_source = profile.knee_manifest
        self._regions = (
            regions_from_processing_manifest(profile.processing_manifest)
            if profile.processing_manifest is not None
            else ()
        )
        self._model_sources = {region: profile.deeplabcut_models.get(region) for region in self._regions}
        blockers = (
            QSignalBlocker(self.include_gait_analysis_button),
            QSignalBlocker(self.include_knee_correction_button),
        )
        self.include_gait_analysis_button.setChecked(profile.gait_analysis_enabled)
        self.include_knee_correction_button.setChecked(profile.knee_correction_enabled)
        del blockers
        self._apply_profile_stage_option_state()
        self._refresh_paths()
        self._render_model_rows()
        self._saved_snapshot = self._snapshot()
        self.delete_profile_button.setEnabled(True)
        self.duplicate_profile_button.setEnabled(True)
        self.save_profile_button.setText("Save changes")
        self.status_label.setText(f'Profile "{profile.name}" is selected. Saving does not run the pipeline.')

    def _choose_processing_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose video settings or processing manifest",
            str(self._project_root / "outputs" / "manual_pipeline" / "processed_videos"),
            "Video manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_manifest_source(Path(path))

    def _set_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            regions = regions_from_processing_manifest(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not read regions", str(exc))
            return False
        previous_models = self._model_sources
        self._manifest_source = path
        self._regions = regions
        self._model_sources = {region: previous_models.get(region) for region in regions}
        self._refresh_paths()
        self._render_model_rows()
        self.status_label.setText(
            f"Detected {len(regions)} region(s). Upload one model per region in step 2."
        )
        return True

    def _choose_calibration_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose calibration map",
            str(self._project_root / "outputs" / "calibration"),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._calibration_source = Path(path).expanduser().resolve()
            self._refresh_paths()
            self.status_label.setText("Calibration selected. Add the gait manifest and optional knee manifest below it.")

    def _profile_stage_options_changed(self, _checked: bool = False) -> None:
        self._apply_profile_stage_option_state()
        self._refresh_profile_readiness()
        included = []
        if self.include_gait_analysis_button.isChecked():
            included.append("gait analysis")
        if self.include_knee_correction_button.isChecked():
            included.append("knee correction")
        self.status_label.setText(
            "Included: " + (", ".join(included) if included else "video processing and DLC only")
        )

    def _apply_profile_stage_option_state(self) -> None:
        gait_enabled = self.include_gait_analysis_button.isChecked()
        knee_enabled = self.include_knee_correction_button.isChecked()
        for widget in (
            self.calibration_path_label,
            self.open_calibration_settings_button,
            self.calibration_upload_button,
            self.analysis_manifest_path_label,
            self.open_gait_settings_button,
            self.analysis_manifest_upload_button,
        ):
            widget.setEnabled(gait_enabled)
        for widget in (
            self.knee_manifest_path_label,
            self.open_knee_settings_button,
            self.knee_manifest_upload_button,
        ):
            widget.setEnabled(knee_enabled)

    def _choose_analysis_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose gait analysis manifest",
            str(self._project_root / "outputs" / "manual_pipeline" / "gait_analysis"),
            "Analysis manifest (analysis_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_analysis_manifest_source(Path(path))

    def _set_analysis_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            read_analysis_manifest(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not read analysis manifest", str(exc))
            return False
        self._analysis_manifest_source = path
        self.include_gait_analysis_button.setChecked(True)
        self._refresh_paths()
        self.status_label.setText("Gait analysis settings selected. Save the profile when ready.")
        return True

    def _choose_knee_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose knee analysis manifest",
            str(self._project_root / "outputs" / "manual_pipeline" / "knee_correction"),
            "Knee analysis manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_knee_manifest_source(Path(path))

    def _set_knee_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            read_knee_analysis_manifest(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not read knee manifest", str(exc))
            return False
        self._knee_manifest_source = path
        self.include_knee_correction_button.setChecked(True)
        self._refresh_paths()
        self.status_label.setText("Knee analysis settings selected. Save the profile when ready.")
        return True

    def _choose_model_file(self, region: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose DeepLabCut config for {region}",
            str(Path.home()),
            "DeepLabCut config (config.yaml);;YAML files (*.yaml);;All files (*)",
        )
        if path:
            self._set_model_source(region, Path(path))

    def _choose_model_folder(self, region: str) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            f"Choose DeepLabCut model folder for {region}",
            str(Path.home()),
        )
        if path:
            self._set_model_source(region, Path(path))

    def _set_model_source(self, region: str, path: Path) -> None:
        if region not in self._model_sources:
            raise ValueError(f"Unknown manifest region: {region}")
        self._model_sources[region] = path.expanduser().resolve()
        self._render_model_rows()
        self._refresh_profile_readiness()
        selected = sum(path is not None for path in self._model_sources.values())
        self.status_label.setText(f"Models selected for {selected} of {len(self._regions)} regions.")

    def _render_model_rows(self) -> None:
        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._regions:
            placeholder = QLabel("Manifest required")
            placeholder.setObjectName("ModelsPlaceholder")
            placeholder.setWordWrap(True)
            placeholder.setToolTip(
                "Complete step 1 first. The manifest supplies the region names needed to "
                "create one DeepLabCut model slot per region."
            )
            self.models_layout.addWidget(placeholder)
            return
        for region in self._regions:
            row = QFrame()
            row.setObjectName("RegionModelRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(8)
            region_label = QLabel(region)
            region_label.setObjectName("RegionName")
            region_label.setMinimumWidth(110)
            layout.addWidget(region_label)
            model_path = self._model_sources.get(region)
            path_label = self._path_label()
            path_label.setText(str(model_path) if model_path is not None else "Model required")
            path_label.setToolTip(str(model_path) if model_path is not None else "")
            layout.addWidget(path_label, 1)
            file_button = QPushButton("Choose config")
            file_button.setToolTip(
                f"Choose config.yaml from the trained DeepLabCut project for {region}."
            )
            file_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_file(name))
            layout.addWidget(file_button)
            folder_button = QPushButton("Choose project")
            folder_button.setToolTip(
                f"Choose the complete trained DeepLabCut project folder for {region}."
            )
            folder_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_folder(name))
            layout.addWidget(folder_button)
            self.models_layout.addWidget(row)

    def _refresh_paths(self) -> None:
        self._set_path_label(self.manifest_path_label, self._manifest_source)
        self._set_path_label(self.calibration_path_label, self._calibration_source)
        self._set_path_label(
            self.analysis_manifest_path_label,
            self._analysis_manifest_source,
        )
        self._set_path_label(self.knee_manifest_path_label, self._knee_manifest_source)
        if self._regions:
            self.regions_label.setText("Detected regions: " + " → ".join(self._regions))
        else:
            self.regions_label.setText("No regions detected yet.")
        self._refresh_profile_readiness()

    def _refresh_profile_readiness(self) -> None:
        gait_enabled = self.include_gait_analysis_button.isChecked()
        knee_enabled = self.include_knee_correction_button.isChecked()
        selected_models = sum(path is not None for path in self._model_sources.values())
        total_models = len(self._regions)
        model_state = "ready" if total_models and selected_models == total_models else "missing"
        model_text = (
            f"{selected_models} / {total_models} selected"
            if total_models
            else "Needs manifest"
        )
        self._set_profile_readiness_value(
            "manifest",
            "Selected" if self._manifest_source is not None else "Required",
            "ready" if self._manifest_source is not None else "missing",
        )
        self._set_profile_readiness_value("models", model_text, model_state)
        self._set_profile_readiness_value(
            "calibration",
            (
                "Selected"
                if gait_enabled and self._calibration_source is not None
                else "Required" if gait_enabled else "Excluded"
            ),
            (
                "ready"
                if gait_enabled and self._calibration_source is not None
                else "missing" if gait_enabled else "optional"
            ),
        )
        self._set_profile_readiness_value(
            "analysis",
            (
                "Selected"
                if gait_enabled and self._analysis_manifest_source is not None
                else "Required" if gait_enabled else "Excluded"
            ),
            (
                "ready"
                if gait_enabled and self._analysis_manifest_source is not None
                else "missing" if gait_enabled else "optional"
            ),
        )
        self._set_profile_readiness_value(
            "knee",
            (
                "Selected"
                if knee_enabled and self._knee_manifest_source is not None
                else "Required" if knee_enabled else "Excluded"
            ),
            (
                "ready"
                if knee_enabled and self._knee_manifest_source is not None
                else "missing" if knee_enabled else "optional"
            ),
        )

    def _set_profile_readiness_value(self, key: str, text: str, state: str) -> None:
        label = self.profile_readiness_values[key]
        if label.text() == text and label.property("readinessState") == state:
            return
        label.setText(text)
        label.setProperty("readinessState", state)
        label.style().unpolish(label)
        label.style().polish(label)

    @staticmethod
    def _set_path_label(label: QLabel, path: Path | None) -> None:
        label.setText(str(path) if path is not None else "Not selected")
        label.setToolTip(str(path) if path is not None else "")

    def _save_profile(self) -> None:
        name = self.profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Profile name required", "Enter a name for this profile.")
            return
        if self._manifest_source is None:
            QMessageBox.warning(self, "Manifest required", "Complete step 1 by uploading a processing manifest.")
            return
        missing_models = [region for region in self._regions if self._model_sources.get(region) is None]
        if missing_models:
            QMessageBox.warning(
                self,
                "Region models required",
                "Upload one DeepLabCut model for each region:\n• " + "\n• ".join(missing_models),
            )
            return
        gait_enabled = self.include_gait_analysis_button.isChecked()
        knee_enabled = self.include_knee_correction_button.isChecked()
        if gait_enabled and self._calibration_source is None:
            QMessageBox.warning(self, "Calibration required", "Complete step 3 by uploading a calibration map.")
            return
        if gait_enabled and self._analysis_manifest_source is None:
            QMessageBox.warning(
                self,
                "Analysis manifest required",
                "Complete step 3 by uploading a gait analysis manifest.",
            )
            return
        if knee_enabled and self._knee_manifest_source is None:
            QMessageBox.warning(
                self,
                "Knee manifest required",
                "Upload a knee analysis manifest or turn off Knee correction.",
            )
            return
        if self._current_profile_id is not None:
            if not self._is_dirty():
                self.status_label.setText("No profile changes to save.")
                return
            if not self._confirm_replace_profile(name):
                return
        try:
            profile = self._store.save(
                name,
                self._manifest_source,
                self._calibration_source if gait_enabled else None,
                {region: path for region, path in self._model_sources.items() if path is not None},
                profile_id=self._current_profile_id,
                analysis_manifest=self._analysis_manifest_source if gait_enabled else None,
                knee_manifest=self._knee_manifest_source if knee_enabled else None,
                gait_analysis_enabled=gait_enabled,
                knee_correction_enabled=knee_enabled,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not save profile", str(exc))
            return
        self._refresh_profiles(profile.id)
        self.status_label.setText(f'Profile "{profile.name}" saved. No pipeline was started.')

    def _delete_profile(self) -> None:
        if self._current_profile_id is None:
            return
        profile_name = self.profile_name.text().strip() or "this profile"
        if not self._confirm_delete_profile(profile_name):
            return
        try:
            self._store.delete(self._current_profile_id)
        except OSError as exc:
            QMessageBox.critical(self, "Could not delete profile", str(exc))
            return
        self._refresh_profiles()
        self.status_label.setText(f'Profile "{profile_name}" was permanently deleted.')

    def _confirm_replace_profile(self, profile_name: str) -> bool:
        return QMessageBox.question(
            self,
            "Replace saved profile?",
            f'Saving will replace the files currently stored in "{profile_name}" and delete those '
            "app-managed copies forever. Keep your own backup. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _confirm_delete_profile(self, profile_name: str) -> bool:
        return QMessageBox.question(
            self,
            "Delete profile forever?",
            f'Deleting "{profile_name}" will permanently remove the profile and all of its stored '
            "files. Keep your own backup. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _confirm_discard_changes(self) -> bool:
        if not self._is_dirty():
            return True
        return QMessageBox.question(
            self,
            "Discard unsaved profile changes?",
            "Changing profiles will discard the selections you have not saved. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _snapshot(self) -> tuple[str, ...]:
        return ProfileDraft(
            name=self.profile_name.text(),
            processing_manifest=self._manifest_source,
            calibration_map=self._calibration_source,
            deeplabcut_models={
                region: path
                for region, path in self._model_sources.items()
                if path is not None
            },
            analysis_manifest=self._analysis_manifest_source,
            knee_manifest=self._knee_manifest_source,
            gait_analysis_enabled=self.include_gait_analysis_button.isChecked(),
            knee_correction_enabled=self.include_knee_correction_button.isChecked(),
        ).snapshot()

    def _is_dirty(self) -> bool:
        if self._saved_snapshot is None:
            return any(self._snapshot())
        return self._snapshot() != self._saved_snapshot

    def _select_combo_id(self, profile_id: str | None) -> None:
        selectors = (self.profile_selector, self.configuration_profile_selector)
        blockers = [QSignalBlocker(selector) for selector in selectors]
        for selector in selectors:
            target_index = -1
            for index in range(selector.count()):
                if selector.itemData(index) == profile_id:
                    target_index = index
                    break
            selector.setCurrentIndex(target_index)
        del blockers
