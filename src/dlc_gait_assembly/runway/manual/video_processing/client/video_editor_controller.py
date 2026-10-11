"""Connect editor actions, settings manifests, and video-export requests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QToolButton

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions
from dlc_gait_assembly.runway.manual.video_processing.client.video_export_dialog import ExportSettingsDialog
from dlc_gait_assembly.runway.manual.video_processing.client.video_export_worker import VideoProcessingThread
from dlc_gait_assembly.shared.client.qt_input_behaviors import add_shortcut, animate_button_emphasis
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class VideoEditorController:
    """VideoEditorController operates on its explicitly supplied VideoEditorWidget view."""

    def __init__(self, view):
        self.view = view

    def _connect_signals(self) -> None:
        self.view.add_videos_button.clicked.connect(self.view.sources._add_videos)
        self.view.add_folder_button.clicked.connect(self.view.sources._add_video_folder)
        self.view.remove_videos_button.clicked.connect(self.view.sources._remove_selected_videos)
        self.view.clear_videos_button.clicked.connect(self.view.sources._clear_videos)
        self.view.video_list.currentItemChanged.connect(self.view.playback._load_selected_video)
        self.view.import_video_manifest_button.clicked.connect(self._import_video_manifest)
        self.view.export_video_manifest_button.clicked.connect(self._export_video_manifest)
        self.view.crop_tool_button.clicked.connect(lambda: self._set_active_tool("crop"))
        self.view.enhancements_tool_button.clicked.connect(lambda: self._set_active_tool("enhancements"))
        self.view.trim_tool_button.clicked.connect(lambda: self._set_active_tool("trim"))
        self.view.process_button.clicked.connect(self._process_all_videos)
        self.view.timeline.valueChanged.connect(self.view.playback._timeline_changed)
        self.view.timeline.sliderReleased.connect(self.view.playback._flush_pending_frame)
        self.view.timeline.trim_active_changed.connect(self.view.trims._on_trim_active_changed)
        self.view.timeline.trim_range_changed.connect(self.view.trims._on_trim_range_changed)
        self.view.preview.operation_enabled_requested.connect(self._enable_operation_from_preview)
        self.view.settings_panel.trim_active_range_changed.connect(self.view.trims._on_trim_active_changed)
        self.view.settings_panel.trim_range_changed.connect(self.view.trims._on_trim_range_changed)
        self.view.settings_panel.trim_range_added.connect(self.view.trims._add_trim_range)
        self.view.settings_panel.trim_range_deleted.connect(self.view.trims._delete_trim_range)
        self.view.settings_panel.trim_ranges_reset.connect(self.view.trims._reset_current_video_trim)
        self.view.settings_panel.video_preview_requested.connect(self.view.sources._select_video_by_path)

    def _install_shortcuts(self) -> None:
        self.view._shortcuts = [
            add_shortcut(self.view, "Ctrl+O", self.view.sources._add_videos),
            add_shortcut(self.view, "Ctrl+Shift+O", self.view.sources._add_video_folder),
            add_shortcut(self.view, "Ctrl+Backspace", self.view.sources._remove_selected_videos),
            add_shortcut(self.view, "Ctrl+L", self.view.sources._clear_videos),
            add_shortcut(self.view, "Ctrl+1", lambda: self._activate_tool_button(self.view.crop_tool_button, "crop")),
            add_shortcut(
                self.view,
                "Ctrl+2",
                lambda: self._activate_tool_button(self.view.enhancements_tool_button, "enhancements"),
            ),
            add_shortcut(self.view, "Ctrl+3", lambda: self._activate_tool_button(self.view.trim_tool_button, "trim")),
            add_shortcut(self.view, "Ctrl+R", self._process_all_videos),
        ]

    def _enable_operation_from_preview(self, name: str, enabled: bool) -> None:
        if not enabled:
            return
        if name == "crop":
            self.view.crop_tool_button.setChecked(True)
            self._set_active_tool("crop")

    def _set_active_tool(self, name: str) -> None:
        self.view.preview.set_mode(name)
        self.view.settings_panel.set_active_tool(name)
        self.view.timeline.set_trim_editing_enabled(name == "trim")
        self._emphasize_operation_tool(name)
        self.view.trims._refresh_trim_context()

    def _emphasize_operation_tool(self, active_name: str) -> None:
        for name, button in (
            ("crop", self.view.crop_tool_button),
            ("enhancements", self.view.enhancements_tool_button),
            ("trim", self.view.trim_tool_button),
        ):
            animate_button_emphasis(button, name == active_name, resting_height=30, emphasized_height=40)

    def _activate_tool_button(self, button: QToolButton, name: str) -> None:
        button.setChecked(True)
        self._set_active_tool(name)

    def _process_all_videos(self) -> None:
        videos = self.view.sources._video_paths()
        if not videos:
            QMessageBox.information(self.view, "No videos", "Add one or more videos before processing.")
            return
        options = self._current_processing_options()
        trim_ranges_by_path = self.view.trims._trim_ranges_for_processing(videos)
        if not self.view.use_cases.available():
            QMessageBox.critical(
                self.view,
                "ffmpeg is missing",
                "Install the conda environment first, or run: conda install -c conda-forge ffmpeg",
            )
            return
        export_dialog = ExportSettingsDialog(len(videos), self.view._default_output_root(), self.view)
        if export_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_root = export_dialog.output_root()
        options = replace(options, crf=export_dialog.crf(), preset=export_dialog.preset())
        try:
            session_dir = self.view.use_cases.prepare_session(output_root)
        except Exception as exc:
            QMessageBox.critical(self.view, "Output error", str(exc))
            return
        self.view.progress.setRange(0, len(videos))
        self.view.progress.setValue(0)
        self.view.progress.setFormat("%v / %m")
        self.view.progress.set_active(True)
        self.view.process_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        animate_button_emphasis(self.view.process_button, True)
        self.view.state.processing_errors = []
        self.view.state.processing_failures = []
        self.view.state.processing_outputs = []
        self.view.state.processing_options = options
        self.view.state.processing_video_paths = videos
        self.view.state.processing_trim_ranges_by_path = trim_ranges_by_path
        self._set_processing_enabled(False)
        self.view._processing_thread = VideoProcessingThread(
            videos, session_dir, options, trim_ranges_by_path, self.view, use_cases=self.view.use_cases
        )
        self.view._processing_thread.file_started.connect(self._on_file_started)
        self.view._processing_thread.file_finished.connect(self._on_file_finished)
        self.view._processing_thread.file_failed.connect(self._on_file_failed)
        self.view._processing_thread.completed.connect(self._on_processing_completed)
        self.view._processing_thread.start()

    def _on_file_started(self, index: int, total: int, name: str) -> None:
        self.view.progress.setFormat(f"{index} / {total}")

    def _on_file_finished(self, input_path: str, output_paths) -> None:
        self.view.progress.setValue(self.view.progress.value() + 1)
        for output_path in output_paths:
            self.view.state.processing_outputs.append((input_path, str(output_path)))

    def _on_file_failed(self, input_path: str, message: str) -> None:
        self.view.progress.setValue(self.view.progress.value() + 1)
        self.view.state.processing_failures.append((input_path, message))
        self.view.state.processing_errors.append(f"{Path(input_path).name}: {message}")

    def _on_processing_completed(self, session_dir: str) -> None:
        self.view.progress.setFormat("Done")
        self.view.progress.set_active(False)
        animate_button_emphasis(self.view.process_button, False)
        self._set_processing_enabled(True)
        if self.view._processing_thread is not None:
            self.view._processing_thread.deleteLater()
            self.view._processing_thread = None
        documentation_error = None
        if self.view.state.processing_options is not None:
            try:
                self.view.use_cases.record_session(
                    session_dir,
                    self.view.state.processing_video_paths,
                    self.view.state.processing_outputs,
                    self.view.state.processing_failures,
                    self.view.state.processing_options,
                    self.view.state.processing_trim_ranges_by_path,
                )
            except Exception as exc:
                documentation_error = str(exc)
        self.view.state.processing_options = None
        self.view.state.processing_video_paths = []
        self.view.state.processing_trim_ranges_by_path = {}
        if documentation_error is not None:
            self.view.state.processing_errors.append(f"Documentation: {documentation_error}")
        if self.view.state.processing_errors:
            self.view.process_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
            QMessageBox.warning(
                self.view,
                "Processing finished with errors",
                f"Output folder:\n{session_dir}\n\nFailed files:\n" + "\n".join(self.view.state.processing_errors[:8]),
            )
        else:
            self.view.process_button.setIcon(interface_icon("check", theme.PRIMARY_TEXT))
            QMessageBox.information(self.view, "Processing complete", f"Output folder:\n{session_dir}")

    def _current_processing_options(self) -> ProcessingOptions:
        crop_regions = self.view.preview.crop_regions()
        invert_regions = tuple(self.view.preview.invert_regions())
        return ProcessingOptions(
            crop_enabled=bool(crop_regions),
            crop_regions=crop_regions,
            invert_enabled=bool(invert_regions),
            invert_rects=invert_regions,
            enhancements=self.view.preview.enhancement_settings(),
            crf=self.view.crf_spin.value(),
            preset=self.view.preset_combo.currentText(),
        )

    def _export_video_manifest(self) -> None:
        (destination, _) = QFileDialog.getSaveFileName(
            self.view,
            "Export video settings manifest",
            str(self.view._default_output_root() / "video_settings_manifest.json"),
            "Video settings manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if not destination:
            return
        path = Path(destination).expanduser()
        if not path.suffix:
            path = path.with_suffix(".json")
        try:
            saved = self.view.use_cases.save_settings(
                path, self._current_processing_options(), self.view.trims._trim_ranges_for_manifest()
            )
        except OSError as exc:
            QMessageBox.critical(self.view, "Could not export video settings manifest", str(exc))
            return
        self.view.state.profile_manifest_path = Path(saved).expanduser().resolve()
        QMessageBox.information(self.view, "Video settings manifest exported", f"Saved:\n{saved}")

    def _import_video_manifest(self) -> None:
        (source, _) = QFileDialog.getOpenFileName(
            self.view,
            "Upload video settings manifest",
            str(self.view._default_output_root()),
            "Video settings manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if not source:
            return
        try:
            (options, trim_ranges_by_video) = self.view.use_cases.load_settings(source)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.view, "Could not upload video settings manifest", str(exc))
            return
        self.view.state.profile_manifest_path = Path(source).expanduser().resolve()
        self.view.preview.set_crop_regions(options.crop_regions)
        self.view.preview.set_invert_regions(options.invert_rects)
        self.view.preview.set_enhancements(options.enhancements)
        self.view.crf_spin.setValue(options.crf)
        self.view.preset_combo.setCurrentText(options.preset)
        self.view.trims._apply_imported_trim_ranges(trim_ranges_by_video)
        self.view.settings_panel.refresh()
        self.view.trims._refresh_trim_context()
        self._update_process_state()
        QMessageBox.information(self.view, "Video settings manifest uploaded", "Video settings were applied.")

    def _confirm_action(self, title: str, text: str, details: str = "") -> bool:
        message = QMessageBox(self.view)
        message.setIcon(QMessageBox.Icon.Question)
        message.setWindowTitle(title)
        message.setText(text)
        if details:
            message.setInformativeText(details)
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        message.setDefaultButton(QMessageBox.StandardButton.No)
        return message.exec() == QMessageBox.StandardButton.Yes

    def _update_process_state(self) -> None:
        self.view.process_button.setEnabled(self.view.video_list.count() > 0)

    def _set_processing_enabled(self, enabled: bool) -> None:
        self.view.add_videos_button.setEnabled(enabled)
        self.view.add_folder_button.setEnabled(enabled)
        self.view.remove_videos_button.setEnabled(enabled)
        self.view.clear_videos_button.setEnabled(enabled)
        self.view.process_button.setEnabled(enabled and self.view.video_list.count() > 0)
        self.view.import_video_manifest_button.setEnabled(enabled)
        self.view.export_video_manifest_button.setEnabled(enabled)
        self.view.crop_tool_button.setEnabled(enabled)
        self.view.enhancements_tool_button.setEnabled(enabled)
        self.view.trim_tool_button.setEnabled(enabled)
        self.view.crf_spin.setEnabled(enabled)
        self.view.preset_combo.setEnabled(enabled)
