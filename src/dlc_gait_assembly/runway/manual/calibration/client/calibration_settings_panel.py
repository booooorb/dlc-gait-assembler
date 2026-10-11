"""Edit marker intervals, measurement units, tolerance, and distance method."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


def build_calibration_settings(self, tool_buttons_row, tools_layout):
    self.marker_gap_frame = QFrame()
    self.marker_gap_frame.setObjectName("MarkerGapInline")
    marker_row = QHBoxLayout(self.marker_gap_frame)
    marker_row.setContentsMargins(8, 4, 8, 4)
    marker_row.setSpacing(8)
    marker_row.addWidget(QLabel("Marker gap"))
    self.marker_interval_spin = QDoubleSpinBox()
    self.marker_interval_spin.setRange(1e-06, 100000.0)
    self.marker_interval_spin.setDecimals(4)
    self.marker_interval_spin.setSingleStep(1.0)
    self.marker_interval_spin.setValue(1.0)
    self.marker_interval_spin.setMaximumWidth(92)
    set_tooltip(self.marker_interval_spin, "Measurement represented by the distance between two adjacent markers.")
    marker_row.addWidget(self.marker_interval_spin)
    self.marker_unit_combo = QComboBox()
    self.marker_unit_combo.addItems(["cm", "inches"])
    self.marker_unit_combo.setMaximumWidth(82)
    set_tooltip(self.marker_unit_combo, "Measurement unit for the marker gap.")
    marker_row.addWidget(self.marker_unit_combo)
    tool_buttons_row.addWidget(self.marker_gap_frame)
    tool_buttons_row.addStretch(1)
    tools_layout.addLayout(tool_buttons_row, 1)
    self.settings_frame = QFrame()
    self.settings_frame.setObjectName("InlineSettings")
    self.settings_frame.setMaximumWidth(230)
    settings_layout = QVBoxLayout(self.settings_frame)
    settings_layout.setContentsMargins(8, 4, 8, 4)
    settings_layout.setSpacing(4)
    margin_row = QHBoxLayout()
    margin_row.setContentsMargins(0, 0, 0, 0)
    margin_row.setSpacing(8)
    margin_row.addWidget(QLabel("Margin of error"))
    self.tau_spin = QDoubleSpinBox()
    self.tau_spin.setRange(0.1, 20.0)
    self.tau_spin.setDecimals(2)
    self.tau_spin.setSingleStep(0.25)
    self.tau_spin.setSuffix("%")
    self.tau_spin.setValue(2.0)
    self.tau_spin.setMaximumWidth(82)
    set_tooltip(self.tau_spin, "Margin of calibration error.")
    return (margin_row, settings_layout)
