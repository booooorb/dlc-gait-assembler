"""Edit confidence, filtering, dragging, phase, and stride-quality controls."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QPushButton, QSpinBox

from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_analysis_settings_panel import double_spin
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitFilterPanel:
    """GaitFilterPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _update_confidence_scope(self, *_args) -> None:
        runway = (
            self.view.analysis_type_combo.currentText() == "Spontaneous walking"
            and self.view.stride_method_combo.currentText() == "ALMA (confidence-aware runway)"
        )
        combined = self.view.setup._is_combined_workflow()
        self.view.likelihood_threshold_label.setText(
            "Bottom confidence min"
            if runway and combined
            else "Other detectors' confidence"
            if runway
            else "Likelihood min"
        )
        self.view.likelihood_threshold_spin.setEnabled(not runway or combined)
        self.view.runway_confidence_link.setVisible(runway)
        confidence = self.view.runway_spins["runway_confidence_threshold"].value()
        self.view.runway_confidence_link.setText(f"Runway confidence: {confidence:.2f} · edit in Strides")
        set_tooltip(
            self.view.likelihood_threshold_spin,
            "Confidence for the separate underside R analysis. Updated ALMA contact and joint measurements "
            "use Tracking confidence min in Strides."
            if runway
            else "DLC likelihood threshold for legacy and alternative detectors and underside R analysis. "
            "Updated ALMA has a separate Tracking confidence min in Strides.",
        )

    def _update_rustlab_filter_range(self, *_args) -> None:
        nyquist_limit = max(0.1, self.view.frame_rate_spin.value() / 2.0 - 0.1)
        maximum = min(50.0, nyquist_limit)
        self.view.rustlab_filter_cutoff_spin.setMaximum(maximum)
        set_tooltip(
            self.view.rustlab_filter_cutoff_spin,
            f"Butterworth low-pass cutoff used for all three coordinate views. At {self.view.frame_rate_spin.value():g} fps, it must be at most {maximum:g} Hz.",
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
    self.likelihood_threshold_label = QLabel("Likelihood min")
    filter_layout.addWidget(self.likelihood_threshold_label, 4, 0)
    filter_layout.addWidget(self.likelihood_threshold_spin, 4, 1)
    self.runway_confidence_link = QPushButton()
    self.runway_confidence_link.hide()
    self.runway_confidence_link.clicked.connect(
        lambda: (
            self.settings_tabs.setCurrentWidget(self.stride_detection_tab),
            self.runway_spins["runway_confidence_threshold"].setFocus(),
        )
    )
    filter_layout.addWidget(self.runway_confidence_link, 5, 0, 1, 2)
    filters_tab_layout.addWidget(filter_box)
    stroke_filter_box = QGroupBox("Stroke recovery and coordination")
    self.stroke_filter_box = stroke_filter_box
    stroke_filter_layout = QGridLayout(stroke_filter_box)
    self.stroke_likelihood_spin = double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2)
    self.stroke_likelihood_spin.setEnabled(False)
    set_tooltip(
        self.stroke_likelihood_spin,
        "All extraction types share the ALMA likelihood threshold. Weber et al. excluded labels below 0.95.",
    )
    self.stroke_gap_spin = QSpinBox()
    self.stroke_gap_spin.setRange(0, 60)
    self.stroke_gap_spin.setSpecialValueText("Shared filtering")
    self.stroke_gap_spin.setValue(0)
    self.stroke_gap_spin.setEnabled(False)
    set_tooltip(
        self.stroke_gap_spin,
        "Filtering is shared. New swing measurements require observed samples in their measurement window; bottom coordination excludes long tracking gaps.",
    )
    self.stroke_swing_speed_spin = double_spin(0.1, 100.0, self._defaults.swing_speed_threshold_cm_s, 1)
    self.stroke_min_cycles_spin = QSpinBox()
    self.stroke_min_cycles_spin.setRange(1, 100)
    self.stroke_min_cycles_spin.setValue(self._defaults.minimum_synchronized_cycles)
    set_tooltip(
        self.stroke_swing_speed_spin,
        "Main multiview bottom-paw stance/swing classification uses calibrated cm/s. Weber et al. used 10 cm/s; set each camera's actual FPS in Setup.",
    )
    set_tooltip(
        self.stroke_min_cycles_spin,
        "Minimum valid complete strides per side in the common interval for bilateral asymmetry. CV also requires at least three strides. This is a study QC choice, not a published diagnostic cutoff.",
    )
    stroke_filter_layout.addWidget(QLabel("ALMA likelihood (shared)"), 0, 0)
    stroke_filter_layout.addWidget(self.stroke_likelihood_spin, 0, 1)
    stroke_filter_layout.addWidget(QLabel("Coordinate gap policy"), 1, 0)
    stroke_filter_layout.addWidget(self.stroke_gap_spin, 1, 1)
    stroke_filter_layout.addWidget(QLabel("Swing threshold (cm/s)"), 2, 0)
    stroke_filter_layout.addWidget(self.stroke_swing_speed_spin, 2, 1)
    stroke_filter_layout.addWidget(QLabel("Minimum strides per side"), 3, 0)
    stroke_filter_layout.addWidget(self.stroke_min_cycles_spin, 3, 1)
    self.stroke_paper_settings_button = QPushButton("Use Weber tracking and contact thresholds")
    set_tooltip(
        self.stroke_paper_settings_button,
        "Set shared likelihood to 0.95 and bottom swing speed to 10 cm/s (Weber et al., 2022). Camera FPS and spatial calibration must describe your recordings.",
    )
    self.stroke_paper_settings_button.clicked.connect(
        lambda: (self.likelihood_threshold_spin.setValue(0.95), self.stroke_swing_speed_spin.setValue(10.0))
    )
    stroke_filter_layout.addWidget(self.stroke_paper_settings_button, 4, 0, 1, 2)
    filters_tab_layout.addWidget(stroke_filter_box)
    rustlab_detector_box = QGroupBox("Adapted RustLab1 R · Speed GMM")
    rustlab_detector_box.setObjectName("RustLab1StrideDetectionSettings")
    rustlab_detector_layout = QGridLayout(rustlab_detector_box)
    self.rustlab_likelihood_spin = double_spin(0.0, 1.0, 0.5, 2)
    self.rustlab_likelihood_spin.setSingleStep(0.01)
    self.rustlab_filter_cutoff_spin = double_spin(0.1, 50.0, 6.0, 1)
    self.rustlab_coordinate_gap_spin = QSpinBox()
    self.rustlab_coordinate_gap_spin.setRange(0, 1000)
    self.rustlab_coordinate_gap_spin.setValue(11)
    self.rustlab_min_strides_spin = QSpinBox()
    self.rustlab_min_strides_spin.setRange(1, 1000)
    self.rustlab_min_strides_spin.setValue(1)
    set_tooltip(
        self.rustlab_likelihood_spin,
        "Likelihood cutoff for side-toe Speed GMM timing only. R measurements retain every finite parameter coordinate.",
    )
    set_tooltip(
        self.rustlab_filter_cutoff_spin,
        "Fifth-order zero-phase Butterworth cutoff used by timing and R parameter coordinates.",
    )
    set_tooltip(
        self.rustlab_coordinate_gap_spin,
        "Repair genuinely missing coordinates only within one accepted cycle, with finite endpoints. No extrapolation.",
    )
    set_tooltip(self.rustlab_min_strides_spin, "Minimum complete GMM cycles required independently on each side.")
    for row, (label, control) in enumerate(
        (
            ("Timing likelihood min", self.rustlab_likelihood_spin),
            ("Low-pass cutoff (Hz)", self.rustlab_filter_cutoff_spin),
            ("Coordinate gap repair (frames)", self.rustlab_coordinate_gap_spin),
            ("Minimum cycles per side", self.rustlab_min_strides_spin),
        )
    ):
        rustlab_detector_layout.addWidget(QLabel(label), row, 0)
        rustlab_detector_layout.addWidget(control, row, 1)
    rustlab_detector_box.hide()
    self.rustlab_detector_box = rustlab_detector_box
    filters_tab_layout.addWidget(rustlab_detector_box)
    filters_tab_layout.addStretch(1)
    analysis_tab_layout.addStretch(1)
