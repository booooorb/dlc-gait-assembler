"""Assemble profile configuration, asset selection, model assignments, and readiness controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_assets_panel import (
    build_automatic_analysis_assets,
    build_automatic_processing_asset,
)
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_list import build_automatic_profile_list
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_models_panel import (
    build_automatic_model_assignments,
)
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_readiness_panel import (
    build_automatic_profile_readiness,
)


def build_automatic_profile_editor(self):
    configuration_page = QWidget()
    configuration_page.setObjectName("ProfileConfigurationPage")
    configuration_layout = QVBoxLayout(configuration_page)
    configuration_layout.setContentsMargins(0, 0, 0, 0)
    configuration_layout.setSpacing(8)
    build_automatic_profile_list(self, configuration_layout)
    manifest_page = build_automatic_processing_asset(self)
    build_automatic_model_assignments(self, manifest_page)
    build_automatic_analysis_assets(self)
    readiness_panel = build_automatic_profile_readiness(self)
    setup_layout = QHBoxLayout()
    setup_layout.setSpacing(10)
    setup_layout.addWidget(self.configuration_tabs, 1)
    setup_layout.addWidget(readiness_panel)
    self.configuration_tabs.setMinimumHeight(230)
    self.configuration_tabs.setMaximumHeight(440)
    configuration_layout.addLayout(setup_layout)
    configuration_layout.addStretch(1)
    self.workspace_stack.addWidget(configuration_page)
    self.configuration_page = configuration_page
