"""Edit confidence, filtering, dragging, phase, and stride-quality controls."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel, QSpinBox

from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_analysis_settings_panel import double_spin
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_setup_panel import RUSTLAB1_PAW_LABELS
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitFilterPanel:
    """GaitFilterPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _update_rustlab_filter_range(self, *_args) -> None:
        nyquist_limit = max(0.1, self.view.frame_rate_spin.value() / 2.0 - 0.1)
        maximum = min(50.0, nyquist_limit)
        self.view.rustlab_filter_cutoff_spin.setMaximum(maximum)
        set_tooltip(
            self.view.rustlab_filter_cutoff_spin,
            f"Butterworth low-pass cutoff used for all three coordinate views. At {self.view.frame_rate_spin.value():g} fps, it must be at most {maximum:g} Hz.",
        )

    def _update_rustlab_speed_range(self, *_args) -> None:
        minimum = self.view.rustlab_stance_speed_spin.value() + 0.1
        self.view.rustlab_max_tracking_speed_spin.setMinimum(minimum)
        set_tooltip(
            self.view.rustlab_max_tracking_speed_spin,
            f"Reject candidate strides containing implausible paw speeds. The upstream notebook rejects phases at 100 px/frame or more; this value must remain above the {self.view.rustlab_stance_speed_spin.value():g} px/frame stance threshold.",
        )


