"""Build cohort analysis choices and output-destination controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QScrollArea

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


def build_cohort_options(self, controls, controls_layout, splitter):
    settings_box = QGroupBox("Analysis")
    settings_layout = QGridLayout(settings_box)
    self.pca_checkbox = QCheckBox("PCA on animal-session summaries")
    self.pca_checkbox.setChecked(True)
    self.random_forest_checkbox = QCheckBox("Animal-grouped Random Forest")
    self.random_forest_checkbox.setChecked(True)
    self.mixed_effects_checkbox = QCheckBox("Mixed-effects primary-outcome models")
    self.mixed_effects_checkbox.setChecked(True)
    self.output_edit = QLineEdit(str(self.workspace.manual / "pca_random_forest"))
    output_button = QPushButton("Browse")
    output_button.clicked.connect(self.controller._choose_output)
    settings_layout.addWidget(self.pca_checkbox, 0, 0, 1, 2)
    settings_layout.addWidget(self.random_forest_checkbox, 1, 0, 1, 2)
    settings_layout.addWidget(self.mixed_effects_checkbox, 2, 0, 1, 2)
    settings_layout.addWidget(QLabel("Output folder"), 3, 0, 1, 3)
    settings_layout.addWidget(self.output_edit, 4, 0, 1, 2)
    settings_layout.addWidget(output_button, 4, 2)
    controls_layout.addWidget(settings_box)
    self.run_button = QPushButton("Run cohort analysis")
    self.run_button.setObjectName("PrimaryButton")
    self.run_button.clicked.connect(self.controller._run_analysis)
    set_tooltip(self.run_button, "Run redundancy control, PCA, grouped Random Forest, and repeated-measures models.")
    controls_layout.addWidget(self.run_button)
    controls_layout.addStretch(1)
    self.controls_scroll = QScrollArea()
    self.controls_scroll.setObjectName("CohortControlsScroll")
    self.controls_scroll.setWidgetResizable(True)
    self.controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.controls_scroll.setMinimumWidth(410)
    self.controls_scroll.setMaximumWidth(540)
    self.controls_scroll.setWidget(controls)
    splitter.addWidget(self.controls_scroll)
