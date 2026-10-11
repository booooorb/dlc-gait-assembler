"""Edit gait workflow, single/multi-view input, and recording setup controls."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    MULTI_SIDE_VIEW_MODE_LABEL,
    SINGLE_SIDE_VIEW_MODE_LABEL,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitSetupPanel:
    """GaitSetupPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _is_rustlab1_workflow(self) -> bool:
        return self.view.workflow_combo.currentText() == RUSTLAB1_WORKFLOW_LABEL

    def _set_settings_tab_visible(self, index: int, visible: bool) -> None:
        self.view.settings_tabs.setTabVisible(index, visible)
        row_index = next(i for i, indices in enumerate(self.view.settings_navigation_indices) if index in indices)
        local_index = self.view.settings_navigation_indices[row_index].index(index)
        self.view.settings_section_rows[row_index].setTabVisible(local_index, visible)

    def _set_settings_tab_text(self, index: int, text: str) -> None:
        self.view.settings_tabs.setTabText(index, text)
        row_index = next(i for i, indices in enumerate(self.view.settings_navigation_indices) if index in indices)
        local_index = self.view.settings_navigation_indices[row_index].index(index)
        self.view.settings_section_rows[row_index].setTabText(local_index, text)

    def _update_workflow(self) -> None:
        rustlab1_only = self._is_rustlab1_workflow()
        if rustlab1_only and self.view.input_mode_combo.currentText() != MULTI_SIDE_VIEW_MODE_LABEL:
            self.view.input_mode_combo.setCurrentText(MULTI_SIDE_VIEW_MODE_LABEL)
        if rustlab1_only and self.view.settings_tabs.currentIndex() in {2, 4, 7}:
            self.view.settings_tabs.setCurrentIndex(0)
        self._set_settings_tab_visible(7, not rustlab1_only)
        self._set_settings_tab_visible(2, not rustlab1_only)
        self._set_settings_tab_visible(4, not rustlab1_only)
        self._set_settings_tab_text(3, "Stride QC" if rustlab1_only else "Filters")
        self.view.input_mode_combo.setEnabled(not rustlab1_only)
        self.view.analysis_type_combo.setEnabled(not rustlab1_only)
        self.view.input_mode_label.setVisible(not rustlab1_only)
        self.view.input_mode_combo.setVisible(not rustlab1_only)
        self.view.analysis_type_label.setVisible(not rustlab1_only)
        self.view.analysis_type_combo.setVisible(not rustlab1_only)
        self.view.setup_box.setTitle("RustLab1 recording" if rustlab1_only else "Experimental setup")
        self.view.stride_detection_box.setTitle("Stick-plot preview" if rustlab1_only else "Stride detection method")
        self.view.stride_method_combo.setVisible(not rustlab1_only)
        self.view.stride_method_description.setVisible(not rustlab1_only)
        self.view.compare_strides_button.setVisible(not rustlab1_only)
        self.view.comparison_rustlab_box.setVisible(
            not rustlab1_only and self.view.stride_method_combo.currentText() == "RustLab1 (bottom paw)"
        )
        self.view.speed_box.setTitle("Recording timing" if rustlab1_only else "Treadmill speed and calibration")
        self.view.view_timing_box.setVisible(not rustlab1_only)
        self.view.workspace_title.setText("RustLab1 standalone analysis" if rustlab1_only else "Runway analysis")
        self.view.file_box.setTitle(
            "Three-view RustLab1 input and output" if rustlab1_only else "Multi-view ALMA input and output"
        )
        for control in (self.view.direction_combo, self.view.drag_clearance_spin, self.view.drag_frames_spin):
            control.setEnabled(not rustlab1_only)
        self.view.filter_box.setVisible(not rustlab1_only)
        self.view.stroke_filter_box.setVisible(not rustlab1_only)
        self.view.rustlab_detector_box.setVisible(rustlab1_only)
        self.view.output_options_box.setVisible(not rustlab1_only)
        self.view.parameter_selection.set_source_filter("RustLab1" if rustlab1_only else None)
        self.view.rustlab_box.setTitle("Standalone RustLab1 outputs" if rustlab1_only else "RustLab1 multi-view")
        self.view.rustlab1_checkbox.setVisible(not rustlab1_only)
        self.view.rustlab_box.setVisible(rustlab1_only)
        self.view.rustlab_standalone_figures_checkbox.setVisible(rustlab1_only)
        set_tooltip(
            self.view.rustlab_standalone_figures_checkbox,
            "Save supported RustLab1 figures; retired bottom-center angles are excluded.",
        )
        set_tooltip(
            self.view.output_folder_edit,
            "Folder where standalone RustLab1 outputs will be saved."
            if rustlab1_only
            else "Folder where ALMA gait-analysis outputs will be saved.",
        )
        self.view.rustlab_status_label.setText(
            "Standalone mode uses bottom-paw timing and exports RustLab1 results. Choose ALMA + post-ALMA features for combined ALMA and RustLab1 outputs."
            if rustlab1_only
            else "RustLab1 needs paired left, right, and bottom CSVs."
        )
        self.view.export_manifest_button.setEnabled(not rustlab1_only)
        self.view.export_manifest_button.setVisible(not rustlab1_only)
        self.view.bottom_y_pixels_per_cm_label.setVisible(not rustlab1_only)
        self.view.bottom_y_pixels_per_cm_spin.setVisible(not rustlab1_only)
        self.view.bottom_x_pixels_per_cm_label.setText(
            "Bottom X pixels per cm (optional)" if rustlab1_only else "Bottom X pixels per cm"
        )
        set_tooltip(
            self.view.bottom_x_pixels_per_cm_spin,
            "Optional bottom-view horizontal calibration override for standalone stride length."
            if rustlab1_only
            else "Bottom-view horizontal calibration. Set both bottom values for synchronized stroke outputs.",
        )
        self.view.preview_button.setText(
            "1. Generate RustLab1 stick-plot preview" if rustlab1_only else "1. Generate stick-plot preview"
        )
        self.view.run_button.setText("2. Run RustLab1 analysis" if rustlab1_only else "2. Analyze and save outputs")
        set_tooltip(
            self.view.preview_button,
            "Detect RustLab1 stance-onset strides from the selected three-view set and preview the side-view stick plots."
            if rustlab1_only
            else "Generate and inspect an ALMA stick plot from the selected left-view CSV before running the full analysis.",
            "Ctrl+P",
        )
        set_tooltip(
            self.view.run_button,
            "Run standalone RustLab1 analysis after reviewing its stride preview."
            if rustlab1_only
            else "Run ALMA gait analysis after reviewing the stick plot.",
            "Ctrl+R",
        )
        self._update_analysis_mode()
        self._update_limb_scope()
        self.view.controller._invalidate_stickplot_preview()

    def _update_input_mode(self) -> None:
        three_view = self.view.inputs._is_three_view_mode()
        self.view.view_calibration_box.setEnabled(three_view)
        self.view.view_timing_box.setEnabled(three_view)
        self.view.view_calibration_hint.setText(
            "Each camera uses its own map or pixels per cm. Zero side values use the shared/reference calibration."
            if three_view
            else "Choose Multi side view above to calibrate each camera. Single side view uses the Calibration tab."
        )
        self.view.parameter_selection.set_multiside(three_view)
        self.view.parameter_reference.set_multiside(three_view)
        self.view.view_set_table.setVisible(three_view)
        self.view.view_set_status_label.setVisible(three_view)
        self.view.edit_pairing_button.setVisible(three_view)
        self.view.label_matching_button.setVisible(three_view)
        self.view.file_list.setVisible(not three_view)
        self.view.rustlab1_checkbox.setEnabled(three_view)
        self.view.stickplot_checkbox.setText(
            "Left and right stick plots (SVG)" if three_view else "Side stick plot (SVG)"
        )
        if not three_view:
            self.view.rustlab_status_label.setText(
                "Single side view mode: RustLab1 multi side view output is disabled."
            )
        else:
            self.view.inputs._refresh_view_sets()
        self.view.controller._invalidate_stickplot_preview()
        self.view.controller._update_run_state()

    def _update_analysis_mode(self) -> None:
        if self._is_rustlab1_workflow():
            self.view.treadmill_speed_label.hide()
            self.view.treadmill_speed_spin.hide()
            self.view.spontaneous_box.hide()
            return
        treadmill = self.view.analysis_type_combo.currentText() == "Treadmill"
        self.view.treadmill_speed_label.setVisible(treadmill)
        self.view.treadmill_speed_spin.setVisible(treadmill)
        self.view.spontaneous_box.setVisible(not treadmill)
        self.view.stride_method_combo.setEnabled(not treadmill)
        self.view.compare_strides_button.setEnabled(not treadmill)
        if treadmill:
            self.view.stride_method_combo.setCurrentText("ALMA (legacy)")

    def _update_limb_scope(self) -> None:
        include_forelimb = self.view.limb_scope_combo.currentText() == "Hindlimb + Forelimb"
        self.view.parameter_selection.set_limb_scope(include_forelimb)
        if self.view.inputs._is_three_view_mode() and (not self._is_rustlab1_workflow()):
            detail = "64 RustLab1 parameters" if include_forelimb else "24 RustLab1 parameters"
            self.view.rustlab_status_label.setText(
                f"RustLab1 mode: {detail}; paired left, right, and bottom CSVs required."
            )

    def _collect_settings(self) -> AlmaSettings:
        if self.view.direction_combo.currentText() == "Auto-detect":
            right_to_left: bool | str = "auto"
        elif self.view.direction_combo.currentText() == "Right-to-Left":
            right_to_left = True
        else:
            right_to_left = False
        return AlmaSettings(
            **{
                name: int(spin.value()) if name.startswith("minimum_") else spin.value()
                for name, spin in self.view.comparison_rustlab_spins.items()
            },
            stride_detection_method=self.view.stride_method_combo.currentText(),
            mixture_context_ms=self.view.mixture_context_spin.value(),
            input_mode=MULTI_SIDE_VIEW_MODE_LABEL
            if self.view.inputs._is_three_view_mode()
            else SINGLE_SIDE_VIEW_MODE_LABEL,
            limb_scope=self.view.limb_scope_combo.currentText(),
            analysis_type=self.view.analysis_type_combo.currentText(),
            frame_rate=self.view.frame_rate_spin.value(),
            filter_cutoff=self.view.filter_cutoff_spin.value(),
            treadmill_speed_cm_s=self.view.treadmill_speed_spin.value(),
            calibration_method="reference"
            if self.view.calibration_method_combo.currentText() == "Reference body segment"
            else "manual",
            reference_segment=self.view.reference_segment_combo.currentText().split(" ", 1)[0],
            reference_length_cm=self.view.reference_length_spin.value(),
            calibration_map_path=self.view.state.calibration_map_path,
            right_to_left=right_to_left,
            pixels_per_cm=self.view.pixels_per_cm_spin.value()
            if self.view.calibration_method_combo.currentText() == "Manual pixel-to-cm ratio"
            else None,
            no_outlier_filter=self.view.no_outlier_checkbox.isChecked(),
            dragging_filter=self.view.dragging_filter_checkbox.isChecked(),
            likelihood_threshold=self.view.likelihood_threshold_spin.value(),
            drag_clearance_cm=self.view.drag_clearance_spin.value(),
            drag_min_consecutive_frames=self.view.drag_frames_spin.value(),
            step_height_min_cm=self.view.step_height_min_spin.value(),
            step_height_max_cm=self.view.step_height_max_spin.value(),
            stride_length_min_cm=self.view.stride_length_min_spin.value(),
            stride_length_max_cm=self.view.stride_length_max_spin.value(),
            generate_stickplot=self.view.stickplot_checkbox.isChecked(),
            generate_alma_representations=self.view.alma_representations_checkbox.isChecked(),
            generate_rustlab1_parameters=self.view.rustlab1_checkbox.isChecked()
            and self.view.inputs._is_three_view_mode(),
            custom_bodypart_mapping=self.view.mapping._collect_bodypart_mapping(),
            view_bodypart_mapping=self.view.mapping._collect_view_bodypart_mapping(),
            stroke_analysis_enabled=self.view.stroke_analysis_checkbox.isChecked()
            and self.view.inputs._is_three_view_mode(),
            stroke_likelihood_threshold=self.view.likelihood_threshold_spin.value(),
            max_interpolation_gap_frames=self.view.detection_gap_spin.value(),
            swing_speed_threshold_cm_s=self.view.stroke_swing_speed_spin.value(),
            minimum_synchronized_cycles=self.view.stroke_min_cycles_spin.value(),
            view_calibration=self.view.calibration._collect_view_calibration(),
            view_timing={
                side: {
                    "frame_rate": self.view.view_fps_spins[side].value(),
                    "offset_s": self.view.view_offset_spins[side].value(),
                }
                for side in ("left", "right", "bottom")
            },
            enabled_parameter_names=self.view.parameter_selection.enabled_parameter_names(),
        )

    def _collect_rustlab1_settings(self) -> RustLab1StandaloneSettings:
        return RustLab1StandaloneSettings(
            frame_rate=self.view.frame_rate_spin.value(),
            filter_cutoff=self.view.rustlab_filter_cutoff_spin.value(),
            likelihood_threshold=self.view.rustlab_likelihood_spin.value(),
            stance_speed_threshold_px_frame=self.view.rustlab_stance_speed_spin.value(),
            maximum_tracking_speed_px_frame=self.view.rustlab_max_tracking_speed_spin.value(),
            minimum_stance_frames=self.view.rustlab_min_stance_spin.value(),
            minimum_swing_frames=self.view.rustlab_min_swing_spin.value(),
            minimum_complete_strides=self.view.rustlab_min_strides_spin.value(),
            reference_paw=RUSTLAB1_PAW_LABELS[self.view.rustlab_reference_paw_combo.currentText()],
            limb_scope=self.view.limb_scope_combo.currentText(),
            calibration_method="reference"
            if self.view.calibration_method_combo.currentText() == "Reference body segment"
            else "manual",
            reference_segment=self.view.reference_segment_combo.currentText().split(" ", 1)[0],
            reference_length_cm=self.view.reference_length_spin.value(),
            pixels_per_cm=self.view.pixels_per_cm_spin.value()
            if self.view.calibration_method_combo.currentText() == "Manual pixel-to-cm ratio"
            else None,
            view_calibration=self.view.calibration._collect_view_calibration(),
            view_bodypart_mapping=self.view.mapping._collect_view_bodypart_mapping(),
            enabled_parameter_names=self.view.parameter_selection.enabled_parameter_names(),
            generate_figures=self.view.rustlab_standalone_figures_checkbox.isChecked(),
        )


