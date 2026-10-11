"""Assign inspected DeepLabCut model files or project folders to processing regions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


class AutomaticProfileModelsPanel:
    """AutomaticProfileModelsPanel operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_model_file(self, region: str) -> None:
        (path, _) = QFileDialog.getOpenFileName(
            self.view,
            f"Choose DeepLabCut config for {region}",
            str(Path.home()),
            "DeepLabCut config (config.yaml);;YAML files (*.yaml);;All files (*)",
        )
        if path:
            self._set_model_source(region, Path(path))

    def _choose_model_folder(self, region: str) -> None:
        path = QFileDialog.getExistingDirectory(
            self.view, f"Choose DeepLabCut model folder for {region}", str(Path.home())
        )
        if path:
            self._set_model_source(region, Path(path))

    def _set_model_source(self, region: str, path: Path) -> None:
        if region not in self.view.profile_state.model_sources:
            raise ValueError(f"Unknown manifest region: {region}")
        self.view.profile_state.model_sources[region] = path.expanduser().resolve()
        self._render_model_rows()
        self.view.profile_readiness._refresh_profile_readiness()
        selected = sum(path is not None for path in self.view.profile_state.model_sources.values())
        self.view.status_label.setText(
            f"Models selected for {selected} of {len(self.view.profile_state.regions)} regions."
        )

    def _render_model_rows(self) -> None:
        while self.view.models_layout.count():
            item = self.view.models_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.view.profile_state.regions:
            placeholder = QLabel("Manifest required")
            placeholder.setObjectName("ModelsPlaceholder")
            placeholder.setWordWrap(True)
            placeholder.setToolTip(
                "Complete step 1 first. The manifest supplies the region names needed to create one DeepLabCut model slot per region."
            )
            self.view.models_layout.addWidget(placeholder)
            return
        for region in self.view.profile_state.regions:
            row = QFrame()
            row.setObjectName("RegionModelRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(8)
            region_label = QLabel(region)
            region_label.setObjectName("RegionName")
            region_label.setMinimumWidth(110)
            layout.addWidget(region_label)
            model_path = self.view.profile_state.model_sources.get(region)
            path_label = self.view._path_label()
            path_label.setText(str(model_path) if model_path is not None else "Model required")
            path_label.setToolTip(str(model_path) if model_path is not None else "")
            layout.addWidget(path_label, 1)
            file_button = QPushButton("Choose config")
            file_button.setToolTip(f"Choose config.yaml from the trained DeepLabCut project for {region}.")
            file_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_file(name))
            layout.addWidget(file_button)
            folder_button = QPushButton("Choose project")
            folder_button.setToolTip(f"Choose the complete trained DeepLabCut project folder for {region}.")
            folder_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_folder(name))
            layout.addWidget(folder_button)
            self.view.models_layout.addWidget(row)


def build_automatic_model_assignments(self, manifest_page):
    self.configuration_tabs.addTab(manifest_page, "1  Video settings")
    self.configuration_tabs.setTabToolTip(
        0,
        "Choose the video settings or processing manifest that defines cropping, trimming, enhancement settings, and named regions.",
    )
    (models_page, models_content) = self._stage_page()
    self.models_container = QWidget()
    self.models_layout = QVBoxLayout(self.models_container)
    self.models_layout.setContentsMargins(0, 0, 0, 0)
    self.models_layout.setSpacing(6)
    self.models_scroll = QScrollArea()
    self.models_scroll.setObjectName("ProfileModelsScroll")
    self.models_scroll.setWidgetResizable(True)
    self.models_scroll.setFrameShape(QFrame.NoFrame)
    self.models_scroll.setWidget(self.models_container)
    models_content.addWidget(self.models_scroll, 1)
    self.configuration_tabs.addTab(models_page, "2  DLC models")
    self.configuration_tabs.setTabToolTip(
        1, "Assign one trained DeepLabCut model file or model folder to each region detected in step 1."
    )
