"""Connect input changes, preview validity, selected detectors, analysis requests, and returned outputs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_worker import (
    AlmaAnalysisThread,
    RustLab1AnalysisThread,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_preview_worker import (
    RustLab1PreviewThread,
    StickPlotPreviewThread,
)
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS
from dlc_gait_assembly.shared.client.qt_input_behaviors import (
    add_shortcut,
    animate_button_emphasis,
    install_wheel_value_guard,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class GaitAnalysisController:
    """GaitAnalysisController operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _install_interactions(self) -> None:
        self.view._shortcuts = [
            add_shortcut(self.view, "Ctrl+O", self.view.inputs._add_file),
            add_shortcut(self.view, "Ctrl+Shift+O", self.view.inputs._add_folder),
            add_shortcut(self.view, "Ctrl+L", self.view.inputs._clear_files),
            add_shortcut(self.view, "Ctrl+Shift+S", self.view.outputs._select_output_folder),
            add_shortcut(self.view, "Ctrl+F", self._load_frame_rate_from_video),
            add_shortcut(self.view, "Ctrl+M", self.view.calibration._import_calibration_map),
            add_shortcut(self.view, "Ctrl+Shift+E", self.view.outputs._export_analysis_manifest),
            add_shortcut(self.view, "Ctrl+P", self._generate_stickplot_preview),
            add_shortcut(self.view, "Ctrl+R", self._run_analysis),
        ]
        self.view._wheel_value_guard = install_wheel_value_guard(self.view)

    def _connect_signals(self) -> None:
        self.view.parameter_figures_button.clicked.connect(self._show_parameter_figures)
        self.view.figure_reference_button.clicked.connect(self._show_figure_documentation)
        self.view.parameter_reference_button.clicked.connect(self._show_parameter_documentation)
        self.view.documentation_back_button.clicked.connect(self._close_documentation)
        self.view.add_file_button.clicked.connect(self.view.inputs._add_file)
        self.view.add_folder_button.clicked.connect(self.view.inputs._add_folder)
        self.view.clear_files_button.clicked.connect(self.view.inputs._clear_files)
        self.view.edit_pairing_button.clicked.connect(self.view.inputs._open_csv_pairing_dialog)
        self.view.label_matching_button.clicked.connect(self.view.mapping._open_label_matching_dialog)
        self.view.output_folder_button.clicked.connect(self.view.outputs._select_output_folder)
        self.view.output_folder_edit.textChanged.connect(self._update_run_state)
        self.view.compare_strides_button.clicked.connect(self._compare_stride_methods)
        self.view.preview_button.clicked.connect(self._generate_stickplot_preview)
        self.view.run_button.clicked.connect(self._run_analysis)
        self.view.workflow_combo.currentTextChanged.connect(self.view.setup._update_workflow)
        self.view.analysis_type_combo.currentTextChanged.connect(self.view.setup._update_analysis_mode)
        self.view.limb_scope_combo.currentTextChanged.connect(self.view.setup._update_limb_scope)
        self.view.likelihood_threshold_spin.valueChanged.connect(self.view.stroke_likelihood_spin.setValue)
        self.view.calibration_method_combo.currentTextChanged.connect(self.view.calibration._update_calibration_method)
        self.view.load_fps_button.clicked.connect(self._load_frame_rate_from_video)
        self.view.import_calibration_map_button.clicked.connect(self.view.calibration._import_calibration_map)
        self.view.export_manifest_button.clicked.connect(self.view.outputs._export_analysis_manifest)
        self.view.import_manifest_button.clicked.connect(self.view.outputs._import_analysis_manifest)
        self.view.use_custom_mapping_checkbox.toggled.connect(self.view.mapping._update_mapping_enabled)
        self.view.reload_mapping_button.clicked.connect(self.view.mapping._load_bodypart_mapping_from_first_file)
        self.view.auto_mapping_button.clicked.connect(self.view.mapping._apply_auto_bodypart_mapping)
        self.view.file_list.model().rowsInserted.connect(self._update_run_state)
        self.view.file_list.model().rowsRemoved.connect(self._update_run_state)
        self.view.file_list.currentRowChanged.connect(self._preview_file_changed)
        self.view.view_set_table.currentItemChanged.connect(self._preview_view_set_changed)
        self.view.input_mode_combo.currentTextChanged.connect(self.view.setup._update_input_mode)
        preview_controls = (
            self.view.workflow_combo,
            self.view.input_mode_combo,
            self.view.analysis_type_combo,
            self.view.limb_scope_combo,
            self.view.calibration_method_combo,
            self.view.reference_segment_combo,
            self.view.direction_combo,
            self.view.stride_method_combo,
        )
        for combo in preview_controls:
            combo.currentTextChanged.connect(self._invalidate_stickplot_preview)
        preview_spins = (
            self.view.treadmill_speed_spin,
            self.view.frame_rate_spin,
            self.view.reference_length_spin,
            self.view.pixels_per_cm_spin,
            self.view.filter_cutoff_spin,
            self.view.drag_clearance_spin,
            self.view.drag_frames_spin,
            self.view.step_height_min_spin,
            self.view.step_height_max_spin,
            self.view.stride_length_min_spin,
            self.view.stride_length_max_spin,
            self.view.likelihood_threshold_spin,
            self.view.rustlab_likelihood_spin,
            self.view.rustlab_filter_cutoff_spin,
            self.view.rustlab_stance_speed_spin,
            self.view.rustlab_max_tracking_speed_spin,
            self.view.rustlab_min_stance_spin,
            self.view.rustlab_min_swing_spin,
            self.view.rustlab_min_strides_spin,
        )
        for spin in (
            self.view.mixture_context_spin,
            *preview_spins,
            *self.view.view_scale_spins.values(),
            *self.view.view_fps_spins.values(),
            *self.view.view_offset_spins.values(),
            *self.view.comparison_rustlab_spins.values(),
            self.view.bottom_x_pixels_per_cm_spin,
            self.view.bottom_y_pixels_per_cm_spin,
            self.view.detection_gap_spin,
        ):
            spin.valueChanged.connect(self._invalidate_stickplot_preview)
        self.view.rustlab_reference_paw_combo.currentTextChanged.connect(self._invalidate_stickplot_preview)
        self.view.frame_rate_spin.valueChanged.connect(self.view.filters._update_rustlab_filter_range)
        self.view.rustlab_stance_speed_spin.valueChanged.connect(self.view.filters._update_rustlab_speed_range)
        for checkbox in (
            self.view.no_outlier_checkbox,
            self.view.dragging_filter_checkbox,
            self.view.use_custom_mapping_checkbox,
        ):
            checkbox.toggled.connect(self._invalidate_stickplot_preview)
        for combo in self.view._bodypart_combos.values():
            combo.currentTextChanged.connect(self._invalidate_stickplot_preview)

    def _show_figure_documentation(self) -> None:
        self.view.parameter_reference.figure_source_filter.setCurrentText(
            "RustLab1" if self.view.setup._is_rustlab1_workflow() else "All figures"
        )
        self.view.parameter_reference.show_figure_documentation()
        self._show_documentation("Figure creator documentation")

    def _show_parameter_documentation(self) -> None:
        self.view.parameter_reference.set_multiside(self.view.inputs._is_three_view_mode())
        self.view.parameter_reference.source_filter.setCurrentText(
            "RustLab1" if self.view.setup._is_rustlab1_workflow() else "All sources"
        )
        self.view.parameter_reference.show_parameter_documentation()
        self._show_documentation("Gait parameter documentation")

    def _show_documentation(self, title: str) -> None:
        self.view.workspace_stack.setCurrentWidget(self.view.parameter_reference)
        self.view.workspace_title.setText(title)
        self.view.documentation_back_button.show()

    def _close_documentation(self) -> None:
        self.view.workspace_stack.setCurrentIndex(0)
        self.view.workspace_title.setText(
            "RustLab1 standalone analysis" if self.view.setup._is_rustlab1_workflow() else "Runway analysis"
        )
        self.view.documentation_back_button.hide()

    def _run_analysis(self) -> None:
        if self._processing_running():
            return
        if not self.view.output_folder_edit.text().strip():
            self.view.outputs._select_output_folder()
            if not self.view.output_folder_edit.text().strip():
                return
        output_folder = Path(self.view.output_folder_edit.text()).expanduser().resolve()
        if not self.view.inputs._has_valid_inputs():
            QMessageBox.information(self.view, "Input CSVs required", self.view.inputs._input_requirement_message())
            return
        if not self.view.state.preview_validity.ready:
            preview_name = (
                "RustLab1 stride preview" if self.view.setup._is_rustlab1_workflow() else "stick-plot preview"
            )
            QMessageBox.information(
                self.view,
                f"{preview_name.capitalize()} required",
                f"Generate and review the {preview_name} before running the analysis.",
            )
            return
        if self.view.setup._is_rustlab1_workflow():
            self._run_rustlab1_analysis(output_folder)
            return
        settings = self.view.setup._collect_settings()
        if self.view.use_custom_mapping_checkbox.isChecked() and (not settings.custom_bodypart_mapping):
            QMessageBox.warning(
                self.view, "No body part mapping", "Select at least one body part mapping or turn off custom mapping."
            )
            return
        self.view.progress.setValue(0)
        self.view.progress.set_active(True)
        self.view.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        animate_button_emphasis(self.view.preview_button, False)
        animate_button_emphasis(self.view.run_button, True)
        self.view.log.clear()
        self.view.status_label.setText("Running ALMA gait analysis...")
        self.view.workspace_tabs.setCurrentWidget(self.view.log_page)
        self.view.run_button.setEnabled(False)
        analysis_inputs = (
            self.view.state.view_sets if self.view.inputs._is_three_view_mode() else self.view.state.selected_files
        )
        self.view._worker = AlmaAnalysisThread(
            analysis_inputs, output_folder, settings, analyze=self.view.analysis.analyze_alma
        )
        self.view._worker.progress_updated.connect(self._update_progress)
        self.view._worker.log_message.connect(self._append_log)
        self.view._worker.results_ready.connect(self._output_results_ready)
        self.view._worker.analysis_completed.connect(self._analysis_completed)
        self.view._worker.finished.connect(self._worker_finished)
        self.view._worker.start()
        self._update_run_state()

    def _run_rustlab1_analysis(self, output_folder: Path) -> None:
        settings = self.view.setup._collect_rustlab1_settings()
        self.view.progress.setValue(0)
        self.view.progress.set_active(True)
        self.view.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        animate_button_emphasis(self.view.preview_button, False)
        animate_button_emphasis(self.view.run_button, True)
        self.view.log.clear()
        self.view.status_label.setText("Running standalone RustLab1 analysis...")
        self.view.workspace_tabs.setCurrentWidget(self.view.log_page)
        self.view.run_button.setEnabled(False)
        self.view._worker = RustLab1AnalysisThread(
            self.view.state.view_sets, output_folder, settings, analyze=self.view.analysis.analyze_rustlab1
        )
        self.view._worker.progress_updated.connect(self._update_progress)
        self.view._worker.log_message.connect(self._append_log)
        self.view._worker.results_ready.connect(self._output_results_ready)
        self.view._worker.analysis_completed.connect(self._analysis_completed)
        self.view._worker.finished.connect(self._worker_finished)
        self.view._worker.start()
        self._update_run_state()

    def _update_progress(self, value: int, text: str) -> None:
        self.view.progress.setValue(value)
        self.view.status_label.setText(text)

    def _append_log(self, text: str) -> None:
        self.view.log.append(text)

    def _analysis_completed(self, success: bool, message: str) -> None:
        workflow_name = "RustLab1 analysis" if self.view.setup._is_rustlab1_workflow() else "ALMA gait analysis"
        status_message = message
        if success and self.view.state.output_preview_paths:
            status_message += "\nPreview the generated figures and tables below."
        self.view.status_label.setText(status_message)
        self.view.progress.set_active(False)
        self.view.progress.setValue(100 if success else self.view.progress.value())
        animate_button_emphasis(self.view.run_button, False)
        if success:
            self.view.run_button.setIcon(interface_icon("check", theme.PRIMARY_TEXT))
            QMessageBox.information(self.view, f"{workflow_name} complete", message)
        else:
            self.view.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
            self.view.workspace_tabs.setCurrentWidget(self.view.log_page)
            QMessageBox.critical(self.view, f"{workflow_name} failed", message)

    def _show_parameter_figures(self):
        from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_preview_worker import ParameterFiguresThread

        paths = getattr(self.view, "_parameter_csv_paths", ())
        if not paths or self._processing_running():
            return
        self.view.progress.setValue(0)
        self.view.progress.set_active(True)
        self.view.status_label.setText("Preparing all parameter figures…")
        self.view._preview_worker = ParameterFiguresThread(paths, reader=self.view.analysis.results)
        self.view._preview_worker.progress_updated.connect(self._update_progress)
        self.view._preview_worker.figures_ready.connect(self._parameter_figures_ready)
        self.view._preview_worker.figures_failed.connect(self._parameter_figures_failed)
        self.view._preview_worker.finished.connect(self._preview_worker_finished)
        self.view._preview_worker.start()
        self._update_run_state()

    def _parameter_figures_ready(self, plots):
        from dlc_gait_assembly.shared.client.qt_svg_preview import SvgPreviewDialog

        dialog = SvgPreviewDialog("All gait parameter figures", plots, self.view)
        self.view._parameter_figures_dialog = dialog
        self.view.status_label.setText(f"All parameter figures ready: {len(plots)} pages.")
        self.view.progress.setValue(100)
        dialog.show()

    def _parameter_figures_failed(self, message):
        self.view.status_label.setText("Parameter figures could not be generated.")
        QMessageBox.warning(self.view, "Parameter figures", message)

    def _output_results_ready(self, results) -> None:
        files = tuple(dict.fromkeys(path for result in results for path in result.output_files))
        if files:
            report = next((path for path in files if path.name == "export_report.txt"), files[0])
            self.view._saved_results_folder = report.parent
            self.view.open_results_button.setEnabled(True)
            self.view.export_summary_label.setText(f"Saved {len(files)} files to:\n{self.view._saved_results_folder}")
        self.view._parameter_csv_paths = tuple(
            path
            for path in files
            if path.name
            in {
                "left_stride_parameters.csv",
                "right_stride_parameters.csv",
                "side_stride_parameters.csv",
                "general_parameters.csv",
                "gait_parameters.csv",
            }
        )
        self.view._parameter_csv_path = next(iter(self.view._parameter_csv_paths), None)
        self.view.parameter_figures_button.setEnabled(self.view._parameter_csv_path is not None)
        output_files = (output_file for result in results for output_file in getattr(result, "output_files", ()))
        self.view.state.output_preview_paths = self.view.analysis.results.previewable_paths(output_files)
        if not self.view.state.output_preview_paths:
            self._append_log("No SVG or CSV output previews were available.")
            return
        self.view.output_preview_view.load_paths(self.view.state.output_preview_paths)
        self.view.preview_stack.setCurrentWidget(self.view.output_preview_view)
        self.view.workspace_tabs.setCurrentWidget(self.view.preview_page)
        self._append_log(f"Loaded {len(self.view.state.output_preview_paths)} generated output previews.")

    def _worker_finished(self) -> None:
        self.view._worker = None
        self.view.progress.set_active(False)
        self._update_run_state()

    def _processing_running(self):
        analysis_running = self.view._worker is not None and self.view._worker.isRunning()
        preview_running = self.view._preview_worker is not None and self.view._preview_worker.isRunning()
        return analysis_running or preview_running

    def _update_run_state(self) -> None:
        has_files = self.view.inputs._has_valid_inputs()
        has_output = bool(self.view.output_folder_edit.text().strip())
        running = self._processing_running()
        self.view.import_manifest_button.setEnabled(not running)
        for control in (
            self.view.output_folder_edit,
            self.view.output_folder_button,
            self.view.export_folder_edit,
            self.view.export_folder_button,
        ):
            control.setEnabled(not running)
        self.view.parameter_figures_button.setEnabled(
            getattr(self.view, "_parameter_csv_path", None) is not None and not running
        )
        self.view.preview_button.setEnabled(has_files and (not running))
        self.view.compare_strides_button.setEnabled(
            has_files and not running and self.view.analysis_type_combo.currentText() != "Treadmill"
        )
        self.view.run_button.setEnabled(
            has_files and has_output and self.view.state.preview_validity.ready and (not running)
        )

    def _preview_file_changed(self, row: int) -> None:
        if row < 0 or not self.view.state.selected_files:
            return
        selected = self.view.state.selected_files[row]
        if not self.view.inputs._is_three_view_mode():
            self._invalidate_stickplot_preview(f"Generate a stick-plot preview for {selected.name}.")
            return
        for index, view_set in enumerate(self.view.state.view_sets):
            if selected in (view_set.left_csv, view_set.right_csv, view_set.bottom_csv):
                self._select_view_set_row(index)
                break
        if self.view.inputs._has_valid_view_sets():
            self._invalidate_stickplot_preview(
                f"Generate a stick-plot preview for {self.view.inputs._selected_preview_file().name}."
            )
        else:
            self._invalidate_stickplot_preview(self.view.inputs._multiview_requirement_message())

    def _preview_view_set_changed(self, current, _previous) -> None:
        if current is None:
            return
        if self.view.inputs._selected_view_set() is not None:
            self._invalidate_stickplot_preview(
                f"Generate a stick-plot preview for {self.view.inputs._selected_preview_file().name}."
            )
        else:
            self._invalidate_stickplot_preview(self.view.inputs._multiview_requirement_message())

    def _select_view_set_row(self, view_set_index: int) -> None:
        for row in range(self.view.view_set_table.topLevelItemCount()):
            item = self.view.view_set_table.topLevelItem(row)
            if item.data(0, Qt.UserRole) == view_set_index:
                self.view.view_set_table.setCurrentItem(item)
                return

    def _load_frame_rate_from_video(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        (filename, _) = QFileDialog.getOpenFileName(
            self.view,
            "Select video to read frame rate",
            str(self.view._project_root),
            f"Video files ({extensions});;All files (*)",
        )
        if not filename:
            return
        try:
            info = self.view.analysis.inputs.probe_video(filename)
        except Exception as exc:
            QMessageBox.critical(self.view, "Could not read frame rate", str(exc))
            return
        if info.fps <= 0:
            QMessageBox.warning(
                self.view, "No frame rate detected", "The selected video did not report a usable frame rate."
            )
            return
        fps = round(info.fps, 2)
        self.view.frame_rate_spin.setValue(fps)
        self.view.status_label.setText(f"Frame rate detected: {fps:g} fps")
        self._append_log(f"Frame rate loaded from {Path(filename).name}: {fps:g} fps")

    def _invalidate_stickplot_preview(self, message=None, *_args) -> None:
        rustlab1_only = self.view.setup._is_rustlab1_workflow()
        preview_name = "RustLab1 stride preview" if rustlab1_only else "stick-plot preview"
        if isinstance(message, str) and message:
            placeholder_text = message
        elif (
            self.view.inputs._is_three_view_mode()
            and self.view.state.selected_files
            and (not self.view.inputs._has_valid_view_sets())
        ):
            placeholder_text = self.view.inputs._multiview_requirement_message()
        elif self.view.state.selected_files:
            source_name = (
                self.view.inputs._selected_view_set().name
                if rustlab1_only and self.view.inputs._selected_view_set() is not None
                else self.view.inputs._selected_preview_file().name
            )
            placeholder_text = f"Settings changed. Regenerate the {preview_name} for {source_name}."
        elif rustlab1_only:
            placeholder_text = "Select matched left/right/bottom CSVs, then generate a RustLab1 stride preview."
        else:
            placeholder_text = (
                "Select left/right/bottom CSVs, then generate a stick-plot preview."
                if self.view.inputs._is_three_view_mode()
                else "Select one side-view CSV, then generate a stick-plot preview."
            )
        self.view.state.preview_validity.invalidate()
        self.view.state.preview_svg_data = None
        self.view.state.preview_source_name = ""
        if self.view._preview_worker is not None and self.view._preview_worker.isRunning():
            pass
        elif self.view.inputs._has_valid_inputs():
            self.view.status_label.setText(f"Generate a {preview_name} before running the analysis.")
        else:
            self.view.status_label.setText(
                "Select matched left/right/bottom CSV files to begin."
                if self.view.inputs._is_three_view_mode()
                else "Select a side-view CSV file to begin."
            )
        self.view.preview_placeholder.setText(placeholder_text)
        self.view.preview_stack.setCurrentWidget(self.view.preview_placeholder)
        self.view.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        self._update_run_state()

    def _compare_stride_methods(self):
        if self._processing_running():
            return
        if not self.view.inputs._has_valid_inputs():
            QMessageBox.information(
                self.view, "Select a recording", "Select paired CSVs before comparing detection methods."
            )
            return
        from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_preview_worker import StrideComparisonThread

        settings = self.view.setup._collect_settings()
        view_set = self.view.inputs._selected_view_set() if self.view.inputs._is_three_view_mode() else None
        if view_set:
            settings = replace(settings, view_bodypart_mapping=view_mappings_for_set(settings, view_set.name))
        self.view.state.preview_validity.begin()
        self.view._preview_worker = StrideComparisonThread(
            self.view.inputs._preview_inputs(), settings, preview=self.view.preview
        )
        self.view._preview_worker.progress_updated.connect(self._update_progress)
        self.view._preview_worker.comparison_ready.connect(self._show_stride_comparison)
        self.view._preview_worker.preview_failed.connect(self._stickplot_preview_failed)
        self.view._preview_worker.finished.connect(self._preview_worker_finished)
        self.view._preview_worker.start()
        self._update_run_state()

    def _show_stride_comparison(self, results):
        from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_stride_comparison_dialog import (
            StrideComparisonDialog,
        )

        if self.view.state.preview_validity.stale:
            self.view.status_label.setText(
                "Settings changed during comparison. Compare again before choosing a method."
            )
            return
        dialog = StrideComparisonDialog(results, self.view.stride_method_combo.currentText(), self.view)
        if dialog.exec():
            self.view.stride_method_combo.setCurrentText(dialog.selected_method())
            self._invalidate_stickplot_preview(
                "Method selected. Generate a preview to review its detected strides before analysis."
            )

    def _generate_stickplot_preview(self) -> None:
        if self._processing_running():
            return
        if not self.view.inputs._has_valid_inputs():
            QMessageBox.information(self.view, "Input CSVs required", self.view.inputs._input_requirement_message())
            return
        if self.view.setup._is_rustlab1_workflow():
            self._generate_rustlab1_preview()
            return
        settings = self.view.setup._collect_settings()
        if self.view.inputs._is_three_view_mode():
            view_set = self.view.inputs._selected_view_set()
            settings = replace(
                settings,
                view_bodypart_mapping=view_mappings_for_set(settings, view_set.name) if view_set is not None else None,
            )
        if self.view.use_custom_mapping_checkbox.isChecked() and (not settings.custom_bodypart_mapping):
            QMessageBox.warning(
                self.view, "No body part mapping", "Select at least one body part mapping or turn off custom mapping."
            )
            return
        missing_bodyparts = self.view.inputs._missing_required_bodyparts(settings)
        if missing_bodyparts:
            if self.view.inputs._is_three_view_mode():
                self.view.mapping._open_label_matching_dialog()
            else:
                self.view.settings_tabs.setCurrentWidget(self.view.mapping_tab)
            self.view.mapping_status_label.setText("Missing required ALMA body parts: " + ", ".join(missing_bodyparts))
            QMessageBox.warning(
                self.view,
                "Body part mapping incomplete",
                "ALMA needs toe, mtp, ankle, knee, hip, and iliac crest coordinates for each side view. Open Label matching and assign the left, right, and bottom labels for the selected CSV set.",
            )
            return
        self.view.state.preview_validity.fail()
        self.view.state.preview_validity.begin()
        self.view.progress.setValue(0)
        self.view.progress.set_active(True)
        self.view.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        animate_button_emphasis(self.view.preview_button, True)
        animate_button_emphasis(self.view.run_button, False)
        self.view.log.clear()
        preview_inputs = self.view.inputs._preview_inputs()
        preview_names = ", ".join(path.name for (_label, path) in preview_inputs)
        self.view.status_label.setText(f"Generating stick-plot preview for {preview_names}...")
        self.view.preview_placeholder.setText(f"Generating ALMA stick plot for {preview_names}...")
        self.view.preview_stack.setCurrentWidget(self.view.preview_placeholder)
        self.view.workspace_tabs.setCurrentWidget(self.view.preview_page)
        preview_settings = replace(
            settings,
            generate_stickplot=True,
            generate_alma_representations=False,
            generate_rustlab1_parameters=False,
            stroke_analysis_enabled=False,
        )
        self.view._preview_worker = StickPlotPreviewThread(preview_inputs, preview_settings, preview=self.view.preview)
        self.view._preview_worker.progress_updated.connect(self._update_progress)
        self.view._preview_worker.log_message.connect(self._append_log)
        self.view._preview_worker.preview_ready.connect(self._stickplot_preview_completed)
        self.view._preview_worker.preview_failed.connect(self._stickplot_preview_failed)
        self.view._preview_worker.finished.connect(self._preview_worker_finished)
        self.view._preview_worker.start()
        self._update_run_state()

    def _generate_rustlab1_preview(self) -> None:
        view_set = self.view.inputs._selected_view_set()
        if view_set is None:
            QMessageBox.information(
                self.view, "Three-view CSV set required", self.view.inputs._multiview_requirement_message()
            )
            return
        settings = replace(
            self.view.setup._collect_rustlab1_settings(),
            view_bodypart_mapping=self.view.state.view_label_mappings.get(view_set.name),
        )
        missing_bodyparts = self.view.inputs._missing_rustlab1_bodyparts(view_set, settings)
        if missing_bodyparts:
            self.view.mapping._open_label_matching_dialog()
            self.view.mapping_status_label.setText(
                "Missing required RustLab1 body parts: " + ", ".join(missing_bodyparts)
            )
            QMessageBox.warning(
                self.view,
                "RustLab1 label mapping incomplete",
                "RustLab1 needs the side-view joints and bottom-view paw labels for the selected limb scope and reference paw. Open Label matching and assign the missing labels for this CSV set.",
            )
            return
        self.view.state.preview_validity.fail()
        self.view.state.preview_validity.begin()
        self.view.progress.setValue(0)
        self.view.progress.set_active(True)
        self.view.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        animate_button_emphasis(self.view.preview_button, True)
        animate_button_emphasis(self.view.run_button, False)
        self.view.log.clear()
        self.view.status_label.setText(f"Detecting RustLab1 strides for {view_set.name}...")
        self.view.preview_placeholder.setText(f"Generating bottom-paw speed and stride preview for {view_set.name}...")
        self.view.preview_stack.setCurrentWidget(self.view.preview_placeholder)
        self.view.workspace_tabs.setCurrentWidget(self.view.preview_page)
        self.view._preview_worker = RustLab1PreviewThread(view_set, settings, preview=self.view.preview)
        self.view._preview_worker.progress_updated.connect(self._update_progress)
        self.view._preview_worker.log_message.connect(self._append_log)
        self.view._preview_worker.preview_ready.connect(self._stickplot_preview_completed)
        self.view._preview_worker.preview_failed.connect(self._stickplot_preview_failed)
        self.view._preview_worker.finished.connect(self._preview_worker_finished)
        self.view._preview_worker.start()
        self._update_run_state()

    def _stickplot_preview_completed(self, plots, source_name: str) -> None:
        rustlab1_only = self.view.setup._is_rustlab1_workflow()
        preview_name = "RustLab1 stride preview" if rustlab1_only else "Stick-plot preview"
        if self.view.state.preview_validity.stale:
            self.view.state.preview_validity.fail()
            self.view.preview_placeholder.setText("Settings changed while the preview was running. Generate it again.")
            self.view.preview_stack.setCurrentWidget(self.view.preview_placeholder)
            self.view.status_label.setText(f"{preview_name} is out of date.")
            self._append_log("Preview discarded because its settings changed during generation.")
            return
        plot_tuple = tuple(plots)
        if not plot_tuple:
            self._stickplot_preview_failed(f"{preview_name} did not return any SVG plots.")
            return
        self.view.stickplot_view.load_plots(plot_tuple)
        self.view.preview_stack.setCurrentWidget(self.view.stickplot_view)
        self.view.workspace_tabs.setCurrentWidget(self.view.preview_page)
        self.view.state.preview_validity.complete()
        self.view.state.preview_svg_data = plot_tuple
        self.view.state.preview_source_name = source_name
        self.view.progress.setValue(100)
        self.view.preview_button.setIcon(interface_icon("check", theme.STATUS_READY))
        animate_button_emphasis(self.view.preview_button, False)
        next_action = "run RustLab1 analysis" if rustlab1_only else "run gait analysis"
        self.view.status_label.setText(f"{preview_name} ready. Review it, then {next_action}.")
        self._append_log(f"{preview_name} generated from {source_name}.")

    def _stickplot_preview_failed(self, message: str) -> None:
        preview_name = "RustLab1 stride preview" if self.view.setup._is_rustlab1_workflow() else "Stick-plot preview"
        self.view.state.preview_validity.fail()
        self.view.state.preview_svg_data = None
        self.view.state.preview_source_name = ""
        self.view.preview_placeholder.setText(f"{preview_name} could not be generated.")
        self.view.preview_stack.setCurrentWidget(self.view.preview_placeholder)
        self.view.status_label.setText(f"{preview_name} failed.")
        self.view.progress.set_active(False)
        self.view.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        animate_button_emphasis(self.view.preview_button, False)
        self._append_log(message)
        QMessageBox.critical(self.view, f"{preview_name} failed", message)

    def _preview_worker_finished(self) -> None:
        self.view._preview_worker = None
        self.view.progress.set_active(False)
        self._update_run_state()
