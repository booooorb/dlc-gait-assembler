from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.services.automated_profiles import (
    ASSET_KEYS,
    AutomatedPipelineProfile,
    AutomatedProfileStore,
)
from dlc_gait_assembly.services.project_paths import find_project_root


ASSET_DETAILS = {
    "calibration_map": (
        "Calibration map",
        "Export from Manual calibration (conversion_factor_map.json).",
    ),
    "deeplabcut_model": (
        "DeepLabCut model",
        "Choose a trained model file, archive, or project/model folder.",
    ),
    "processing_manifest": (
        "Video processing manifest",
        "Export from Video Processing (processing_manifest.json).",
    ),
}


class AutomatedPipelineProfilesWidget(QWidget):
    """Profile-only UI for future automated-pipeline inputs."""

    def __init__(self, store: AutomatedProfileStore | None = None):
        super().__init__()
        self.setObjectName("AutomatedPipelineProfilesWidget")
        project_root = find_project_root(Path.cwd())
        self._store = store or AutomatedProfileStore(project_root / "outputs" / "automated_profiles")
        self._profiles: dict[str, AutomatedPipelineProfile] = {}
        self._current_profile_id: str | None = None
        self._asset_sources: dict[str, Path | None] = {key: None for key in ASSET_KEYS}
        self._saved_snapshot: tuple[str, ...] | None = None
        self._build_ui()
        self._connect_signals()
        self._refresh_profiles()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("ProfileHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(8)

        title = QLabel("Automated pipeline profiles")
        title.setObjectName("AutomatedProfileTitle")
        header_layout.addWidget(title)
        description = QLabel(
            "Bundle the three inputs required by a future automated run. "
            "Saving a profile only stores copies; it does not start the pipeline."
        )
        description.setObjectName("AutomatedProfileDescription")
        description.setWordWrap(True)
        header_layout.addWidget(description)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_label = QLabel("Profile")
        selector_label.setObjectName("FieldLabel")
        selector_row.addWidget(selector_label)
        self.profile_selector = QComboBox()
        self.profile_selector.setObjectName("ProfileSelector")
        self.profile_selector.setAccessibleName("Saved automated pipeline profile")
        selector_row.addWidget(self.profile_selector, 1)
        self.new_profile_button = QPushButton("New profile")
        self.new_profile_button.setObjectName("NewProfileButton")
        selector_row.addWidget(self.new_profile_button)
        self.delete_profile_button = QPushButton("Delete profile")
        self.delete_profile_button.setObjectName("DeleteProfileButton")
        selector_row.addWidget(self.delete_profile_button)
        header_layout.addLayout(selector_row)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel("Name")
        name_label.setObjectName("FieldLabel")
        name_row.addWidget(name_label)
        self.profile_name = QLineEdit()
        self.profile_name.setObjectName("ProfileNameInput")
        self.profile_name.setPlaceholderText("Example: Treadmill camera setup")
        self.profile_name.setAccessibleName("Automated pipeline profile name")
        name_row.addWidget(self.profile_name, 1)
        header_layout.addLayout(name_row)
        root.addWidget(header)

        self.asset_path_labels: dict[str, QLabel] = {}
        self.asset_upload_buttons: dict[str, QPushButton] = {}
        for key in ASSET_KEYS:
            root.addWidget(self._asset_card(key))

        footer = QFrame()
        footer.setObjectName("ProfileFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)
        footer_layout.setSpacing(8)
        self.status_label = QLabel("Choose all three inputs, then save the profile.")
        self.status_label.setObjectName("ProfileStatusLabel")
        self.status_label.setWordWrap(True)
        footer_layout.addWidget(self.status_label, 1)
        self.save_profile_button = QPushButton("Save profile")
        self.save_profile_button.setObjectName("PrimaryButton")
        footer_layout.addWidget(self.save_profile_button)
        root.addWidget(footer)
        root.addStretch(1)

    def _asset_card(self, key: str) -> QFrame:
        title_text, description_text = ASSET_DETAILS[key]
        card = QFrame()
        card.setObjectName("ProfileAssetCard")
        card.setProperty("assetKey", key)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        text_block = QWidget()
        text_layout = QVBoxLayout(text_block)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        title = QLabel(title_text)
        title.setObjectName("AssetTitle")
        text_layout.addWidget(title)
        description = QLabel(description_text)
        description.setObjectName("AssetDescription")
        description.setWordWrap(True)
        text_layout.addWidget(description)
        path_label = QLabel("Not selected")
        path_label.setObjectName("AssetPath")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setWordWrap(True)
        text_layout.addWidget(path_label)
        self.asset_path_labels[key] = path_label
        layout.addWidget(text_block, 1)

        button_column = QVBoxLayout()
        button_column.setSpacing(6)
        upload_button = QPushButton("Upload file")
        upload_button.setObjectName("AssetUploadButton")
        upload_button.setProperty("assetKey", key)
        self.asset_upload_buttons[key] = upload_button
        button_column.addWidget(upload_button)
        if key == "deeplabcut_model":
            self.model_folder_button = QPushButton("Upload folder")
            self.model_folder_button.setObjectName("ModelFolderButton")
            button_column.addWidget(self.model_folder_button)
        button_column.addStretch(1)
        layout.addLayout(button_column)
        return card

    def _connect_signals(self) -> None:
        self.profile_selector.currentIndexChanged.connect(self._profile_selection_changed)
        self.new_profile_button.clicked.connect(self._new_profile)
        self.delete_profile_button.clicked.connect(self._delete_profile)
        self.save_profile_button.clicked.connect(self._save_profile)
        self.asset_upload_buttons["calibration_map"].clicked.connect(self._choose_calibration_map)
        self.asset_upload_buttons["deeplabcut_model"].clicked.connect(self._choose_model_file)
        self.model_folder_button.clicked.connect(self._choose_model_folder)
        self.asset_upload_buttons["processing_manifest"].clicked.connect(self._choose_processing_manifest)

    def _refresh_profiles(self, selected_id: str | None = None) -> None:
        profiles = self._store.list_profiles()
        self._profiles = {profile.id: profile for profile in profiles}
        blocker = QSignalBlocker(self.profile_selector)
        self.profile_selector.clear()
        if not profiles:
            self.profile_selector.addItem("No saved profiles", None)
            self.profile_selector.setEnabled(False)
            self.delete_profile_button.setEnabled(False)
            del blocker
            self._show_new_profile()
            return

        self.profile_selector.setEnabled(True)
        for profile in profiles:
            self.profile_selector.addItem(profile.name, profile.id)
        profile_ids = [profile.id for profile in profiles]
        selected_id = selected_id if selected_id in profile_ids else profile_ids[0]
        self.profile_selector.setCurrentIndex(profile_ids.index(selected_id))
        del blocker
        self._load_profile(self._profiles[selected_id])

    def _profile_selection_changed(self, index: int) -> None:
        profile_id = self.profile_selector.itemData(index)
        if not profile_id or profile_id == self._current_profile_id:
            return
        if not self._confirm_discard_changes():
            blocker = QSignalBlocker(self.profile_selector)
            self._select_combo_id(self._current_profile_id)
            del blocker
            return
        self._load_profile(self._profiles[profile_id])

    def _new_profile(self) -> None:
        if not self._confirm_discard_changes():
            return
        blocker = QSignalBlocker(self.profile_selector)
        self.profile_selector.setCurrentIndex(-1)
        del blocker
        self._show_new_profile()
        self.profile_name.setFocus()

    def _show_new_profile(self) -> None:
        self._current_profile_id = None
        self.profile_name.clear()
        self._asset_sources = {key: None for key in ASSET_KEYS}
        self._saved_snapshot = None
        self._refresh_asset_labels()
        self.delete_profile_button.setEnabled(False)
        self.save_profile_button.setText("Save new profile")
        self.status_label.setText("Choose all three inputs, then save the profile.")

    def _load_profile(self, profile: AutomatedPipelineProfile) -> None:
        self._current_profile_id = profile.id
        self.profile_name.setText(profile.name)
        self._asset_sources = {key: path for key, path in profile.asset_paths().items()}
        self._refresh_asset_labels()
        self._saved_snapshot = self._snapshot()
        self.delete_profile_button.setEnabled(True)
        self.save_profile_button.setText("Save changes")
        self.status_label.setText(f'Profile "{profile.name}" is selected. Saving does not run the pipeline.')

    def _choose_calibration_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose calibration map",
            str(find_project_root(Path.cwd()) / "outputs" / "calibration"),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_asset_source("calibration_map", Path(path))

    def _choose_model_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose DeepLabCut model file or archive",
            str(Path.home()),
            "Model files (*.zip *.tar *.gz *.h5 *.pt *.pth *.yaml *.yml);;All files (*)",
        )
        if path:
            self._set_asset_source("deeplabcut_model", Path(path))

    def _choose_model_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose DeepLabCut model or project folder",
            str(Path.home()),
        )
        if path:
            self._set_asset_source("deeplabcut_model", Path(path))

    def _choose_processing_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose video processing manifest",
            str(find_project_root(Path.cwd()) / "outputs" / "videos"),
            "Processing manifest (processing_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_asset_source("processing_manifest", Path(path))

    def _set_asset_source(self, key: str, path: Path) -> None:
        if key not in self._asset_sources:
            raise ValueError(f"Unknown automated profile asset: {key}")
        self._asset_sources[key] = path.expanduser().resolve()
        self._refresh_asset_labels()
        self.status_label.setText("Selection updated. Save the profile to keep this change.")

    def _refresh_asset_labels(self) -> None:
        for key, label in self.asset_path_labels.items():
            path = self._asset_sources[key]
            label.setText(str(path) if path is not None else "Not selected")
            label.setToolTip(str(path) if path is not None else "")

    def _save_profile(self) -> None:
        name = self.profile_name.text().strip()
        missing = [ASSET_DETAILS[key][0] for key, path in self._asset_sources.items() if path is None]
        if not name:
            QMessageBox.warning(self, "Profile name required", "Enter a name for this profile.")
            return
        if missing:
            QMessageBox.warning(
                self,
                "Profile inputs required",
                "Choose all three profile inputs before saving:\n• " + "\n• ".join(missing),
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
                {key: path for key, path in self._asset_sources.items() if path is not None},
                self._current_profile_id,
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
        return (
            self.profile_name.text().strip(),
            *(str(self._asset_sources[key]) if self._asset_sources[key] is not None else "" for key in ASSET_KEYS),
        )

    def _is_dirty(self) -> bool:
        if self._saved_snapshot is None:
            return any(self._snapshot())
        return self._snapshot() != self._saved_snapshot

    def _select_combo_id(self, profile_id: str | None) -> None:
        for index in range(self.profile_selector.count()):
            if self.profile_selector.itemData(index) == profile_id:
                self.profile_selector.setCurrentIndex(index)
                return
        self.profile_selector.setCurrentIndex(-1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
                QWidget#AutomatedPipelineProfilesWidget {
                    background: {theme.BACKGROUND};
                    color: {theme.TEXT};
                }
                QFrame#ProfileHeader, QFrame#ProfileAssetCard, QFrame#ProfileFooter {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 3px;
                }
                QLabel#AutomatedProfileTitle {
                    color: {theme.TEXT};
                    font-size: 16px;
                    font-weight: 650;
                }
                QLabel#AutomatedProfileDescription, QLabel#AssetDescription,
                QLabel#AssetPath, QLabel#ProfileStatusLabel {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QLabel#FieldLabel {
                    color: {theme.TEXT};
                    font-weight: 600;
                    min-width: 48px;
                }
                QLabel#AssetTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 600;
                }
                QLabel#AssetPath {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    padding: 4px 6px;
                }
                QPushButton#DeleteProfileButton:hover {
                    border-color: {theme.STATUS_ERROR};
                    color: {theme.STATUS_ERROR};
                }
                """
            )
        )