def build_gait_filters(self, analysis_tab_layout, filters_tab_layout):
    filter_box = QGroupBox("Stride filtering (optional)")
    self.filter_box = filter_box
    filter_layout = QGridLayout(filter_box)
    filter_layout.setHorizontalSpacing(12)
    filter_layout.setVerticalSpacing(4)
    self.step_height_min_spin = double_spin(0.0, 5.0, self._defaults.step_height_min_cm, 2)
    self.step_height_max_spin = double_spin(0.0, 5.0, self._defaults.step_height_max_cm, 2)
    self.stride_length_min_spin = double_spin(0.0, 20.0, self._defaults.stride_length_min_cm, 2)
    self.stride_length_max_spin = double_spin(0.0, 20.0, self._defaults.stride_length_max_cm, 2)
    self.likelihood_threshold_spin = double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2)
    self.likelihood_threshold_spin.setSingleStep(0.05)
    set_tooltip(self.step_height_min_spin, "Minimum accepted step height in centimeters.")
    set_tooltip(self.step_height_max_spin, "Maximum accepted step height in centimeters.")
    set_tooltip(self.stride_length_min_spin, "Minimum accepted stride length in centimeters.")
    set_tooltip(self.stride_length_max_spin, "Maximum accepted stride length in centimeters.")
    set_tooltip(
        self.likelihood_threshold_spin,
        "Minimum DLC likelihood for frames used directly by ALMA. Set to 0 to disable confidence filtering.",
    )
    filter_layout.addWidget(QLabel("Step height min (cm)"), 0, 0)
    filter_layout.addWidget(self.step_height_min_spin, 0, 1)
    filter_layout.addWidget(QLabel("Step height max (cm)"), 1, 0)
    filter_layout.addWidget(self.step_height_max_spin, 1, 1)
    filter_layout.addWidget(QLabel("Stride length min (cm)"), 2, 0)
    filter_layout.addWidget(self.stride_length_min_spin, 2, 1)
    filter_layout.addWidget(QLabel("Stride length max (cm)"), 3, 0)
    filter_layout.addWidget(self.stride_length_max_spin, 3, 1)
    filter_layout.addWidget(QLabel("Likelihood min"), 4, 0)
    filter_layout.addWidget(self.likelihood_threshold_spin, 4, 1)
    filters_tab_layout.addWidget(filter_box)
    stroke_filter_box = QGroupBox("Synchronized stroke-pilot QC")
    self.stroke_filter_box = stroke_filter_box
    stroke_filter_layout = QGridLayout(stroke_filter_box)
    self.stroke_likelihood_spin = double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2)
    self.stroke_likelihood_spin.setEnabled(False)
    set_tooltip(self.stroke_likelihood_spin, "Synchronized outputs use the same likelihood threshold as ALMA.")
    self.stroke_gap_spin = QSpinBox()
    self.stroke_gap_spin.setRange(0, 60)
    self.stroke_gap_spin.setSpecialValueText("ALMA full")
    self.stroke_gap_spin.setValue(0)
    self.stroke_gap_spin.setEnabled(False)
    set_tooltip(self.stroke_gap_spin, "Synchronized outputs use ALMA's linear interpolation in both directions.")
    self.stroke_swing_speed_spin = double_spin(0.1, 100.0, self._defaults.swing_speed_threshold_cm_s, 1)
    self.stroke_min_cycles_spin = QSpinBox()
    self.stroke_min_cycles_spin.setRange(1, 100)
    self.stroke_min_cycles_spin.setValue(self._defaults.minimum_synchronized_cycles)
    stroke_filter_layout.addWidget(QLabel("ALMA likelihood (shared)"), 0, 0)
    stroke_filter_layout.addWidget(self.stroke_likelihood_spin, 0, 1)
    stroke_filter_layout.addWidget(QLabel("Coordinate gap policy"), 1, 0)
    stroke_filter_layout.addWidget(self.stroke_gap_spin, 1, 1)
    stroke_filter_layout.addWidget(QLabel("Swing threshold (cm/s)"), 2, 0)
    stroke_filter_layout.addWidget(self.stroke_swing_speed_spin, 2, 1)
    stroke_filter_layout.addWidget(QLabel("Minimum synchronized cycles"), 3, 0)
    stroke_filter_layout.addWidget(self.stroke_min_cycles_spin, 3, 1)
    filters_tab_layout.addWidget(stroke_filter_box)
    rustlab_detector_box = QGroupBox("Standalone RustLab1 stride detection")
    rustlab_detector_box.setObjectName("RustLab1StrideDetectionSettings")
    rustlab_detector_layout = QGridLayout(rustlab_detector_box)
    self.rustlab_reference_paw_combo = QComboBox()
    self.rustlab_reference_paw_combo.addItems(tuple(RUSTLAB1_PAW_LABELS))
    self.rustlab_likelihood_spin = double_spin(0.0, 1.0, 0.95, 2)
    self.rustlab_likelihood_spin.setSingleStep(0.01)
    self.rustlab_filter_cutoff_spin = double_spin(0.1, 50.0, self._defaults.filter_cutoff, 1)
    self.rustlab_stance_speed_spin = double_spin(0.0, 100.0, 7.0, 1)
    self.rustlab_max_tracking_speed_spin = double_spin(0.1, 1000.0, 100.0, 1)
    self.rustlab_min_stance_spin = QSpinBox()
    self.rustlab_min_stance_spin.setRange(1, 120)
    self.rustlab_min_stance_spin.setValue(1)
    self.rustlab_min_swing_spin = QSpinBox()
    self.rustlab_min_swing_spin.setRange(1, 120)
    self.rustlab_min_swing_spin.setValue(1)
    self.rustlab_min_strides_spin = QSpinBox()
    self.rustlab_min_strides_spin.setRange(1, 1000)
    self.rustlab_min_strides_spin.setValue(1)
    set_tooltip(
        self.rustlab_reference_paw_combo, "Bottom-view paw whose stance onsets define standalone RustLab1 strides."
    )
    set_tooltip(
        self.rustlab_likelihood_spin,
        "Minimum DLC likelihood for standalone RustLab1 coordinates. The upstream notebook uses 0.95.",
    )
    set_tooltip(
        self.rustlab_filter_cutoff_spin,
        "Butterworth low-pass cutoff used for all three coordinate views; it must be below half the frame rate.",
    )
    set_tooltip(
        self.rustlab_stance_speed_spin, "RustLab1 stance rule in pixels per frame. The upstream notebook uses 7."
    )
    set_tooltip(
        self.rustlab_max_tracking_speed_spin,
        "Reject candidate strides containing implausible paw speeds. The upstream notebook rejects phases at 100 px/frame or more.",
    )
    set_tooltip(
        self.rustlab_min_stance_spin, "Minimum consecutive stance frames; raise this to suppress short false contacts."
    )
    set_tooltip(self.rustlab_min_swing_spin, "Minimum consecutive swing frames between stance periods.")
    set_tooltip(
        self.rustlab_min_strides_spin, "Minimum number of complete, QC-accepted strides required for each trial."
    )
    rustlab_detector_layout.addWidget(QLabel("Reference paw"), 0, 0)
    rustlab_detector_layout.addWidget(self.rustlab_reference_paw_combo, 0, 1)
    rustlab_detector_layout.addWidget(QLabel("Likelihood min"), 1, 0)
    rustlab_detector_layout.addWidget(self.rustlab_likelihood_spin, 1, 1)
    rustlab_detector_layout.addWidget(QLabel("Low-pass cutoff (Hz)"), 2, 0)
    rustlab_detector_layout.addWidget(self.rustlab_filter_cutoff_spin, 2, 1)
    rustlab_detector_layout.addWidget(QLabel("Stance speed max (px/frame)"), 3, 0)
    rustlab_detector_layout.addWidget(self.rustlab_stance_speed_spin, 3, 1)
    rustlab_detector_layout.addWidget(QLabel("Tracking speed max (px/frame)"), 4, 0)
    rustlab_detector_layout.addWidget(self.rustlab_max_tracking_speed_spin, 4, 1)
    rustlab_detector_layout.addWidget(QLabel("Minimum stance frames"), 5, 0)
    rustlab_detector_layout.addWidget(self.rustlab_min_stance_spin, 5, 1)
    rustlab_detector_layout.addWidget(QLabel("Minimum swing frames"), 6, 0)
    rustlab_detector_layout.addWidget(self.rustlab_min_swing_spin, 6, 1)
    rustlab_detector_layout.addWidget(QLabel("Minimum complete strides"), 7, 0)
    rustlab_detector_layout.addWidget(self.rustlab_min_strides_spin, 7, 1)
    rustlab_detector_box.hide()
    self.rustlab_detector_box = rustlab_detector_box
    filters_tab_layout.addWidget(rustlab_detector_box)
    filters_tab_layout.addStretch(1)
    analysis_tab_layout.addStretch(1)
