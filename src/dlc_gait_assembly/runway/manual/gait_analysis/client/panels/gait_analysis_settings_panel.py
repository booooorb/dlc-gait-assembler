"""Build treadmill/spontaneous options, limb-scope controls, and analysis-specific settings."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


def double_spin(minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    spin.setDecimals(decimals)
    return spin


def build_gait_stride_detection(self, setup_tab_layout):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
        CONTEXT_MIXTURE_METHOD,
        RUSTLAB1_METHOD,
        STRIDE_METHOD_DESCRIPTIONS,
        STRIDE_METHODS,
    )

    self.stride_detection_box = QGroupBox("Stride detection method")
    layout = QVBoxLayout(self.stride_detection_box)
    self.stride_method_combo = QComboBox()
    self.stride_method_combo.setAccessibleName("Stride detection method")
    self.stride_method_combo.addItems(STRIDE_METHODS)
    self.stride_method_combo.setCurrentText(self._defaults.stride_detection_method)
    self.stride_method_description = QLabel()
    self.stride_method_description.setWordWrap(True)
    self.stride_method_description.setObjectName("MutedLabel")

    def describe_method(*_):
        text = (
            "Treadmill uses the ALMA treadmill detector. Choose Spontaneous walking in Setup "
            f"to select and compare the {len(STRIDE_METHODS)} methods."
            if self.analysis_type_combo.currentText() == "Treadmill"
            else STRIDE_METHOD_DESCRIPTIONS.get(self.stride_method_combo.currentText(), "")
        )
        self.stride_method_description.setText(text)
        self.comparison_rustlab_box.setVisible(self.stride_method_combo.currentText() == RUSTLAB1_METHOD)
        self.mixture_context_box.setVisible(self.stride_method_combo.currentText() == CONTEXT_MIXTURE_METHOD)

    self.refresh_stride_method_description = describe_method
    self.compare_strides_button = QPushButton(f"Compare all {len(STRIDE_METHODS)} stick plots…")
    set_tooltip(
        self.compare_strides_button,
        "Compare the full recording with identical skeleton geometry for every method. Only phase colours and stride boundaries change.",
    )
    layout.addWidget(self.stride_method_combo)
    layout.addWidget(self.stride_method_description)
    self.comparison_rustlab_box = QGroupBox("RustLab1 speed rule")
    rustlab_layout = QGridLayout(self.comparison_rustlab_box)
    self.comparison_rustlab_spins = {}
    for row, (name, title, minimum, maximum, decimals) in enumerate(
        (
            ("stance_speed_threshold_px_frame", "Stance speed max (px/frame)", 0.0, 100.0, 1),
            ("maximum_tracking_speed_px_frame", "Tracking speed max (px/frame)", 0.1, 1000.0, 1),
            ("minimum_stance_frames", "Minimum stance frames", 1, 120, 0),
            ("minimum_swing_frames", "Minimum swing frames", 1, 120, 0),
        )
    ):
        spin = double_spin(minimum, maximum, getattr(self._defaults, name), decimals)
        self.comparison_rustlab_spins[name] = spin
        rustlab_layout.addWidget(QLabel(title), row, 0)
        rustlab_layout.addWidget(spin, row, 1)
    layout.addWidget(self.comparison_rustlab_box)
    self.mixture_context_box = QGroupBox("Neighbouring-frame support")
    context_layout = QVBoxLayout(self.mixture_context_box)
    context_row = QGridLayout()
    self.mixture_context_spin = double_spin(0.0, 250.0, self._defaults.mixture_context_ms, 0)
    self.mixture_context_spin.setSuffix(" ms")
    self.mixture_context_spin.setSingleStep(10.0)
    self.mixture_context_spin.setAccessibleName("Speed mixture neighbour context")
    set_tooltip(
        self.mixture_context_spin,
        "How strongly surrounding frames favour a continuous phase. Larger values suppress brief phase changes; zero disables context. Tracking gaps stop context propagation.",
    )
    context_row.addWidget(QLabel("Neighbour context"), 0, 0)
    context_row.addWidget(self.mixture_context_spin, 0, 1)
    context_layout.addLayout(context_row)
    context_help = QLabel(
        "Starts from Speed mixture. Agreement before and after a frame strengthens its phase estimate. Pale frames have less than 70% phase support. This does not increase the marker’s tracking confidence."
    )
    context_help.setWordWrap(True)
    context_layout.addWidget(context_help)
    layout.addWidget(self.mixture_context_box)
    gap_row = QGridLayout()
    self.detection_gap_spin = QSpinBox()
    self.detection_gap_spin.setRange(-1, 30)
    self.detection_gap_spin.setSpecialValueText("Auto (up to 50 ms)")
    self.detection_gap_spin.setValue(self._defaults.max_interpolation_gap_frames)
    self.detection_gap_spin.setAccessibleName("Bridge tracking gaps")
    set_tooltip(
        self.detection_gap_spin,
        "Auto bridges internal timing-marker gaps lasting at most 50 ms, adjusted to the frame rate. Set 0 for strict detection: any missing timing frame excludes the cycle. Positive values specify frames. Longer gaps and recording edges remain excluded; low-confidence marker positions stay hidden in stick plots.",
    )
    gap_row.addWidget(QLabel("Bridge tracking gaps (frames)"), 0, 0)
    gap_row.addWidget(self.detection_gap_spin, 0, 1)
    layout.addLayout(gap_row)
    self.detection_gap_note = QLabel()
    self.detection_gap_note.setWordWrap(True)
    self.detection_gap_note.setObjectName("MutedLabel")

    def describe_gap(value):
        self.detection_gap_note.setText(
            "Strict: one missing timing frame excludes the entire stride."
            if value == 0
            else "Short gaps can be bridged for stride timing. Longer gaps remain excluded; missing joints stay hidden."
        )

    self.detection_gap_spin.valueChanged.connect(describe_gap)
    describe_gap(self.detection_gap_spin.value())
    layout.addWidget(self.detection_gap_note)
    full_recording_note = QLabel(
        "Every stick plot shows the entire recording. Changing the detector changes stance/swing colours and stride boundaries only. No stride-count limit is applied."
    )
    full_recording_note.setWordWrap(True)
    layout.addWidget(full_recording_note)
    experimental_note = QLabel(
        "Compare against the video before choosing a method. The added experimental methods estimate contact from motion; detection counts can differ."
    )
    experimental_note.setWordWrap(True)
    experimental_note.setObjectName("MutedLabel")
    layout.addWidget(experimental_note)
    layout.addWidget(self.compare_strides_button)
    self.stride_method_combo.currentTextChanged.connect(describe_method)
    self.analysis_type_combo.currentTextChanged.connect(describe_method)
    describe_method()
    setup_tab_layout.addWidget(self.stride_detection_box)


def build_gait_movement_settings(self, analysis_tab_layout):
    movement_box = QGroupBox("Movement analysis settings")
    self.movement_box = movement_box
    movement_layout = QGridLayout(movement_box)
    movement_layout.setHorizontalSpacing(12)
    movement_layout.setVerticalSpacing(4)
    self.filter_cutoff_spin = double_spin(0.1, 50.0, self._defaults.filter_cutoff, 1)
    self.direction_combo = QComboBox()
    self.direction_combo.addItems(["Auto-detect", "Left-to-Right", "Right-to-Left"])
    if self._defaults.right_to_left == "auto":
        self.direction_combo.setCurrentText("Auto-detect")
    elif self._defaults.right_to_left:
        self.direction_combo.setCurrentText("Right-to-Left")
    else:
        self.direction_combo.setCurrentText("Left-to-Right")
    self.drag_clearance_spin = double_spin(0.01, 2.0, self._defaults.drag_clearance_cm, 2)
    self.drag_frames_spin = QSpinBox()
    self.drag_frames_spin.setRange(1, 10)
    self.drag_frames_spin.setValue(self._defaults.drag_min_consecutive_frames)
    set_tooltip(self.direction_combo, "Expected walking direction, or automatic direction detection.")
    set_tooltip(self.drag_clearance_spin, "Toe clearance threshold used by drag detection.")
    set_tooltip(self.drag_frames_spin, "Number of consecutive frames required for drag detection.")
    set_tooltip(self.filter_cutoff_spin, "Low-pass filter cutoff frequency in Hz.")
    movement_layout.addWidget(QLabel("Walking direction"), 0, 0)
    movement_layout.addWidget(self.direction_combo, 0, 1)
    movement_layout.addWidget(QLabel("Drag clearance threshold (cm)"), 1, 0)
    movement_layout.addWidget(self.drag_clearance_spin, 1, 1)
    movement_layout.addWidget(QLabel("Drag detection sensitivity (frames)"), 2, 0)
    movement_layout.addWidget(self.drag_frames_spin, 2, 1)
    movement_layout.addWidget(QLabel("Low-pass filter cutoff (Hz)"), 3, 0)
    movement_layout.addWidget(self.filter_cutoff_spin, 3, 1)
    analysis_tab_layout.addWidget(movement_box)
    spontaneous_box = QGroupBox("Spontaneous walking options")
    spontaneous_layout = QVBoxLayout(spontaneous_box)
    self.no_outlier_checkbox = QCheckBox("No outlier filter")
    self.no_outlier_checkbox.setChecked(self._defaults.no_outlier_filter)
    self.dragging_filter_checkbox = QCheckBox("Dragging filter")
    self.dragging_filter_checkbox.setChecked(self._defaults.dragging_filter)
    set_tooltip(self.no_outlier_checkbox, "Disable the spontaneous-walking outlier filter.")
    set_tooltip(self.dragging_filter_checkbox, "Enable dragging detection/filtering for spontaneous walking.")
    spontaneous_layout.addWidget(self.no_outlier_checkbox)
    spontaneous_layout.addWidget(self.dragging_filter_checkbox)
    self.spontaneous_box = spontaneous_box
    analysis_tab_layout.addWidget(spontaneous_box)
