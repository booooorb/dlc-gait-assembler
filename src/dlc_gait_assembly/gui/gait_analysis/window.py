from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.interaction import add_shortcut, install_wheel_value_guard, set_tooltip
from dlc_gait_assembly.services.pipeline.alma import (
    AlmaSettings,
    default_alma_root,
    load_alma_config_defaults,
    pixels_per_cm_from_calibration_map,
    run_alma_gait_analysis,
    settings_from_alma_config,
)
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.project_paths import find_project_root
from dlc_gait_assembly.services.video_processing import probe_video


STANDARD_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")
BODY_PART_ALIASES = {
    "toe": ("toe", "toer", "toel", "toe_r", "toe_l"),
    "mtp": ("mtp", "mtpr", "mtpl", "mtp_r", "mtp_l"),
    "ankle": ("ankle", "ankler", "anklel", "ankle_r", "ankle_l"),
    "knee": ("knee", "kneer", "kneel", "knee_r", "knee_l"),
    "hip": ("hip", "hipr", "hipl", "hip_r", "hip_l"),
    "iliac crest": ("iliac crest", "crest", "crestr", "crestl", "crest_r", "crest_l", "iliac crestr", "iliac crestl", "iliacr", "iliacl"),
}


class GaitAnalysisWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("GaitAnalysisWidget")
        self._project_root = find_project_root(__file__)
        self._alma_root = default_alma_root(self._project_root)
        self._selected_files: list[Path] = []
        self._worker: AlmaAnalysisThread | None = None
        self._defaults = settings_from_alma_config(load_alma_config_defaults(self._alma_root))
        self._calibration_map_path: Path | None = None
        self._calibration_map_source = ""
        self._raw_bodyparts: list[str] = []
        self._bodypart_combos: dict[str, QComboBox] = {}

        self._build_ui()
        self._install_interactions()
        self._connect_signals()
        self._apply_style()
        self._update_analysis_mode()
        self._update_calibration_method()
        self._update_run_state()

    def can_close(self, parent=None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                parent or self,
                "Gait analysis is running",
                "Wait for the current ALMA gait analysis run to finish before closing the window.",
            )
            return False
        return True

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        left_panel = QWidget()
        left_panel.setMinimumWidth(520)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        file_box = QGroupBox("ALMA input and output")
        file_layout = QVBoxLayout(file_box)
        button_row = QHBoxLayout()
        self.add_file_button = QPushButton("Add CSV")
        set_tooltip(self.add_file_button, "Add one ALMA or DeepLabCut coordinate CSV.", "Ctrl+O")
        self.add_folder_button = QPushButton("Add Folder")
        set_tooltip(self.add_folder_button, "Add every CSV in a folder.", "Ctrl+Shift+O")
        self.clear_files_button = QPushButton("Clear")
        set_tooltip(self.clear_files_button, "Clear the selected input CSV files.", "Ctrl+L")
        button_row.addWidget(self.add_file_button)
        button_row.addWidget(self.add_folder_button)
        button_row.addWidget(self.clear_files_button)
        file_layout.addLayout(button_row)

        self.file_list = QListWidget()
        file_layout.addWidget(self.file_list, 1)

        output_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit(str(self._default_output_root()))
        self.output_folder_button = QPushButton("Output")
        set_tooltip(self.output_folder_edit, "Folder where ALMA gait-analysis outputs will be saved.")
        set_tooltip(self.output_folder_button, "Choose the output folder.", "Ctrl+Shift+S")
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.output_folder_button)
        file_layout.addLayout(output_row)
        left_layout.addWidget(file_box, 2)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(10)
        settings_scroll.setWidget(settings_content)

        setup_box = QGroupBox("Experimental setup")
        setup_layout = QVBoxLayout(setup_box)
        self.analysis_type_group = QButtonGroup(self)
        self.treadmill_radio = QRadioButton("Treadmill")
        self.spontaneous_radio = QRadioButton("Spontaneous walking")
        set_tooltip(self.treadmill_radio, "Use treadmill gait-analysis settings.")
        set_tooltip(self.spontaneous_radio, "Use spontaneous-walking gait-analysis settings.")
        self.treadmill_radio.setChecked(self._defaults.analysis_type == "Treadmill")
        self.spontaneous_radio.setChecked(self._defaults.analysis_type == "Spontaneous walking")
        self.analysis_type_group.addButton(self.treadmill_radio)
        self.analysis_type_group.addButton(self.spontaneous_radio)
        setup_layout.addWidget(self.treadmill_radio)
        setup_layout.addWidget(self.spontaneous_radio)
        settings_layout.addWidget(setup_box)

        speed_box = QGroupBox("Treadmill speed and calibration")
        speed_layout = QGridLayout(speed_box)
        self.treadmill_speed_label = QLabel("Treadmill speed (cm/s)")
        self.treadmill_speed_spin = _double_spin(0.1, 100.0, self._defaults.treadmill_speed_cm_s, 1)
        self.frame_rate_spin = _double_spin(1.0, 1000.0, self._defaults.frame_rate, 1)
        self.load_fps_button = QPushButton("Load from video")
        set_tooltip(self.treadmill_speed_spin, "Treadmill belt speed in centimeters per second.")
        set_tooltip(self.frame_rate_spin, "Coordinate-video frame rate in frames per second.")
        set_tooltip(self.load_fps_button, "Load frame rate from a video file.", "Ctrl+F")
        speed_layout.addWidget(self.treadmill_speed_label, 0, 0)
        speed_layout.addWidget(self.treadmill_speed_spin, 0, 1, 1, 2)
        speed_layout.addWidget(QLabel("Frame rate (fps)"), 1, 0)
        speed_layout.addWidget(self.frame_rate_spin, 1, 1)
        speed_layout.addWidget(self.load_fps_button, 1, 2)
        settings_layout.addWidget(speed_box)

        calibration_box = QGroupBox("Spatial calibration")
        calibration_layout = QVBoxLayout(calibration_box)
        self.calibration_method_group = QButtonGroup(self)
        self.reference_radio = QRadioButton("Reference body segment (recommended)")
        self.manual_radio = QRadioButton("Manual pixel-to-cm ratio")
        set_tooltip(self.reference_radio, "Calculate scale from a tracked anatomical reference segment.")
        set_tooltip(self.manual_radio, "Use a manually supplied pixels-per-centimeter calibration.")
        self.reference_radio.setChecked(self._defaults.calibration_method == "reference")
        self.manual_radio.setChecked(self._defaults.calibration_method == "manual")
        self.calibration_method_group.addButton(self.reference_radio)
        self.calibration_method_group.addButton(self.manual_radio)
        calibration_layout.addWidget(self.reference_radio)
        calibration_layout.addWidget(self.manual_radio)

        self.reference_settings_widget = QWidget()
        reference_layout = QGridLayout(self.reference_settings_widget)
        reference_layout.setContentsMargins(16, 2, 0, 0)
        self.reference_segment_combo = QComboBox()
        self.reference_segment_combo.addItems(["ankle_toe (1.5cm)", "hip_knee (2.5cm)", "knee_ankle (2.0cm)", "ankle_mtp (0.8cm)"])
        self.reference_segment_combo.setCurrentText(_reference_segment_label(self._defaults.reference_segment))
        self.reference_length_spin = _double_spin(0.1, 10.0, self._defaults.reference_length_cm, 2)
        set_tooltip(self.reference_segment_combo, "Body segment used as the reference calibration length.")
        set_tooltip(self.reference_length_spin, "Known length of the selected reference segment in centimeters.")
        reference_layout.addWidget(QLabel("Reference Segment"), 0, 0)
        reference_layout.addWidget(self.reference_segment_combo, 0, 1)
        reference_layout.addWidget(QLabel("Segment Length (cm)"), 1, 0)
        reference_layout.addWidget(self.reference_length_spin, 1, 1)
        calibration_layout.addWidget(self.reference_settings_widget)

        self.manual_settings_widget = QWidget()
        manual_layout = QGridLayout(self.manual_settings_widget)
        manual_layout.setContentsMargins(16, 2, 0, 0)
        self.pixels_per_cm_spin = _double_spin(1.0, 1000.0, self._defaults.pixels_per_cm or 50.0, 3)
        self.import_calibration_map_button = QPushButton("Import Calibration Map")
        set_tooltip(self.pixels_per_cm_spin, "Manual pixel-to-centimeter ratio.")
        set_tooltip(self.import_calibration_map_button, "Import a calibration conversion map.", "Ctrl+M")
        self.calibration_map_label = QLabel("No calibration map imported.")
        self.calibration_map_label.setObjectName("MutedLabel")
        self.calibration_map_label.setWordWrap(True)
        manual_layout.addWidget(QLabel("Pixels per CM"), 0, 0)
        manual_layout.addWidget(self.pixels_per_cm_spin, 0, 1)
        manual_layout.addWidget(self.import_calibration_map_button, 1, 0, 1, 2)
        manual_layout.addWidget(self.calibration_map_label, 2, 0, 1, 2)
        calibration_layout.addWidget(self.manual_settings_widget)
        settings_layout.addWidget(calibration_box)

        movement_box = QGroupBox("Movement Analysis Settings")
        movement_layout = QGridLayout(movement_box)
        self.filter_cutoff_spin = _double_spin(0.1, 50.0, self._defaults.filter_cutoff, 1)
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Auto-detect", "Left-to-Right", "Right-to-Left"])
        if self._defaults.right_to_left == "auto":
            self.direction_combo.setCurrentText("Auto-detect")
        elif self._defaults.right_to_left:
            self.direction_combo.setCurrentText("Right-to-Left")
        else:
            self.direction_combo.setCurrentText("Left-to-Right")
        self.drag_clearance_spin = _double_spin(0.01, 2.0, self._defaults.drag_clearance_cm, 2)
        self.drag_frames_spin = QSpinBox()
        self.drag_frames_spin.setRange(1, 10)
        self.drag_frames_spin.setValue(self._defaults.drag_min_consecutive_frames)
        set_tooltip(self.direction_combo, "Expected walking direction, or automatic direction detection.")
        set_tooltip(self.drag_clearance_spin, "Toe clearance threshold used by drag detection.")
        set_tooltip(self.drag_frames_spin, "Number of consecutive frames required for drag detection.")
        set_tooltip(self.filter_cutoff_spin, "Low-pass filter cutoff frequency in Hz.")
        movement_layout.addWidget(QLabel("Walking Direction"), 0, 0)
        movement_layout.addWidget(self.direction_combo, 0, 1)
        movement_layout.addWidget(QLabel("Drag Clearance Threshold (cm)"), 1, 0)
        movement_layout.addWidget(self.drag_clearance_spin, 1, 1)
        movement_layout.addWidget(QLabel("Drag Detection Sensitivity (frames)"), 2, 0)
        movement_layout.addWidget(self.drag_frames_spin, 2, 1)
        movement_layout.addWidget(QLabel("Lowpass Filter Cutoff (Hz)"), 3, 0)
        movement_layout.addWidget(self.filter_cutoff_spin, 3, 1)
        settings_layout.addWidget(movement_box)

        spontaneous_box = QGroupBox("Spontaneous Walking Options")
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
        settings_layout.addWidget(spontaneous_box)

        filter_box = QGroupBox("Stride Filtering (Optional)")
        filter_layout = QGridLayout(filter_box)
        self.step_height_min_spin = _double_spin(0.0, 5.0, self._defaults.step_height_min_cm, 2)
        self.step_height_max_spin = _double_spin(0.0, 5.0, self._defaults.step_height_max_cm, 2)
        self.stride_length_min_spin = _double_spin(0.0, 20.0, self._defaults.stride_length_min_cm, 2)
        self.stride_length_max_spin = _double_spin(0.0, 20.0, self._defaults.stride_length_max_cm, 2)
        set_tooltip(self.step_height_min_spin, "Minimum accepted step height in centimeters.")
        set_tooltip(self.step_height_max_spin, "Maximum accepted step height in centimeters.")
        set_tooltip(self.stride_length_min_spin, "Minimum accepted stride length in centimeters.")
        set_tooltip(self.stride_length_max_spin, "Maximum accepted stride length in centimeters.")
        filter_layout.addWidget(QLabel("Step height min (cm)"), 0, 0)
        filter_layout.addWidget(self.step_height_min_spin, 0, 1)
        filter_layout.addWidget(QLabel("Step height max (cm)"), 1, 0)
        filter_layout.addWidget(self.step_height_max_spin, 1, 1)
        filter_layout.addWidget(QLabel("Stride length min (cm)"), 2, 0)
        filter_layout.addWidget(self.stride_length_min_spin, 2, 1)
        filter_layout.addWidget(QLabel("Stride length max (cm)"), 3, 0)
        filter_layout.addWidget(self.stride_length_max_spin, 3, 1)
        settings_layout.addWidget(filter_box)

        output_options_box = QGroupBox("Output options")
        output_options_layout = QGridLayout(output_options_box)
        self.continuous_strides_spin = QSpinBox()
        self.continuous_strides_spin.setRange(1, 50)
        self.continuous_strides_spin.setValue(self._defaults.n_continuous_strides)
        self.stickplot_checkbox = QCheckBox("Generate stickplot SVG")
        self.stickplot_checkbox.setChecked(True)
        set_tooltip(self.continuous_strides_spin, "Number of continuous strides used for ALMA outputs.")
        set_tooltip(self.stickplot_checkbox, "Generate an SVG stickplot output.")
        output_options_layout.addWidget(QLabel("Continuous strides"), 0, 0)
        output_options_layout.addWidget(self.continuous_strides_spin, 0, 1)
        output_options_layout.addWidget(self.stickplot_checkbox, 1, 0, 1, 2)
        settings_layout.addWidget(output_options_box)
        settings_layout.addStretch(1)

        left_layout.addWidget(settings_scroll, 5)

        self.run_button = QPushButton("Run ALMA Gait Analysis")
        self.run_button.setObjectName("PrimaryButton")
        set_tooltip(self.run_button, "Run ALMA gait analysis on the selected CSV files.", "Ctrl+R")
        left_layout.addWidget(self.run_button)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)
        self.status_label = QLabel("Select CSV coordinate files to begin.")
        self.status_label.setObjectName("PreviewTitle")
        right_layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(190)
        right_layout.addWidget(self.log, 1)

        mapping_box = QGroupBox("Body Part Mapping")
        mapping_box.setMaximumHeight(210)
        mapping_layout = QVBoxLayout(mapping_box)
        mapping_layout.setSpacing(6)
        mapping_header = QHBoxLayout()
        self.use_custom_mapping_checkbox = QCheckBox("Use custom mapping")
        self.reload_mapping_button = QPushButton("Load From CSV")
        self.auto_mapping_button = QPushButton("Auto Detect")
        set_tooltip(self.use_custom_mapping_checkbox, "Manually map raw DLC labels to the expected ALMA body parts.")
        set_tooltip(self.reload_mapping_button, "Load body-part labels from the first selected CSV.")
        set_tooltip(self.auto_mapping_button, "Automatically match common DLC body-part labels.")
        mapping_header.addWidget(self.use_custom_mapping_checkbox)
        mapping_header.addStretch(1)
        mapping_header.addWidget(self.reload_mapping_button)
        mapping_header.addWidget(self.auto_mapping_button)
        mapping_layout.addLayout(mapping_header)

        self.mapping_status_label = QLabel("Add a CSV to detect labels.")
        self.mapping_status_label.setObjectName("MutedLabel")
        mapping_layout.addWidget(self.mapping_status_label)

        mapping_grid = QGridLayout()
        mapping_grid.setHorizontalSpacing(10)
        mapping_grid.setVerticalSpacing(4)
        for index, standard_bodypart in enumerate(STANDARD_BODYPARTS):
            row = index // 2
            column = (index % 2) * 2
            label = QLabel(standard_bodypart)
            combo = QComboBox()
            combo.setMinimumWidth(130)
            combo.setEnabled(False)
            set_tooltip(combo, f"Raw DLC label to use as {standard_bodypart}.")
            self._bodypart_combos[standard_bodypart] = combo
            mapping_grid.addWidget(label, row, column)
            mapping_grid.addWidget(combo, row, column + 1)
        mapping_layout.addLayout(mapping_grid)
        right_layout.addWidget(mapping_box)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([640, 640])

    def _install_interactions(self) -> None:
        self._shortcuts = [
            add_shortcut(self, "Ctrl+O", self._add_file),
            add_shortcut(self, "Ctrl+Shift+O", self._add_folder),
            add_shortcut(self, "Ctrl+L", self._clear_files),
            add_shortcut(self, "Ctrl+Shift+S", self._select_output_folder),
            add_shortcut(self, "Ctrl+F", self._load_frame_rate_from_video),
            add_shortcut(self, "Ctrl+M", self._import_calibration_map),
            add_shortcut(self, "Ctrl+R", self._run_analysis),
        ]
        self._wheel_value_guard = install_wheel_value_guard(self)

    def _connect_signals(self) -> None:
        self.add_file_button.clicked.connect(self._add_file)
        self.add_folder_button.clicked.connect(self._add_folder)
        self.clear_files_button.clicked.connect(self._clear_files)
        self.output_folder_button.clicked.connect(self._select_output_folder)
        self.run_button.clicked.connect(self._run_analysis)
        self.treadmill_radio.toggled.connect(self._update_analysis_mode)
        self.reference_radio.toggled.connect(self._update_calibration_method)
        self.load_fps_button.clicked.connect(self._load_frame_rate_from_video)
        self.import_calibration_map_button.clicked.connect(self._import_calibration_map)
        self.use_custom_mapping_checkbox.toggled.connect(self._update_mapping_enabled)
        self.reload_mapping_button.clicked.connect(self._load_bodypart_mapping_from_first_file)
        self.auto_mapping_button.clicked.connect(self._apply_auto_bodypart_mapping)
        self.file_list.model().rowsInserted.connect(self._update_run_state)
        self.file_list.model().rowsRemoved.connect(self._update_run_state)

    def _add_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Select ALMA/DLC coordinate CSV", str(self._project_root), "CSV files (*.csv);;All files (*)")
        if filename:
            self._add_csv_paths([Path(filename)])

    def _add_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select folder containing CSV files", str(self._project_root))
        if directory:
            self._add_csv_paths(sorted(Path(directory).glob("*.csv")))

    def _add_csv_paths(self, paths: list[Path]) -> None:
        existing = {str(path) for path in self._selected_files}
        for path in paths:
            resolved = path.expanduser().resolve()
            if resolved.suffix.lower() != ".csv" or str(resolved) in existing:
                continue
            self._selected_files.append(resolved)
            self.file_list.addItem(str(resolved))
            existing.add(str(resolved))
        if self._selected_files and not self._raw_bodyparts:
            self._load_bodypart_mapping_from_first_file()
        self._update_run_state()

    def _clear_files(self) -> None:
        self._selected_files.clear()
        self.file_list.clear()
        self._raw_bodyparts = []
        self._refresh_bodypart_mapping_choices()
        self.mapping_status_label.setText("Add a CSV to detect labels.")
        self._update_run_state()

    def _select_output_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select ALMA output folder", self.output_folder_edit.text())
        if directory:
            self.output_folder_edit.setText(directory)
            self._update_run_state()

    def _load_frame_rate_from_video(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select video to read frame rate",
            str(self._project_root),
            f"Video files ({extensions});;All files (*)",
        )
        if not filename:
            return

        try:
            info = probe_video(filename)
        except Exception as exc:
            QMessageBox.critical(self, "Could not read frame rate", str(exc))
            return

        if info.fps <= 0:
            QMessageBox.warning(self, "No frame rate detected", "The selected video did not report a usable frame rate.")
            return

        fps = round(info.fps, 2)
        self.frame_rate_spin.setValue(fps)
        self.status_label.setText(f"Frame rate detected: {fps:g} fps")
        self._append_log(f"Frame rate loaded from {Path(filename).name}: {fps:g} fps")

    def _import_calibration_map(self) -> None:
        default_folder = self._project_root / "outputs" / "calibration"
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import calibration conversion map",
            str(default_folder if default_folder.exists() else self._project_root),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if not filename:
            return

        path = Path(filename).expanduser().resolve()
        try:
            pixels_per_cm, source = pixels_per_cm_from_calibration_map(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not import calibration map", str(exc))
            return

        self._calibration_map_path = path
        self._calibration_map_source = source
        self.manual_radio.setChecked(True)
        self.pixels_per_cm_spin.setValue(pixels_per_cm)
        self.calibration_map_label.setText(f"{path.name} | {source}: {pixels_per_cm:.3f} px/cm")
        self.status_label.setText("Calibration map imported.")
        self._append_log(f"Calibration map imported from {path}: {pixels_per_cm:.3f} px/cm ({source})")
        self._update_calibration_method()

    def _load_bodypart_mapping_from_first_file(self) -> None:
        if not self._selected_files:
            QMessageBox.information(self, "No input files", "Add a CSV file before loading body part labels.")
            return

        csv_path = self._selected_files[0]
        try:
            self._raw_bodyparts = _read_dlc_bodyparts(csv_path)
        except Exception as exc:
            self._raw_bodyparts = []
            self._refresh_bodypart_mapping_choices()
            self.mapping_status_label.setText("Could not read body part labels.")
            QMessageBox.critical(self, "Could not read body part labels", str(exc))
            return

        self._refresh_bodypart_mapping_choices()
        self._apply_auto_bodypart_mapping()
        self.mapping_status_label.setText(f"{len(self._raw_bodyparts)} labels loaded from {csv_path.name}.")

    def _refresh_bodypart_mapping_choices(self) -> None:
        choices = ["(none)", *self._raw_bodyparts]
        for combo in self._bodypart_combos.values():
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(choices)
            if current in choices:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        self._update_mapping_enabled()

    def _apply_auto_bodypart_mapping(self) -> None:
        if not self._raw_bodyparts:
            return
        for standard_bodypart, combo in self._bodypart_combos.items():
            auto_label = _auto_bodypart_label(self._raw_bodyparts, standard_bodypart)
            combo.setCurrentText(auto_label or "(none)")

    def _update_mapping_enabled(self) -> None:
        enabled = self.use_custom_mapping_checkbox.isChecked() and bool(self._raw_bodyparts)
        for combo in self._bodypart_combos.values():
            combo.setEnabled(enabled)

    def _update_analysis_mode(self) -> None:
        treadmill = self.treadmill_radio.isChecked()
        self.treadmill_speed_label.setVisible(treadmill)
        self.treadmill_speed_spin.setVisible(treadmill)
        self.spontaneous_box.setVisible(not treadmill)

    def _update_calibration_method(self) -> None:
        reference = self.reference_radio.isChecked()
        self.reference_settings_widget.setVisible(reference)
        self.manual_settings_widget.setVisible(not reference)

    def _update_run_state(self) -> None:
        has_files = bool(self._selected_files)
        has_output = bool(self.output_folder_edit.text().strip())
        running = self._worker is not None and self._worker.isRunning()
        self.run_button.setEnabled(has_files and has_output and not running)

    def _run_analysis(self) -> None:
        output_folder = Path(self.output_folder_edit.text()).expanduser().resolve()
        if not self._selected_files:
            QMessageBox.information(self, "No input files", "Add at least one CSV coordinate file.")
            return

        settings = self._collect_settings()
        if self.use_custom_mapping_checkbox.isChecked() and not settings.custom_bodypart_mapping:
            QMessageBox.warning(self, "No body part mapping", "Select at least one body part mapping or turn off custom mapping.")
            return
        self.progress.setValue(0)
        self.log.clear()
        self.status_label.setText("Running ALMA gait analysis...")
        self.run_button.setEnabled(False)

        self._worker = AlmaAnalysisThread(self._selected_files, output_folder, settings, self._alma_root)
        self._worker.progress_updated.connect(self._update_progress)
        self._worker.log_message.connect(self._append_log)
        self._worker.analysis_completed.connect(self._analysis_completed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _collect_settings(self) -> AlmaSettings:
        if self.direction_combo.currentText() == "Auto-detect":
            right_to_left: bool | str = "auto"
        elif self.direction_combo.currentText() == "Right-to-Left":
            right_to_left = True
        else:
            right_to_left = False

        return AlmaSettings(
            analysis_type="Treadmill" if self.treadmill_radio.isChecked() else "Spontaneous walking",
            frame_rate=self.frame_rate_spin.value(),
            filter_cutoff=self.filter_cutoff_spin.value(),
            treadmill_speed_cm_s=self.treadmill_speed_spin.value(),
            calibration_method="reference" if self.reference_radio.isChecked() else "manual",
            reference_segment=self.reference_segment_combo.currentText().split(" ", 1)[0],
            reference_length_cm=self.reference_length_spin.value(),
            calibration_map_path=self._calibration_map_path,
            right_to_left=right_to_left,
            pixels_per_cm=self.pixels_per_cm_spin.value() if self.manual_radio.isChecked() else None,
            no_outlier_filter=self.no_outlier_checkbox.isChecked(),
            dragging_filter=self.dragging_filter_checkbox.isChecked(),
            drag_clearance_cm=self.drag_clearance_spin.value(),
            drag_min_consecutive_frames=self.drag_frames_spin.value(),
            step_height_min_cm=self.step_height_min_spin.value(),
            step_height_max_cm=self.step_height_max_spin.value(),
            stride_length_min_cm=self.stride_length_min_spin.value(),
            stride_length_max_cm=self.stride_length_max_spin.value(),
            n_continuous_strides=self.continuous_strides_spin.value(),
            generate_stickplot=self.stickplot_checkbox.isChecked(),
            custom_bodypart_mapping=self._collect_bodypart_mapping(),
        )

    def _collect_bodypart_mapping(self) -> dict[str, str] | None:
        if not self.use_custom_mapping_checkbox.isChecked():
            return None

        mapping: dict[str, str] = {}
        for standard_bodypart, combo in self._bodypart_combos.items():
            raw_bodypart = combo.currentText()
            if raw_bodypart and raw_bodypart != "(none)":
                mapping[raw_bodypart] = standard_bodypart
        return mapping or None

    def _update_progress(self, value: int, text: str) -> None:
        self.progress.setValue(value)
        self.status_label.setText(text)

    def _append_log(self, text: str) -> None:
        self.log.append(text)

    def _analysis_completed(self, success: bool, message: str) -> None:
        self.status_label.setText(message)
        self.progress.setValue(100 if success else self.progress.value())
        if success:
            QMessageBox.information(self, "ALMA gait analysis complete", message)
        else:
            QMessageBox.critical(self, "ALMA gait analysis failed", message)

    def _worker_finished(self) -> None:
        self._worker = None
        self._update_run_state()

    def _default_output_root(self) -> Path:
        output_root = self._project_root / "outputs" / "gait_analysis"
        output_root.mkdir(parents=True, exist_ok=True)
        return output_root

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
            QWidget#GaitAnalysisWidget {
                background: {theme.BACKGROUND};
                color: {theme.TEXT};
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QGroupBox {
                border: 1px solid {theme.ACCENT};
                border-radius: 2px;
                margin-top: 18px;
                padding: 16px 10px 10px 10px;
                background: {theme.SURFACE};
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 5px;
                padding: 0 3px;
                color: {theme.TEXT};
                font-weight: 600;
                background: {theme.BACKGROUND};
            }
            QLabel#TitleLabel {
                font-size: 19px;
                font-weight: 650;
            }
            QLabel#PreviewTitle {
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#MutedLabel {
                color: {theme.TEXT};
                font-size: 12px;
            }
            QPushButton {
                border: 1px solid {theme.ACCENT};
                border-radius: 3px;
                padding: 7px 10px;
                background: {theme.SURFACE};
                color: {theme.TEXT};
                font-weight: 550;
            }
            QPushButton:hover {
                background: {theme.PANEL};
                border-color: {theme.TEXT};
                color: {theme.TEXT};
            }
            QPushButton#PrimaryButton {
                background: {theme.PRIMARY};
                border-color: {theme.PRIMARY};
                color: {theme.PRIMARY_TEXT};
                font-weight: 650;
                padding: 10px;
            }
            QPushButton#PrimaryButton:hover {
                background: {theme.PANEL};
                border-color: {theme.TEXT};
                color: {theme.TEXT};
            }
            QListWidget, QTextEdit, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
                border: 1px solid {theme.ACCENT};
                border-radius: 2px;
                background: {theme.SURFACE};
                padding: 5px 6px;
            }
            QProgressBar {
                border: 1px solid {theme.ACCENT};
                border-radius: 2px;
                background: {theme.SURFACE};
                height: 16px;
            }
            QProgressBar::chunk {
                border-radius: 1px;
                background: {theme.PRIMARY};
            }
            """
            )
        )


class AlmaAnalysisThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    analysis_completed = Signal(bool, str)

    def __init__(self, files: list[Path], output_folder: Path, settings: AlmaSettings, alma_root: Path):
        super().__init__()
        self._files = files
        self._output_folder = output_folder
        self._settings = settings
        self._alma_root = alma_root

    def run(self) -> None:
        try:
            self.log_message.emit(f"ALMA root: {self._alma_root}")
            self.log_message.emit(f"Output folder: {self._output_folder}")
            self.log_message.emit(f"Setup: {self._settings.analysis_type}")
            self.log_message.emit(f"Frame rate: {self._settings.frame_rate:g} fps")
            self.log_message.emit(f"Calibration method: {self._settings.calibration_method}")
            if self._settings.calibration_method == "manual":
                self.log_message.emit(f"Pixels per CM: {self._settings.pixels_per_cm:g}")
                if self._settings.calibration_map_path is not None:
                    self.log_message.emit(f"Calibration map: {self._settings.calibration_map_path}")
            if self._settings.custom_bodypart_mapping:
                self.log_message.emit(f"Body part mapping: {self._settings.custom_bodypart_mapping}")

            def progress(index: int, total: int, message: str) -> None:
                value = 10 + int((index - 1) * 80 / max(1, total))
                self.progress_updated.emit(value, message)
                self.log_message.emit(message)

            results = run_alma_gait_analysis(
                self._files,
                self._output_folder,
                self._settings,
                self._alma_root,
                progress_callback=progress,
            )
            for result in results:
                self.log_message.emit(f"{result.input_file.name}:")
                for output in result.output_files:
                    self.log_message.emit(f"  {output}")
            self.progress_updated.emit(100, "ALMA gait analysis complete.")
            self.analysis_completed.emit(True, f"Analysis complete. Results saved to:\n{self._output_folder}")
        except Exception as exc:
            self.analysis_completed.emit(False, str(exc))


def _double_spin(minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    spin.setDecimals(decimals)
    return spin


def _reference_segment_label(segment: str) -> str:
    labels = {
        "ankle_toe": "ankle_toe (1.5cm)",
        "hip_knee": "hip_knee (2.5cm)",
        "knee_ankle": "knee_ankle (2.0cm)",
        "ankle_mtp": "ankle_mtp (0.8cm)",
    }
    return labels.get(segment, "ankle_toe (1.5cm)")


def _read_dlc_bodyparts(csv_path: Path) -> list[str]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
            bodyparts = next(reader)
            coords = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{csv_path} does not look like a DeepLabCut CSV with scorer/bodyparts/coords rows.") from exc

    labels: list[str] = []
    seen: set[str] = set()
    for bodypart, coord in zip(bodyparts, coords):
        label = bodypart.strip()
        if coord.strip().lower() == "x" and label and label not in seen:
            labels.append(label)
            seen.add(label)
    if not labels:
        raise ValueError(f"No body part labels were found in {csv_path}.")
    return labels


def _auto_bodypart_label(raw_bodyparts: list[str], standard_bodypart: str) -> str | None:
    aliases = set(BODY_PART_ALIASES.get(standard_bodypart, (standard_bodypart,)))
    for raw_bodypart in raw_bodyparts:
        if raw_bodypart.strip().lower() in aliases:
            return raw_bodypart
    return None
