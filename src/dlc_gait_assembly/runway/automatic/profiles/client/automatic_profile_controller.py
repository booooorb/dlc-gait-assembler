"""Coordinate profile selection, dirty-state prompts, saving, duplication, and deletion."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import (
    AutomatedPipelineProfile,
    ProfileDraft,
)


class AutomaticProfileController:
    """AutomaticProfileController operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _refresh_profiles(self, selected_id: str | None = None) -> None:
        profiles = self.view.profile_use_cases.list_profiles()
        self.view.profile_state.profiles = {profile.id: profile for profile in profiles}
        selectors = (self.view.profile_selector, self.view.configuration_profile_selector)
        blockers = [QSignalBlocker(selector) for selector in selectors]
        for selector in selectors:
            selector.clear()
        if not profiles:
            for selector in selectors:
                selector.addItem("No saved profiles", None)
                selector.setEnabled(False)
            self.view.duplicate_profile_button.setEnabled(False)
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
        self._load_profile(self.view.profile_state.profiles[selected_id])

    def _profile_selection_changed(self, index: int) -> None:
        self._profile_id_selected(self.view.profile_selector.itemData(index))

    def _configuration_profile_selection_changed(self, index: int) -> None:
        self._profile_id_selected(self.view.configuration_profile_selector.itemData(index))

    def _profile_id_selected(self, profile_id: str | None) -> None:
        if not profile_id or profile_id == self.view.profile_state.current_profile_id:
            return
        if not self._confirm_discard_changes():
            self._select_combo_id(self.view.profile_state.current_profile_id)
            return
        self._load_profile(self.view.profile_state.profiles[profile_id])
        self._select_combo_id(profile_id)

    def _new_profile(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._select_combo_id(None)
        self._show_new_profile()
        self.view.profile_name.setFocus()

    def _duplicate_profile(self) -> None:
        if self.view.profile_state.current_profile_id is None or not self._confirm_discard_changes():
            return
        source = self.view.profile_use_cases.load(self.view.profile_state.current_profile_id)
        (duplicate_name, accepted) = QInputDialog.getText(
            self.view, "Duplicate profile", "Name for the duplicated profile:", QLineEdit.Normal, f"{source.name} copy"
        )
        duplicate_name = duplicate_name.strip()
        if not accepted or not duplicate_name:
            return
        try:
            duplicate = self.view.profile_use_cases.duplicate(source.id, duplicate_name)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not duplicate profile", str(exc))
            return
        self._refresh_profiles(duplicate.id)
        self.view.status_label.setText(f'Profile duplicated as "{duplicate.name}".')

    def _show_profile_configuration(self) -> None:
        self.view.workspace_stack.setCurrentWidget(self.view.configuration_page)
        self.view.workspace_changed.emit("profiles")

    def _show_automation_menu(self) -> None:
        self.view.workspace_stack.setCurrentWidget(self.view.automation_page)
        self.view.workspace_changed.emit("run")

    def _show_new_profile(self) -> None:
        self.view.profile_state.current_profile_id = None
        self.view.profile_name.clear()
        self.view.profile_state.manifest_source = None
        self.view.profile_state.calibration_source = None
        self.view.profile_state.analysis_manifest_source = None
        self.view.profile_state.knee_manifest_source = None
        self.view.profile_state.regions = ()
        self.view.profile_state.model_sources = {}
        blockers = (
            QSignalBlocker(self.view.include_gait_analysis_button),
            QSignalBlocker(self.view.include_knee_correction_button),
        )
        self.view.include_gait_analysis_button.setChecked(True)
        self.view.include_knee_correction_button.setChecked(False)
        del blockers
        self.view.profile_assets._apply_profile_stage_option_state()
        self.view.profile_assets._refresh_paths()
        self.view.profile_models._render_model_rows()
        self.view.delete_profile_button.setEnabled(False)
        self.view.duplicate_profile_button.setEnabled(False)
        self.view.save_profile_button.setText("Save new profile")
        self.view.status_label.setText("Start with the video processing manifest in step 1.")
        self.view.profile_state.saved_snapshot = self._snapshot()

    def _load_profile(self, profile: AutomatedPipelineProfile) -> None:
        self.view.profile_state.current_profile_id = profile.id
        self.view.profile_name.setText(profile.name)
        self.view.profile_state.manifest_source = profile.processing_manifest
        self.view.profile_state.calibration_source = profile.calibration_map
        self.view.profile_state.analysis_manifest_source = profile.analysis_manifest
        self.view.profile_state.knee_manifest_source = profile.knee_manifest
        self.view.profile_state.regions = (
            self.view.profile_use_cases.processing_regions(profile.processing_manifest)
            if profile.processing_manifest is not None
            else ()
        )
        self.view.profile_state.model_sources = {
            region: profile.deeplabcut_models.get(region) for region in self.view.profile_state.regions
        }
        blockers = (
            QSignalBlocker(self.view.include_gait_analysis_button),
            QSignalBlocker(self.view.include_knee_correction_button),
        )
        self.view.include_gait_analysis_button.setChecked(profile.gait_analysis_enabled)
        self.view.include_knee_correction_button.setChecked(profile.knee_correction_enabled)
        del blockers
        self.view.profile_assets._apply_profile_stage_option_state()
        self.view.profile_assets._refresh_paths()
        self.view.profile_models._render_model_rows()
        self.view.profile_state.saved_snapshot = self._snapshot()
        self.view.delete_profile_button.setEnabled(True)
        self.view.duplicate_profile_button.setEnabled(True)
        self.view.save_profile_button.setText("Save changes")
        self.view.status_label.setText(f'Profile "{profile.name}" is selected. Saving does not run the pipeline.')

    def _save_profile(self) -> None:
        name = self.view.profile_name.text().strip()
        if not name:
            QMessageBox.warning(self.view, "Profile name required", "Enter a name for this profile.")
            return
        if self.view.profile_state.manifest_source is None:
            QMessageBox.warning(self.view, "Manifest required", "Complete step 1 by uploading a processing manifest.")
            return
        missing_models = [
            region
            for region in self.view.profile_state.regions
            if self.view.profile_state.model_sources.get(region) is None
        ]
        if missing_models:
            QMessageBox.warning(
                self.view,
                "Region models required",
                "Upload one DeepLabCut model for each region:\n• " + "\n• ".join(missing_models),
            )
            return
        gait_enabled = self.view.include_gait_analysis_button.isChecked()
        knee_enabled = self.view.include_knee_correction_button.isChecked()
        if gait_enabled and self.view.profile_state.calibration_source is None:
            QMessageBox.warning(self.view, "Calibration required", "Complete step 3 by uploading a calibration map.")
            return
        if gait_enabled and self.view.profile_state.analysis_manifest_source is None:
            QMessageBox.warning(
                self.view, "Analysis manifest required", "Complete step 3 by uploading a gait analysis manifest."
            )
            return
        if knee_enabled and self.view.profile_state.knee_manifest_source is None:
            QMessageBox.warning(
                self.view, "Knee manifest required", "Upload a knee analysis manifest or turn off Knee correction."
            )
            return
        if self.view.profile_state.current_profile_id is not None:
            if not self._is_dirty():
                self.view.status_label.setText("No profile changes to save.")
                return
            if not self._confirm_replace_profile(name):
                return
        try:
            profile = self.view.profile_use_cases.save(
                name,
                self.view.profile_state.manifest_source,
                self.view.profile_state.calibration_source if gait_enabled else None,
                {region: path for (region, path) in self.view.profile_state.model_sources.items() if path is not None},
                profile_id=self.view.profile_state.current_profile_id,
                analysis_manifest=self.view.profile_state.analysis_manifest_source if gait_enabled else None,
                knee_manifest=self.view.profile_state.knee_manifest_source if knee_enabled else None,
                gait_analysis_enabled=gait_enabled,
                knee_correction_enabled=knee_enabled,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not save profile", str(exc))
            return
        self._refresh_profiles(profile.id)
        self.view.status_label.setText(f'Profile "{profile.name}" saved. No pipeline was started.')

    def _delete_profile(self) -> None:
        if self.view.profile_state.current_profile_id is None:
            return
        profile_name = self.view.profile_name.text().strip() or "this profile"
        if not self._confirm_delete_profile(profile_name):
            return
        try:
            self.view.profile_use_cases.delete(self.view.profile_state.current_profile_id)
        except OSError as exc:
            QMessageBox.critical(self.view, "Could not delete profile", str(exc))
            return
        self._refresh_profiles()
        self.view.status_label.setText(f'Profile "{profile_name}" was permanently deleted.')

    def _confirm_replace_profile(self, profile_name: str) -> bool:
        return (
            QMessageBox.question(
                self.view,
                "Replace saved profile?",
                f'Saving will replace the files currently stored in "{profile_name}" and delete those app-managed copies forever. Keep your own backup. Are you sure?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _confirm_delete_profile(self, profile_name: str) -> bool:
        return (
            QMessageBox.question(
                self.view,
                "Delete profile forever?",
                f'Deleting "{profile_name}" will permanently remove the profile and all of its stored files. Keep your own backup. Are you sure?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _confirm_discard_changes(self) -> bool:
        if not self._is_dirty():
            return True
        return (
            QMessageBox.question(
                self.view,
                "Discard unsaved profile changes?",
                "Changing profiles will discard the selections you have not saved. Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _snapshot(self) -> tuple[str, ...]:
        return ProfileDraft(
            name=self.view.profile_name.text(),
            processing_manifest=self.view.profile_state.manifest_source,
            calibration_map=self.view.profile_state.calibration_source,
            deeplabcut_models={
                region: path for (region, path) in self.view.profile_state.model_sources.items() if path is not None
            },
            analysis_manifest=self.view.profile_state.analysis_manifest_source,
            knee_manifest=self.view.profile_state.knee_manifest_source,
            gait_analysis_enabled=self.view.include_gait_analysis_button.isChecked(),
            knee_correction_enabled=self.view.include_knee_correction_button.isChecked(),
        ).snapshot()

    def _is_dirty(self) -> bool:
        if self.view.profile_state.saved_snapshot is None:
            return any(self._snapshot())
        return self._snapshot() != self.view.profile_state.saved_snapshot

    def _select_combo_id(self, profile_id: str | None) -> None:
        selectors = (self.view.profile_selector, self.view.configuration_profile_selector)
        blockers = [QSignalBlocker(selector) for selector in selectors]
        for selector in selectors:
            target_index = -1
            for index in range(selector.count()):
                if selector.itemData(index) == profile_id:
                    target_index = index
                    break
            selector.setCurrentIndex(target_index)
        del blockers


try:
    import cv2
except ImportError:
    cv2 = None
