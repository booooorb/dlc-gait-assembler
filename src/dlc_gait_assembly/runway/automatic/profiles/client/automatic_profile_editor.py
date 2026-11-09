"""Assemble profile configuration, asset selection, model assignments, and readiness controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_assets_panel import (
    build_automatic_analysis_assets,
    build_automatic_processing_asset,
    build_automatic_stage_switches,
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
    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(10)
    for name, builder in (
        ("stage", build_automatic_stage_switches),
        ("video", build_automatic_processing_asset),
        ("models", build_automatic_model_assignments),
        ("analysis", build_automatic_analysis_assets),
    ):
        section, section_layout = self._stage_page()
        builder(self, section_layout)
        content_layout.addWidget(section)
        setattr(self, f"configuration_{name}_section", section)
    content_layout.addStretch(1)
    self.configuration_scroll = QScrollArea()
    self.configuration_scroll.setObjectName("AutomationSettingsScroll")
    self.configuration_scroll.setFrameShape(QFrame.NoFrame)
    self.configuration_scroll.setWidgetResizable(True)
    self.configuration_scroll.setWidget(content)
    setup_layout = QHBoxLayout()
    setup_layout.setSpacing(10)
    setup_layout.addWidget(self.configuration_scroll, 1)
    setup_layout.addWidget(build_automatic_profile_readiness(self), 0, Qt.AlignTop)
    configuration_layout.addLayout(setup_layout, 1)
    self.workspace_stack.addWidget(configuration_page)
    self.configuration_page = configuration_page