ALMA_WORKFLOW_LABEL = "ALMA + post-ALMA features"
RUSTLAB1_WORKFLOW_LABEL = "RustLab1 standalone (three-view)"
RUSTLAB1_PAW_LABELS = {
    "Left hind paw": "d-back-left",
    "Right hind paw": "d-back-right",
    "Left front paw": "d-front-left",
    "Right front paw": "d-front-right",
}


def build_gait_setup(self, initial_multiside, setup_tab_layout):
    setup_box = QGroupBox("Experimental setup")
    self.setup_box = setup_box
    setup_layout = QGridLayout(setup_box)
    self.input_mode_combo = QComboBox()
    self.input_mode_combo.addItems([MULTI_SIDE_VIEW_MODE_LABEL, SINGLE_SIDE_VIEW_MODE_LABEL])
    self.input_mode_combo.setCurrentText(
        MULTI_SIDE_VIEW_MODE_LABEL if initial_multiside else SINGLE_SIDE_VIEW_MODE_LABEL
    )
    self.analysis_type_combo = QComboBox()
    self.analysis_type_combo.addItems(["Treadmill", "Spontaneous walking"])
    self.analysis_type_combo.setCurrentText(self._defaults.analysis_type)
    self.limb_scope_combo = QComboBox()
    self.limb_scope_combo.addItems(["Hindlimb", "Hindlimb + Forelimb"])
    self.limb_scope_combo.setCurrentText(self._defaults.limb_scope)
    set_tooltip(self.input_mode_combo, "Switch between one side-view CSV and paired left/right/bottom CSV analysis.")
    set_tooltip(self.analysis_type_combo, "Choose treadmill or spontaneous-walking analysis.")
    set_tooltip(
        self.limb_scope_combo,
        "Choose the established hindlimb output or add RustLab1 forelimb and interlimb parameters and plots.",
    )
    self.input_mode_label = QLabel("Input mode")
    self.analysis_type_label = QLabel("Analysis type")
    self.limb_scope_label = QLabel("Limb analysis")
    setup_layout.addWidget(self.input_mode_label, 0, 0)
    setup_layout.addWidget(self.input_mode_combo, 0, 1)
    setup_layout.addWidget(self.analysis_type_label, 1, 0)
    setup_layout.addWidget(self.analysis_type_combo, 1, 1)
    setup_layout.addWidget(self.limb_scope_label, 2, 0)
    setup_layout.addWidget(self.limb_scope_combo, 2, 1)
    setup_tab_layout.addWidget(setup_box)
