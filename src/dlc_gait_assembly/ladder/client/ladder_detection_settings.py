"""Build Ladder method, marker, confidence, and detection-threshold controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar
from dlc_gait_assembly.shared.client.qt_sliding_tabs import install_sliding_tab_bar


def double_spin(minimum, maximum, value, decimals, step) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setValue(value)
    return spin


def build_ladder_settings(self, controls_layout):
    settings_box = QGroupBox("Detection settings")
    settings_box_layout = QVBoxLayout(settings_box)
    self.settings_tabs = QTabWidget()
    install_sliding_tab_bar(self.settings_tabs, theme.TOOL_2)
    left_settings_tab = QWidget()
    settings_layout = QGridLayout(left_settings_tab)
    self.method_combo = QComboBox()
    self.method_combo.addItems(["Deviation", "Baseline", "Threshold"])
    self.likelihood_spin = double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2, 0.05)
    self.depth_spin = double_spin(0.0, 1.0, self._defaults.depth_threshold, 2, 0.05)
    self.threshold_spin = double_spin(-100000.0, 100000.0, self._defaults.threshold or 0.0, 2, 1.0)
    self.auto_threshold_checkbox = QCheckBox("Automatic")
    self.auto_threshold_checkbox.setChecked(self._defaults.threshold is None)
    self.frame_rate_spin = double_spin(1.0, 1000.0, self._defaults.frame_rate, 2, 1.0)
    settings_layout.addWidget(QLabel("Method"), 0, 0)
    settings_layout.addWidget(self.method_combo, 0, 1, 1, 2)
    settings_layout.addWidget(QLabel("Likelihood minimum"), 1, 0)
    settings_layout.addWidget(self.likelihood_spin, 1, 1, 1, 2)
    settings_layout.addWidget(QLabel("Recovery fraction"), 2, 0)
    settings_layout.addWidget(self.depth_spin, 2, 1, 1, 2)
    settings_layout.addWidget(QLabel("Y threshold"), 3, 0)
    settings_layout.addWidget(self.threshold_spin, 3, 1)
    settings_layout.addWidget(self.auto_threshold_checkbox, 3, 2)
    settings_layout.addWidget(QLabel("Frame rate (fps)"), 4, 0)
    settings_layout.addWidget(self.frame_rate_spin, 4, 1, 1, 2)
    set_tooltip(
        self.depth_spin, "Required recovery relative to the preceding footfall depth before ALMA starts a new event."
    )
    right_settings_tab = QWidget()
    right_settings_layout = QGridLayout(right_settings_tab)
    self.right_method_combo = QComboBox()
    self.right_method_combo.addItems(["Deviation", "Baseline", "Threshold"])
    self.right_likelihood_spin = double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2, 0.05)
    self.right_depth_spin = double_spin(0.0, 1.0, self._defaults.depth_threshold, 2, 0.05)
    self.right_threshold_spin = double_spin(-100000.0, 100000.0, self._defaults.threshold or 0.0, 2, 1.0)
    self.right_auto_threshold_checkbox = QCheckBox("Automatic")
    self.right_auto_threshold_checkbox.setChecked(self._defaults.threshold is None)
    self.right_frame_rate_spin = double_spin(1.0, 1000.0, self._defaults.frame_rate, 2, 1.0)
    right_settings_layout.addWidget(QLabel("Method"), 0, 0)
    right_settings_layout.addWidget(self.right_method_combo, 0, 1, 1, 2)
    right_settings_layout.addWidget(QLabel("Likelihood minimum"), 1, 0)
    right_settings_layout.addWidget(self.right_likelihood_spin, 1, 1, 1, 2)
    right_settings_layout.addWidget(QLabel("Recovery fraction"), 2, 0)
    right_settings_layout.addWidget(self.right_depth_spin, 2, 1, 1, 2)
    right_settings_layout.addWidget(QLabel("Y threshold"), 3, 0)
    right_settings_layout.addWidget(self.right_threshold_spin, 3, 1)
    right_settings_layout.addWidget(self.right_auto_threshold_checkbox, 3, 2)
    right_settings_layout.addWidget(QLabel("Frame rate (fps)"), 4, 0)
    right_settings_layout.addWidget(self.right_frame_rate_spin, 4, 1, 1, 2)
    set_tooltip(self.right_depth_spin, "Right-camera recovery fraction; it can differ from the left camera.")
    self.settings_tabs.addTab(left_settings_tab, "Camera / left")
    self.settings_tabs.addTab(right_settings_tab, "Right camera")
    settings_box_layout.addWidget(self.settings_tabs)
    controls_layout.addWidget(settings_box)
    bodyparts_box = QGroupBox("Paw markers")
    bodyparts_layout = QVBoxLayout(bodyparts_box)
    self.bodyparts_tabs = QTabWidget()
    install_sliding_tab_bar(self.bodyparts_tabs, theme.TOOL_2)
    self.bodyparts_list = QListWidget()
    self.bodyparts_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    self.right_bodyparts_list = QListWidget()
    self.right_bodyparts_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    self.bodyparts_tabs.addTab(self.bodyparts_list, "Camera / left")
    self.bodyparts_tabs.addTab(self.right_bodyparts_list, "Right camera")
    bodyparts_layout.addWidget(self.bodyparts_tabs)
    controls_layout.addWidget(bodyparts_box, 1)
    self.run_button = QPushButton("Run ALMA ladder detection")
    self.run_button.setObjectName("PrimaryButton")
    self.progress = DynamicProgressBar(accent_role="tool_1")
    self.progress.setRange(0, 100)
    self.status_label = QLabel("Choose a DeepLabCut coordinate CSV to begin.")
    self.status_label.setWordWrap(True)
    controls_layout.addWidget(self.run_button)
    controls_layout.addWidget(self.progress)
    controls_layout.addWidget(self.status_label)
