"""Assign inspected DeepLabCut model files or project folders to processing regions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from dlc_gait_assembly.runway.automatic.runs.business.automatic_recording_pairing import VIEW_ALIASES, view_role


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
        self._set_model_sources((region,), path)

    def _choose_view_model(self, role: str) -> None:
        regions = tuple(region for region in self.view.profile_state.regions if view_role(region) == role)
        if not regions:
            return
        path = QFileDialog.getExistingDirectory(
            self.view, f"Choose DeepLabCut project for {role} regions", str(Path.home())
        )
        if path:
            self._set_model_sources(regions, Path(path))

    def _set_model_sources(self, regions: tuple[str, ...], path: Path) -> None:
        resolved = path.expanduser().resolve()
        self.view.profile_state.model_sources.update(dict.fromkeys(regions, resolved))
        self._render_model_rows()
        self.view.profile_readiness._refresh_profile_readiness()
        selected = sum(path is not None for path in self.view.profile_state.model_sources.values())
        self.view.status_label.setText(
            f"Models selected for {selected} of {len(self.view.profile_state.regions)} regions."
        )
        workflow = getattr(self.view, "workflow_controller", None)
        if workflow is not None and not workflow.loading:
            workflow.save()

    def _render_model_rows(self) -> None:
        roles = {view_role(region) for region in self.view.profile_state.regions}
        for role, button in self.view.view_model_buttons.items():
            button.setEnabled(role in roles)
        while self.view.models_layout.count():
            item = self.view.models_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.view.profile_state.regions:
            placeholder = QLabel("Video settings required")
            placeholder.setObjectName("ModelsPlaceholder")
            placeholder.setWordWrap(True)
            placeholder.setToolTip(
                "Open Video settings and save the workflow first. Each video region gets its own DeepLabCut model."
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
            region_details = QVBoxLayout()
            region_details.setSpacing(2)
            region_details.addWidget(region_label)
            role = view_role(region)
            role_label = QLabel(f"{role.title()} view" if role else "Custom region")
            role_label.setObjectName("MutedLabel")
            region_details.addWidget(role_label)
            layout.addLayout(region_details)
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


def build_automatic_model_assignments(self, models_content):
    models_content.addWidget(self._field_label("DeepLabCut models by region"))
    view_actions = QHBoxLayout()
    self.view_model_buttons = {}
    for role in VIEW_ALIASES:
        button = QPushButton(f"Assign {role} model…")
        button.setToolTip(f"Choose a trained project for all {role} regions. Individual assignments can be changed below.")
        button.clicked.connect(lambda _checked=False, view_role=role: self.profile_models._choose_view_model(view_role))
        button.setEnabled(False)
        view_actions.addWidget(button)
        self.view_model_buttons[role] = button
    view_actions.addStretch(1)
    models_content.addLayout(view_actions)
    self.models_container = QWidget()
    self.models_layout = QVBoxLayout(self.models_container)
    self.models_layout.setContentsMargins(0, 0, 0, 0)
    self.models_layout.setSpacing(6)
    models_content.addWidget(self.models_container)
