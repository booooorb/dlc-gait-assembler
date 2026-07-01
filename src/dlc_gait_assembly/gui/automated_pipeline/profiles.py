from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedPipelineProfile,
    AutomatedProfileStore,
    regions_from_processing_manifest,
)
from dlc_gait_assembly.services.project_paths import find_project_root


class AutomatedPipelineProfilesWidget(QWidget):
    """Ordered, profile-only setup UI for the future automated pipeline."""

    def __init__(self, store: AutomatedProfileStore | None = None):
        super().__init__()
        self.setObjectName("AutomatedPipelineProfilesWidget")
        project_root = find_project_root(Path.cwd())
        self._store = store or AutomatedProfileStore(project_root / "outputs" / "automated_profiles")
        self._profiles: dict[str, AutomatedPipelineProfile] = {}
        self._current_profile_id: str | None = None
        self._manifest_source: Path | None = None
        self._calibration_source: Path | None = None
        self._regions: tuple[str, ...] = ()
        self._model_sources: dict[str, Path | None] = {}
        self._video_paths: list[Path] = []
        self._saved_snapshot: tuple[str, ...] | None = None
        self._build_ui()
        self._connect_signals()
        self._refresh_profiles()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QFrame()
        header.setObjectName("ProfileHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(8)
        title = QLabel("Automated pipeline profiles")
        title.setObjectName("AutomatedProfileTitle")
        header_layout.addWidget(title)
        description = QLabel(
            "Set up the pipeline in order. The manifest defines the video regions; each detected "
            "region then requires its own DeepLabCut model. Saving does not run the pipeline."
        )
        description.setObjectName("AutomatedProfileDescription")
        description.setWordWrap(True)
        header_layout.addWidget(description)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_row.addWidget(self._field_label("Profile"))
        self.profile_selector = QComboBox()
        self.profile_selector.setObjectName("ProfileSelector")
        self.profile_selector.setAccessibleName("Saved automated pipeline profile")
        selector_row.addWidget(self.profile_selector, 1)
        self.new_profile_button = QPushButton("New profile")
        selector_row.addWidget(self.new_profile_button)
        self.duplicate_profile_button = QPushButton("Duplicate")
        self.duplicate_profile_button.setObjectName("SmallProfileButton")
        self.duplicate_profile_button.setToolTip("Create a separately named copy of the selected profile.")
        selector_row.addWidget(self.duplicate_profile_button)
        self.delete_profile_button = QPushButton("Delete profile")
        self.delete_profile_button.setObjectName("DeleteProfileButton")
        selector_row.addWidget(self.delete_profile_button)
        header_layout.addLayout(selector_row)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(self._field_label("Name"))
        self.profile_name = QLineEdit()
        self.profile_name.setObjectName("ProfileNameInput")
        self.profile_name.setPlaceholderText("Example: Treadmill camera setup")
        name_row.addWidget(self.profile_name, 1)
        header_layout.addLayout(name_row)
        root.addWidget(header)

        automation_menu = QFrame()
        automation_menu.setObjectName("MainAutomationMenu")
        automation_layout = QVBoxLayout(automation_menu)
        automation_layout.setContentsMargins(16, 12, 16, 12)
        automation_layout.setSpacing(8)
        automation_title = QLabel("Main automation menu")
        automation_title.setObjectName("MainAutomationTitle")
        automation_layout.addWidget(automation_title)
        automation_description = QLabel(
            "Add the videos for an automated run. The console will report pipeline activity once execution is connected."
        )
        automation_description.setObjectName("AutomatedProfileDescription")
        automation_description.setWordWrap(True)
        automation_layout.addWidget(automation_description)

        automation_content = QHBoxLayout()
        automation_content.setSpacing(10)
        video_panel = QFrame()
        video_panel.setObjectName("VideoDropPanel")
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(10, 8, 10, 10)
        video_layout.setSpacing(6)
        video_toolbar = QHBoxLayout()
        videos_title = QLabel("Videos")
        videos_title.setObjectName("AutomationPanelTitle")
        video_toolbar.addWidget(videos_title)
        self.video_count_label = QLabel("0 videos")
        self.video_count_label.setObjectName("VideoCountLabel")
        video_toolbar.addWidget(self.video_count_label)
        video_toolbar.addStretch(1)
        self.upload_videos_button = QPushButton("Upload videos")
        video_toolbar.addWidget(self.upload_videos_button)
        self.remove_videos_button = QPushButton("Remove")
        self.remove_videos_button.setObjectName("RemoveButton")
        video_toolbar.addWidget(self.remove_videos_button)
        self.clear_videos_button = QPushButton("Clear")
        self.clear_videos_button.setObjectName("ClearButton")
        video_toolbar.addWidget(self.clear_videos_button)
        video_layout.addLayout(video_toolbar)
        self.video_list = VideoDropList()
        self.video_list.setObjectName("AutomationVideoDropList")
        self.video_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.video_list.setMinimumHeight(180)
        video_layout.addWidget(self.video_list, 1)
        automation_content.addWidget(video_panel, 3)

        console_panel = QFrame()
        console_panel.setObjectName("AutomationConsolePanel")
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(10, 8, 10, 10)
        console_layout.setSpacing(6)
        console_title = QLabel("Automation log / console")
        console_title.setObjectName("AutomationPanelTitle")
        console_layout.addWidget(console_title)
        self.automation_console = QPlainTextEdit()
        self.automation_console.setObjectName("AutomationConsole")
        self.automation_console.setReadOnly(True)
        self.automation_console.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.automation_console.setPlainText(
            "[Ready] Select a saved profile and add videos.\n"
            "[Info] Pipeline execution is not connected yet."
        )
        console_layout.addWidget(self.automation_console, 1)
        automation_content.addWidget(console_panel, 2)
        automation_layout.addLayout(automation_content, 1)

        run_row = QHBoxLayout()
        self.run_readiness_label = QLabel("RUN is unavailable until pipeline execution is implemented.")
        self.run_readiness_label.setObjectName("ProfileStatusLabel")
        run_row.addWidget(self.run_readiness_label, 1)
        self.run_pipeline_button = QPushButton("RUN pipeline")
        self.run_pipeline_button.setObjectName("RunPipelineButton")
        self.run_pipeline_button.setEnabled(False)
        self.run_pipeline_button.setToolTip("Pipeline execution is not connected yet.")
        run_row.addWidget(self.run_pipeline_button)
        automation_layout.addLayout(run_row)
        root.addWidget(automation_menu)

        self.configuration_menu_button = QPushButton("Profile configuration  ▸")
        self.configuration_menu_button.setObjectName("ConfigurationMenuButton")
        self.configuration_menu_button.setCheckable(True)
        self.configuration_menu_button.setAccessibleName("Open profile configuration menu")
        root.addWidget(self.configuration_menu_button)

        self.configuration_menu = QFrame()
        self.configuration_menu.setObjectName("ProfileConfigurationMenu")
        configuration_layout = QVBoxLayout(self.configuration_menu)
        configuration_layout.setContentsMargins(0, 0, 0, 0)
        configuration_layout.setSpacing(0)

        self.configuration_tabs = QTabWidget()
        self.configuration_tabs.setObjectName("ProfileConfigurationTabs")
        self.configuration_tabs.setDocumentMode(True)
        self.configuration_tabs.tabBar().setExpanding(True)

        manifest_page, manifest_content = self._stage_page(
            "Video processing manifest",
            "Upload the manifest first. Its crop regions determine which model menus appear next.",
        )
        manifest_row = QHBoxLayout()
        self.manifest_path_label = self._path_label()
        manifest_row.addWidget(self.manifest_path_label, 1)
        self.manifest_upload_button = QPushButton("Upload manifest")
        manifest_row.addWidget(self.manifest_upload_button)
        manifest_content.addLayout(manifest_row)
        self.regions_label = QLabel("No regions detected yet.")
        self.regions_label.setObjectName("DetectedRegionsLabel")
        self.regions_label.setWordWrap(True)
        manifest_content.addWidget(self.regions_label)
        manifest_content.addStretch(1)
        self.configuration_tabs.addTab(manifest_page, "1  Manifest + regions")

        models_page, models_content = self._stage_page(
            "DeepLabCut models by region",
            "Upload one trained model for every region detected from the manifest.",
        )
        self.models_container = QWidget()
        self.models_layout = QVBoxLayout(self.models_container)
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        self.models_layout.setSpacing(6)
        models_content.addWidget(self.models_container)
        models_content.addStretch(1)
        self.configuration_tabs.addTab(models_page, "2  Region models")

        calibration_page, calibration_content = self._stage_page(
            "Calibration map",
            "Upload conversion_factor_map.json exported from Manual calibration.",
        )
        calibration_row = QHBoxLayout()
        self.calibration_path_label = self._path_label()
        calibration_row.addWidget(self.calibration_path_label, 1)
        self.calibration_upload_button = QPushButton("Upload calibration map")
        calibration_row.addWidget(self.calibration_upload_button)
        calibration_content.addLayout(calibration_row)
        calibration_content.addStretch(1)
        self.configuration_tabs.addTab(calibration_page, "3  Calibration")

        save_page, save_content = self._stage_page(
            "Save profile",
            "Review the region-to-model mapping and save these inputs for a future automated run.",
        )
        save_row = QHBoxLayout()
        self.status_label = QLabel("Start with the video processing manifest in step 1.")
        self.status_label.setObjectName("ProfileStatusLabel")
        self.status_label.setWordWrap(True)
        save_row.addWidget(self.status_label, 1)
        self.save_profile_button = QPushButton("Save new profile")
        self.save_profile_button.setObjectName("PrimaryButton")
        save_row.addWidget(self.save_profile_button)
        save_content.addLayout(save_row)
        save_content.addStretch(1)
        self.configuration_tabs.addTab(save_page, "4  Review + save")
        self.configuration_tabs.setMinimumHeight(190)
        configuration_layout.addWidget(self.configuration_tabs)
        root.addWidget(self.configuration_menu)
        self.configuration_menu.setVisible(False)
        root.addStretch(1)
        self._render_model_rows()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    @staticmethod
    def _path_label() -> QLabel:
        label = QLabel("Not selected")
        label.setObjectName("AssetPath")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _stage_page(title: str, description: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("ProfileStagePage")
        content = QVBoxLayout(page)
        content.setContentsMargins(14, 12, 14, 12)
        content.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("ProfileStageTitle")
        content.addWidget(title_label)
        description_label = QLabel(description)
        description_label.setObjectName("ProfileStageDescription")
        description_label.setWordWrap(True)
        content.addWidget(description_label)
        return page, content

    def _connect_signals(self) -> None:
        self.profile_selector.currentIndexChanged.connect(self._profile_selection_changed)
        self.new_profile_button.clicked.connect(self._new_profile)
        self.duplicate_profile_button.clicked.connect(self._duplicate_profile)
        self.delete_profile_button.clicked.connect(self._delete_profile)
        self.configuration_menu_button.toggled.connect(self._toggle_configuration_menu)
        self.manifest_upload_button.clicked.connect(self._choose_processing_manifest)
        self.calibration_upload_button.clicked.connect(self._choose_calibration_map)
        self.save_profile_button.clicked.connect(self._save_profile)
        self.upload_videos_button.clicked.connect(self._choose_videos)
        self.remove_videos_button.clicked.connect(self._remove_selected_videos)
        self.clear_videos_button.clicked.connect(self._clear_videos)
        self.video_list.paths_dropped.connect(self._add_video_paths)

    def _refresh_profiles(self, selected_id: str | None = None) -> None:
        profiles = self._store.list_profiles()
        self._profiles = {profile.id: profile for profile in profiles}
        blocker = QSignalBlocker(self.profile_selector)
        self.profile_selector.clear()
        if not profiles:
            self.profile_selector.addItem("No saved profiles", None)
            self.profile_selector.setEnabled(False)
            self.duplicate_profile_button.setEnabled(False)
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
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not duplicate profile", str(exc))
            return
        self._refresh_profiles(duplicate.id)
        self.status_label.setText(f'Profile duplicated as "{duplicate.name}".')

    def _toggle_configuration_menu(self, expanded: bool) -> None:
        self.configuration_menu.setVisible(expanded)
        self.configuration_menu_button.setText(
            "Profile configuration  ▾" if expanded else "Profile configuration  ▸"
        )

    def _show_new_profile(self) -> None:
        self._current_profile_id = None
        self.profile_name.clear()
        self._manifest_source = None
        self._calibration_source = None
        self._regions = ()
        self._model_sources = {}
        self._saved_snapshot = None
        self._refresh_paths()
        self._render_model_rows()
        self.delete_profile_button.setEnabled(False)
        self.duplicate_profile_button.setEnabled(False)
        self.save_profile_button.setText("Save new profile")
        self.status_label.setText("Start with the video processing manifest in step 1.")

    def _load_profile(self, profile: AutomatedPipelineProfile) -> None:
        self._current_profile_id = profile.id
        self.profile_name.setText(profile.name)
        self._manifest_source = profile.processing_manifest
        self._calibration_source = profile.calibration_map
        self._regions = regions_from_processing_manifest(profile.processing_manifest)
        self._model_sources = {region: profile.deeplabcut_models.get(region) for region in self._regions}
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
            "Choose video processing manifest",
            str(find_project_root(Path.cwd()) / "outputs" / "videos"),
            "Processing manifest (processing_manifest.json);;JSON files (*.json);;All files (*)",
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
            str(find_project_root(Path.cwd()) / "outputs" / "calibration"),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._calibration_source = Path(path).expanduser().resolve()
            self._refresh_paths()
            self.status_label.setText("Calibration selected. Save the profile after every region has a model.")

    def _choose_videos(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Upload videos for automated processing",
            str(Path.home()),
            f"Video files ({extensions});;All files (*)",
        )
        self._add_video_paths([Path(path) for path in paths])

    def _add_video_paths(self, paths: object) -> None:
        added = 0
        skipped = 0
        known_paths = {str(path) for path in self._video_paths}
        for raw_path in paths if isinstance(paths, (list, tuple)) else ():
            path = Path(raw_path).expanduser().resolve()
            key = str(path)
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS or key in known_paths:
                skipped += 1
                continue
            self._video_paths.append(path)
            known_paths.add(key)
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, key)
            item.setToolTip(key)
            self.video_list.addItem(item)
            added += 1
        self._update_video_count()
        if added:
            self._append_console(f"[Videos] Added {added} video(s); {len(self._video_paths)} queued.")
        if skipped:
            self._append_console(f"[Videos] Skipped {skipped} unsupported or duplicate item(s).")

    def _remove_selected_videos(self) -> None:
        selected = self.video_list.selectedItems()
        if not selected:
            return
        removed_paths = {str(item.data(Qt.UserRole)) for item in selected}
        for item in selected:
            self.video_list.takeItem(self.video_list.row(item))
        self._video_paths = [path for path in self._video_paths if str(path) not in removed_paths]
        self._update_video_count()
        self._append_console(f"[Videos] Removed {len(removed_paths)} video(s).")

    def _clear_videos(self) -> None:
        if not self._video_paths:
            return
        count = len(self._video_paths)
        self._video_paths.clear()
        self.video_list.clear()
        self._update_video_count()
        self._append_console(f"[Videos] Cleared {count} video(s).")

    def _update_video_count(self) -> None:
        count = len(self._video_paths)
        self.video_count_label.setText(f"{count} video" if count == 1 else f"{count} videos")
        self.video_list.viewport().update()

    def _append_console(self, message: str) -> None:
        self.automation_console.appendPlainText(message)

    def _choose_model_file(self, region: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose DeepLabCut model for {region}",
            str(Path.home()),
            "Model files (*.zip *.tar *.gz *.h5 *.pt *.pth *.yaml *.yml);;All files (*)",
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
        selected = sum(path is not None for path in self._model_sources.values())
        self.status_label.setText(f"Models selected for {selected} of {len(self._regions)} regions.")

    def _render_model_rows(self) -> None:
        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._regions:
            placeholder = QLabel("Upload the manifest in step 1 to detect regions and unlock model uploads.")
            placeholder.setObjectName("ModelsPlaceholder")
            placeholder.setWordWrap(True)
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
            file_button = QPushButton("Upload file")
            file_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_file(name))
            layout.addWidget(file_button)
            folder_button = QPushButton("Upload folder")
            folder_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_folder(name))
            layout.addWidget(folder_button)
            self.models_layout.addWidget(row)

    def _refresh_paths(self) -> None:
        self._set_path_label(self.manifest_path_label, self._manifest_source)
        self._set_path_label(self.calibration_path_label, self._calibration_source)
        if self._regions:
            self.regions_label.setText("Detected regions: " + " → ".join(self._regions))
        else:
            self.regions_label.setText("No regions detected yet.")

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
        if self._calibration_source is None:
            QMessageBox.warning(self, "Calibration required", "Complete step 3 by uploading a calibration map.")
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
                self._calibration_source,
                {region: path for region, path in self._model_sources.items() if path is not None},
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
            str(self._manifest_source or ""),
            *(f"{region}\0{self._model_sources.get(region) or ''}" for region in self._regions),
            str(self._calibration_source or ""),
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
                QFrame#ProfileHeader, QFrame#MainAutomationMenu {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 3px;
                }
                QLabel#AutomatedProfileTitle, QLabel#MainAutomationTitle,
                QLabel#ProfileConfigurationTitle, QLabel#ProfileStageTitle {
                    color: {theme.TEXT};
                    font-size: 15px;
                    font-weight: 650;
                }
                QLabel#AutomatedProfileDescription, QLabel#ProfileStageDescription,
                QLabel#DetectedRegionsLabel, QLabel#ModelsPlaceholder, QLabel#ProfileStatusLabel {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QLabel#AutomationPanelTitle {
                    color: {theme.TEXT};
                    font-weight: 650;
                }
                QLabel#VideoCountLabel {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QLabel#FieldLabel, QLabel#RegionName {
                    color: {theme.TEXT};
                    font-weight: 600;
                    min-width: 48px;
                }
                QFrame#VideoDropPanel, QFrame#AutomationConsolePanel {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                QListWidget#AutomationVideoDropList {
                    background: {theme.SURFACE};
                    border: 2px dashed {theme.BORDER};
                    border-radius: 3px;
                    color: {theme.TEXT};
                    padding: 6px;
                }
                QListWidget#AutomationVideoDropList:focus {
                    border-color: {theme.PRIMARY};
                }
                QPlainTextEdit#AutomationConsole {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                    font-family: monospace;
                    font-size: 11px;
                }
                QPushButton#RunPipelineButton {
                    background: {theme.PRIMARY};
                    border-color: {theme.PRIMARY};
                    color: {theme.PRIMARY_TEXT};
                    font-size: 14px;
                    font-weight: 700;
                    min-width: 150px;
                    padding: 9px 16px;
                }
                QPushButton#RunPipelineButton:disabled {
                    background: {theme.PANEL};
                    border-color: {theme.BORDER};
                    color: {theme.CONNECTOR};
                }
                QTabWidget#ProfileConfigurationTabs::pane {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                }
                QTabWidget#ProfileConfigurationTabs QTabBar::tab {
                    background: {theme.PANEL};
                }
                QTabWidget#ProfileConfigurationTabs QTabBar::tab:selected {
                    background: {theme.SURFACE};
                    color: {theme.TEXT};
                    font-weight: 650;
                }
                QWidget#ProfileStagePage {
                    background: {theme.SURFACE};
                }
                QFrame#RegionModelRow {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                QLabel#AssetPath {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                    padding: 4px 6px;
                }
                QPushButton#DeleteProfileButton:hover {
                    border-color: {theme.STATUS_ERROR};
                    color: {theme.STATUS_ERROR};
                }
                QPushButton#SmallProfileButton {
                    min-height: 16px;
                    padding: 4px 7px;
                    font-size: 11px;
                }
                QPushButton#ConfigurationMenuButton {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                    padding: 9px 12px;
                    text-align: left;
                }
                QPushButton#ConfigurationMenuButton:checked {
                    background: {theme.PANEL};
                    border-bottom-left-radius: 0;
                    border-bottom-right-radius: 0;
                }
                QFrame#ProfileConfigurationMenu {
                    background: {theme.SURFACE};
                    border: 0;
                }
                """
            )
        )


class VideoDropList(QListWidget):
    paths_dropped = Signal(object)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._video_paths(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._video_paths(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._video_paths(event.mimeData().urls())
        if not paths:
            event.ignore()
            return
        self.paths_dropped.emit(paths)
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        painter.drawText(
            self.viewport().rect().adjusted(20, 20, -20, -20),
            Qt.AlignCenter | Qt.TextWordWrap,
            "Drag & drop videos here\n\nor use Upload videos",
        )

    @staticmethod
    def _video_paths(urls) -> list[Path]:
        paths = []
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile()).expanduser().resolve()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                paths.append(path)
        return paths
