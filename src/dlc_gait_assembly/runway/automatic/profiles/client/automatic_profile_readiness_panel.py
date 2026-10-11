"""Present satisfied and missing requirements for the selected automatic profile."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class AutomaticProfileReadinessPanel:
    """AutomaticProfileReadinessPanel operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _refresh_profile_readiness(self) -> None:
        gait_enabled = self.view.include_gait_analysis_button.isChecked()
        knee_enabled = self.view.include_knee_correction_button.isChecked()
        selected_models = sum(path is not None for path in self.view.profile_state.model_sources.values())
        total_models = len(self.view.profile_state.regions)
        model_state = "ready" if total_models and selected_models == total_models else "missing"
        model_text = f"{selected_models} / {total_models} selected" if total_models else "Needs manifest"
        self._set_profile_readiness_value(
            "manifest",
            "Selected" if self.view.profile_state.manifest_source is not None else "Required",
            "ready" if self.view.profile_state.manifest_source is not None else "missing",
        )
        self._set_profile_readiness_value("models", model_text, model_state)
        self._set_profile_readiness_value(
            "calibration",
            "Selected"
            if gait_enabled and self.view.profile_state.calibration_source is not None
            else "Required"
            if gait_enabled
            else "Excluded",
            "ready"
            if gait_enabled and self.view.profile_state.calibration_source is not None
            else "missing"
            if gait_enabled
            else "optional",
        )
        self._set_profile_readiness_value(
            "analysis",
            "Selected"
            if gait_enabled and self.view.profile_state.analysis_manifest_source is not None
            else "Required"
            if gait_enabled
            else "Excluded",
            "ready"
            if gait_enabled and self.view.profile_state.analysis_manifest_source is not None
            else "missing"
            if gait_enabled
            else "optional",
        )
        self._set_profile_readiness_value(
            "knee",
            "Selected"
            if knee_enabled and self.view.profile_state.knee_manifest_source is not None
            else "Required"
            if knee_enabled
            else "Excluded",
            "ready"
            if knee_enabled and self.view.profile_state.knee_manifest_source is not None
            else "missing"
            if knee_enabled
            else "optional",
        )

    def _set_profile_readiness_value(self, key: str, text: str, state: str) -> None:
        label = self.view.profile_readiness_values[key]
        if label.text() == text and label.property("readinessState") == state:
            return
        label.setText(text)
        label.setProperty("readinessState", state)
        label.style().unpolish(label)
        label.style().polish(label)


def build_automatic_profile_readiness(self):
    readiness_panel = QFrame()
    readiness_panel.setObjectName("ProfileReadinessPanel")
    readiness_panel.setMinimumWidth(250)
    readiness_panel.setMaximumWidth(300)
    readiness_panel.setMinimumHeight(230)
    readiness_panel.setMaximumHeight(440)
    readiness_layout = QVBoxLayout(readiness_panel)
    readiness_layout.setContentsMargins(12, 12, 12, 12)
    readiness_layout.setSpacing(8)
    readiness_title = QLabel("Profile readiness")
    readiness_title.setObjectName("ProfileReadinessTitle")
    readiness_layout.addWidget(readiness_title)
    self.profile_readiness_values: dict[str, QLabel] = {}
    for key, label_text in (
        ("manifest", "Video settings"),
        ("models", "DLC models"),
        ("calibration", "Calibration"),
        ("analysis", "Gait settings"),
        ("knee", "Knee settings"),
    ):
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("ProfileReadinessLabel")
        row.addWidget(label)
        value = QLabel()
        value.setObjectName("ProfileReadinessValue")
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(value, 1)
        readiness_layout.addLayout(row)
        self.profile_readiness_values[key] = value
    readiness_layout.addStretch(1)
    self.status_label = QLabel("Start with the video processing manifest in step 1.")
    self.status_label.setObjectName("ProfileStatusLabel")
    self.status_label.setWordWrap(True)
    readiness_layout.addWidget(self.status_label)
    self.save_profile_button = QPushButton("Save new profile")
    self.save_profile_button.setObjectName("PrimaryButton")
    self.save_profile_button.setToolTip(
        "Validate the required inputs and save them together as a reusable profile. Saving a profile does not start the pipeline."
    )
    readiness_layout.addWidget(self.save_profile_button)
    return readiness_panel
