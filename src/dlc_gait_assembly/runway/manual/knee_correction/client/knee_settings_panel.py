"""Edit knee markers, segment lengths, direction, confidence, and calibration settings."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.qt_sliding_tabs import install_sliding_tab_bar


def length_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.001, 1000.0)
    spin.setDecimals(3)
    spin.setValue(1.5)
    spin.setSuffix(" cm")
    return spin


def build_knee_settings(self, left_column):
    self.settings_tabs = QTabWidget()
    install_sliding_tab_bar(self.settings_tabs, theme.TOOL_3)
    self.settings_tabs.setObjectName("KneeCorrectionSettingsTabs")
    self.settings_tabs.setDocumentMode(True)
    self.settings_tabs.tabBar().setExpanding(True)
    self.settings_tabs.setMaximumHeight(225)
    calibration_page = QWidget()
    calibration_layout = QGridLayout(calibration_page)
    calibration_layout.setContentsMargins(8, 8, 8, 8)
    self.calibration_map_button = QPushButton("Import calibration map")
    self.calibration_map_label = QLabel("No calibration map selected")
    self.calibration_map_label.setObjectName("MutedLabel")
    calibration_layout.addWidget(self.calibration_map_button, 0, 0)
    calibration_layout.addWidget(self.calibration_map_label, 0, 1)
    self.hip_knee_length = length_spin()
    self.knee_ankle_length = length_spin()
    calibration_layout.addWidget(QLabel("Hip–knee length (femur)"), 1, 0)
    calibration_layout.addWidget(self.hip_knee_length, 1, 1)
    calibration_layout.addWidget(QLabel("Knee–ankle length (tibia/fibula)"), 2, 0)
    calibration_layout.addWidget(self.knee_ankle_length, 2, 1)
    self.settings_tabs.addTab(calibration_page, "Calibration")
    labels_page = QWidget()
    labels_layout = QGridLayout(labels_page)
    labels_layout.setContentsMargins(8, 8, 8, 8)
    self.knee_label_combo = QComboBox()
    self.knee_label_combo.addItem("Auto-detect labels containing 'knee'", None)
    self.knee_label_combo.setEnabled(False)
    labels_layout.addWidget(QLabel("Existing knee label"), 0, 0)
    labels_layout.addWidget(self.knee_label_combo, 0, 1)
    self.generated_knee_label_edit = QLineEdit("knee")
    labels_layout.addWidget(QLabel("Generated knee label"), 1, 0)
    labels_layout.addWidget(self.generated_knee_label_edit, 1, 1)
    self.hip_label_combo = QComboBox()
    self.hip_label_combo.addItem("Auto-detect matching hip", None)
    self.hip_label_combo.setEnabled(False)
    labels_layout.addWidget(QLabel("Hip label"), 2, 0)
    labels_layout.addWidget(self.hip_label_combo, 2, 1)
    self.ankle_label_combo = QComboBox()
    self.ankle_label_combo.addItem("Auto-detect matching ankle", None)
    self.ankle_label_combo.setEnabled(False)
    labels_layout.addWidget(QLabel("Ankle label"), 3, 0)
    labels_layout.addWidget(self.ankle_label_combo, 3, 1)
    self.knee_direction_combo = QComboBox()
    self.knee_direction_combo.addItem("Auto from old knee / continuity", "auto")
    self.knee_direction_combo.addItem("Manual side A", "positive")
    self.knee_direction_combo.addItem("Manual side B", "negative")
    labels_layout.addWidget(QLabel("Knee direction"), 4, 0)
    labels_layout.addWidget(self.knee_direction_combo, 4, 1)
    self.likelihood_threshold = QDoubleSpinBox()
    self.likelihood_threshold.setRange(0.0, 1.0)
    self.likelihood_threshold.setDecimals(2)
    self.likelihood_threshold.setSingleStep(0.05)
    self.likelihood_threshold.setValue(0.0)
    labels_layout.addWidget(QLabel("Hip/ankle likelihood minimum"), 5, 0)
    labels_layout.addWidget(self.likelihood_threshold, 5, 1)
    self.settings_tabs.addTab(labels_page, "Label selection")
    left_column.addWidget(self.settings_tabs)
