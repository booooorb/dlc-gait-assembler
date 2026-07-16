from __future__ import annotations

import csv
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, Qt, QThread, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.interaction import add_shortcut, install_wheel_value_guard, set_tooltip
from dlc_gait_assembly.gui.shared.progress import DynamicProgressBar
from dlc_gait_assembly.services.analysis_manifests import write_analysis_manifest
from dlc_gait_assembly.services.pipeline.alma import (
    AlmaSettings,
    AlmaViewCsvSet,
    default_alma_root,
    load_alma_config_defaults,
    pixels_per_cm_from_calibration_map,
    run_alma_gait_analysis,
    settings_from_alma_config,
)
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.project_paths import (
    find_project_root,
    manual_pipeline_output_folders,
)
from dlc_gait_assembly.services.video_processing import probe_video


STANDARD_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")
SIDE_VIEW_LABELS = STANDARD_BODYPARTS
BOTTOM_VIEW_LABELS = ("center back", "back left", "back right", "body reference")
MULTI_SIDE_VIEW_MODE_LABEL = "Multi side view"
SINGLE_SIDE_VIEW_MODE_LABEL = "Single side view"
BODY_PART_ALIASES = {
    "toe": ("toe", "toer", "toel", "toe_r", "toe_l", "l-back-toe", "l-back-toe_tip", "r-back-toe", "r-back-toe_tip"),
    "mtp": ("mtp", "mtpr", "mtpl", "mtp_r", "mtp_l", "l-back-mtp", "r-back-mtp"),
    "ankle": ("ankle", "ankler", "anklel", "ankle_r", "ankle_l", "l-back-ankle", "r-back-ankle"),
    "knee": ("knee", "kneer", "kneel", "knee_r", "knee_l", "l-back-knee", "r-back-knee"),
    "hip": ("hip", "hipr", "hipl", "hip_r", "hip_l", "l-hip", "r-hip"),
    "iliac crest": (
        "iliac crest",
        "iliac-crest",
        "iliac_crest",
        "crest",
        "crestr",
        "crestl",
        "crest_r",
        "crest_l",
        "iliac crestr",
        "iliac crestl",
        "iliacr",
        "iliacl",
        "l-iliac-crest",
        "r-iliac-crest",
    ),
    "center back": ("center back", "center-back", "centre back", "centre-back", "back-center", "back-centre", "d-center-back"),
    "back left": ("back left", "back-left", "left back", "left-back", "d-back-left"),
    "back right": ("back right", "back-right", "right back", "right-back", "d-back-right"),
    "body reference": ("body reference", "body-reference", "reference", "ref", "tail base", "tail-base"),
}


class DoubleClickSvgWidget(QSvgWidget):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()


class StickPlotPairPreviewWidget(QWidget):
    double_clicked = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        self._panels: list[tuple[QLabel, QSvgWidget]] = []
        for _index in range(2):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(4)
            label = QLabel("")
            label.setObjectName("MutedLabel")
            label.setAlignment(Qt.AlignCenter)
            svg = QSvgWidget()
            svg.setObjectName("StickPlotSvg")
            svg.setMinimumSize(150, 104)
            svg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            panel_layout.addWidget(label, 0)
            panel_layout.addWidget(svg, 1)
            layout.addWidget(panel, 1)
            panel.installEventFilter(self)
            label.installEventFilter(self)
            svg.installEventFilter(self)
            self._panels.append((label, svg))
        self._panels[1][0].parentWidget().hide()

    def load_plots(self, plots: tuple[tuple[str, bytes], ...]) -> None:
        for index, (label, svg) in enumerate(self._panels):
            panel = label.parentWidget()
            if index < len(plots):
                plot_label, svg_data = plots[index]
                label.setText(plot_label)
                svg.load(QByteArray(_qt_safe_svg_bytes(svg_data)))
                panel.show()
            else:
                panel.hide()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.MouseButtonDblClick:
            self.double_clicked.emit()
            event.accept()
            return True
        return super().eventFilter(watched, event)


class AlmaKinematicsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("GaitAnalysisWidget")
        self._project_root = find_project_root(__file__)
        self._alma_root = default_alma_root(self._project_root)
        self._selected_files: list[Path] = []
        self._view_sets: list[AlmaViewCsvSet] = []
        self._view_set_errors: list[str] = []
        self._manual_view_sets: list[AlmaViewCsvSet] | None = None
        self._worker: AlmaAnalysisThread | None = None
        self._preview_worker: StickPlotPreviewThread | None = None
        self._large_stickplot_dialog: StickPlotPreviewDialog | None = None
        self._stickplot_preview_ready = False
        self._preview_invalidated_while_running = False
        self._preview_svg_data: tuple[tuple[str, bytes], ...] | None = None
        self._preview_source_name = ""
        self._defaults = settings_from_alma_config(load_alma_config_defaults(self._alma_root))
        self._calibration_map_path: Path | None = None
        self._calibration_map_source = ""
        self._raw_bodyparts: list[str] = []
        self._bodypart_combos: dict[str, QComboBox] = {}
        self._view_label_mappings: dict[str, dict[str, dict[str, str]]] = {}

        self._build_ui()
        self._install_interactions()
        self._connect_signals()
        self._apply_style()
        self._update_input_mode()
        self._update_analysis_mode()
        self._update_calibration_method()
        self._update_run_state()

    def can_close(self, parent=None) -> bool:
        analysis_running = self._worker is not None and self._worker.isRunning()
        preview_running = self._preview_worker is not None and self._preview_worker.isRunning()
        if analysis_running or preview_running:
            QMessageBox.information(
                parent or self,
                "Gait processing is running",
                "Wait for the current stick-plot preview or gait-analysis run to finish before closing the window.",
            )
            return False
        return True

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header.setObjectName("WorkspaceHeader")
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 0)
        header_layout.setSpacing(12)
        title = QLabel("Runway analysis")
        title.setObjectName("TitleLabel")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        root.addWidget(header, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_panel.setMinimumWidth(440)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        file_box = QGroupBox("Multi-view ALMA input and output")
        file_layout = QVBoxLayout(file_box)
        button_row = QHBoxLayout()
        self.add_file_button = QPushButton("Add CSVs")
        set_tooltip(self.add_file_button, "Add left, right, and bottom DeepLabCut coordinate CSVs.", "Ctrl+O")
        self.add_folder_button = QPushButton("Add folder")
        set_tooltip(self.add_folder_button, "Add every CSV in a folder and group left/right/bottom views.", "Ctrl+Shift+O")
        self.clear_files_button = QPushButton("Clear")
        set_tooltip(self.clear_files_button, "Clear the selected input CSV files.", "Ctrl+L")
        button_row.addWidget(self.add_file_button)
        button_row.addWidget(self.add_folder_button)
        button_row.addWidget(self.clear_files_button)
        file_layout.addLayout(button_row)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(96)
        self.file_list.setVisible(False)
        file_layout.addWidget(self.file_list)
        self.view_set_table = QTreeWidget()
        self.view_set_table.setObjectName("RunwayViewSetTable")
        self.view_set_table.setHeaderLabels(
            ["CSV set", "Left side view CSV", "Right side view CSV", "Bottom view CSV", "Pairing"]
        )
        self.view_set_table.setRootIsDecorated(False)
        self.view_set_table.setAlternatingRowColors(False)
        self.view_set_table.setMinimumHeight(128)
        self.view_set_table.setMaximumHeight(180)
        self.view_set_table.header().setStretchLastSection(False)
        self.view_set_table.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.view_set_table.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.view_set_table.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.view_set_table.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.view_set_table.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        file_layout.addWidget(self.view_set_table)
        self.view_set_status_label = QLabel("Add matched left, right, and bottom CSVs.")
        self.view_set_status_label.setObjectName("MutedLabel")
        self.view_set_status_label.setWordWrap(True)
        file_layout.addWidget(self.view_set_status_label)
        pairing_row = QHBoxLayout()
        self.edit_pairing_button = QPushButton("Edit CSV pairing...")
        self.label_matching_button = QPushButton("Label body parts...")
        set_tooltip(self.edit_pairing_button, "Assign selected CSV files to left side, right side, and bottom views.")
        set_tooltip(self.label_matching_button, "Map body-part labels for the selected left/right/bottom CSV set.")
        pairing_row.addWidget(self.edit_pairing_button)
        pairing_row.addWidget(self.label_matching_button)
        file_layout.addLayout(pairing_row)

        output_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit(str(self._default_output_root()))
        self.output_folder_button = QPushButton("Output")
        set_tooltip(self.output_folder_edit, "Folder where ALMA gait-analysis outputs will be saved.")
        set_tooltip(self.output_folder_button, "Choose the output folder.", "Ctrl+Shift+S")
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.output_folder_button)
        file_layout.addLayout(output_row)
        settings_tabs = QTabWidget()
        settings_tabs.setObjectName("RunwaySettingsTabs")
        settings_tabs.setDocumentMode(True)
        settings_tabs.tabBar().setExpanding(True)
        self.settings_tabs = settings_tabs
        setup_tab = QWidget()
        setup_tab_layout = QVBoxLayout(setup_tab)
        setup_tab_layout.setContentsMargins(6, 6, 6, 6)
        setup_tab_layout.setSpacing(3)
        analysis_tab = QWidget()
        analysis_tab_layout = QVBoxLayout(analysis_tab)
        analysis_tab_layout.setContentsMargins(6, 6, 6, 6)
        analysis_tab_layout.setSpacing(3)
        calibration_tab = QWidget()
        calibration_tab_layout = QVBoxLayout(calibration_tab)
        calibration_tab_layout.setContentsMargins(6, 6, 6, 6)
        calibration_tab_layout.setSpacing(3)
        filters_tab = QWidget()
        filters_tab_layout = QVBoxLayout(filters_tab)
        filters_tab_layout.setContentsMargins(6, 6, 6, 6)
        filters_tab_layout.setSpacing(3)
        mapping_tab = QWidget()
        mapping_tab_layout = QVBoxLayout(mapping_tab)
        mapping_tab_layout.setContentsMargins(6, 6, 6, 6)
        mapping_tab_layout.setSpacing(8)
        output_tab = QWidget()
        output_tab_layout = QVBoxLayout(output_tab)
        output_tab_layout.setContentsMargins(6, 6, 6, 6)
        output_tab_layout.setSpacing(3)
        settings_tabs.addTab(setup_tab, "Setup")
        settings_tabs.addTab(calibration_tab, "Calibration")
        settings_tabs.addTab(analysis_tab, "Analysis")
        settings_tabs.addTab(filters_tab, "Filters")
        settings_tabs.addTab(mapping_tab, "Mapping")
        settings_tabs.addTab(output_tab, "Output")
        self.mapping_tab = mapping_tab

        setup_box = QGroupBox("Experimental setup")
        setup_layout = QGridLayout(setup_box)
        self.input_mode_combo = QComboBox()
        self.input_mode_combo.addItems([MULTI_SIDE_VIEW_MODE_LABEL, SINGLE_SIDE_VIEW_MODE_LABEL])
        self.input_mode_combo.setCurrentText(
            SINGLE_SIDE_VIEW_MODE_LABEL
            if self._defaults.input_mode in {"Single side view", "Single-side ALMA"}
            else MULTI_SIDE_VIEW_MODE_LABEL
        )
        self.analysis_type_combo = QComboBox()
        self.analysis_type_combo.addItems(["Treadmill", "Spontaneous walking"])
        self.analysis_type_combo.setCurrentText(self._defaults.analysis_type)
        set_tooltip(self.input_mode_combo, "Switch between one side-view CSV and paired left/right/bottom CSV analysis.")
        set_tooltip(self.analysis_type_combo, "Choose treadmill or spontaneous-walking analysis.")
        setup_layout.addWidget(QLabel("Input mode"), 0, 0)
        setup_layout.addWidget(self.input_mode_combo, 0, 1)
        setup_layout.addWidget(QLabel("Analysis type"), 1, 0)
        setup_layout.addWidget(self.analysis_type_combo, 1, 1)
        setup_tab_layout.addWidget(setup_box)

        speed_box = QGroupBox("Treadmill speed and calibration")
        speed_layout = QGridLayout(speed_box)
        speed_layout.setHorizontalSpacing(12)
        speed_layout.setVerticalSpacing(4)
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
        setup_tab_layout.addWidget(speed_box)
        setup_tab_layout.addStretch(1)

        calibration_box = QGroupBox("Spatial calibration")
        calibration_layout = QVBoxLayout(calibration_box)
        self.calibration_method_combo = QComboBox()
        self.calibration_method_combo.addItems(["Reference body segment", "Manual pixel-to-cm ratio"])
        self.calibration_method_combo.setCurrentIndex(0 if self._defaults.calibration_method == "reference" else 1)
        set_tooltip(self.calibration_method_combo, "Choose anatomical-reference or manual spatial calibration.")
        calibration_layout.addWidget(self.calibration_method_combo)

        self.reference_settings_widget = QWidget()
        reference_layout = QGridLayout(self.reference_settings_widget)
        reference_layout.setContentsMargins(16, 4, 0, 0)
        reference_layout.setHorizontalSpacing(12)
        reference_layout.setVerticalSpacing(4)
        self.reference_segment_combo = QComboBox()
        self.reference_segment_combo.addItems(["ankle_toe (1.5cm)", "hip_knee (2.5cm)", "knee_ankle (2.0cm)", "ankle_mtp (0.8cm)"])
        self.reference_segment_combo.setCurrentText(_reference_segment_label(self._defaults.reference_segment))
        self.reference_length_spin = _double_spin(0.1, 10.0, self._defaults.reference_length_cm, 2)
        set_tooltip(self.reference_segment_combo, "Body segment used as the reference calibration length.")
        set_tooltip(self.reference_length_spin, "Known length of the selected reference segment in centimeters.")
        reference_layout.addWidget(QLabel("Reference segment"), 0, 0)
        reference_layout.addWidget(self.reference_segment_combo, 0, 1)
        reference_layout.addWidget(QLabel("Segment length (cm)"), 1, 0)
        reference_layout.addWidget(self.reference_length_spin, 1, 1)
        calibration_layout.addWidget(self.reference_settings_widget)

        self.manual_settings_widget = QWidget()
        manual_layout = QGridLayout(self.manual_settings_widget)
        manual_layout.setContentsMargins(16, 4, 0, 0)
        manual_layout.setHorizontalSpacing(12)
        manual_layout.setVerticalSpacing(4)
        self.pixels_per_cm_spin = _double_spin(1.0, 1000.0, self._defaults.pixels_per_cm or 50.0, 3)
        self.import_calibration_map_button = QPushButton("Import calibration map")
        set_tooltip(self.pixels_per_cm_spin, "Manual pixel-to-centimeter ratio.")
        set_tooltip(self.import_calibration_map_button, "Import a calibration conversion map.", "Ctrl+M")
        self.calibration_map_label = QLabel("No calibration map imported.")
        self.calibration_map_label.setObjectName("MutedLabel")
        self.calibration_map_label.setWordWrap(True)
        manual_layout.addWidget(QLabel("Pixels per cm"), 0, 0)
        manual_layout.addWidget(self.pixels_per_cm_spin, 0, 1)
        manual_layout.addWidget(self.import_calibration_map_button, 1, 0, 1, 2)
        manual_layout.addWidget(self.calibration_map_label, 2, 0, 1, 2)
        calibration_layout.addWidget(self.manual_settings_widget)
        calibration_tab_layout.addWidget(calibration_box)
        calibration_tab_layout.addStretch(1)

        movement_box = QGroupBox("Movement analysis settings")
        movement_layout = QGridLayout(movement_box)
        movement_layout.setHorizontalSpacing(12)
        movement_layout.setVerticalSpacing(4)
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

        filter_box = QGroupBox("Stride filtering (optional)")
        filter_layout = QGridLayout(filter_box)
        filter_layout.setHorizontalSpacing(12)
        filter_layout.setVerticalSpacing(4)
        self.step_height_min_spin = _double_spin(0.0, 5.0, self._defaults.step_height_min_cm, 2)
        self.step_height_max_spin = _double_spin(0.0, 5.0, self._defaults.step_height_max_cm, 2)
        self.stride_length_min_spin = _double_spin(0.0, 20.0, self._defaults.stride_length_min_cm, 2)
        self.stride_length_max_spin = _double_spin(0.0, 20.0, self._defaults.stride_length_max_cm, 2)
        self.likelihood_threshold_spin = _double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2)
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
        filters_tab_layout.addStretch(1)
        analysis_tab_layout.addStretch(1)

        output_options_box = QGroupBox("Output options")
        output_options_layout = QGridLayout(output_options_box)
        output_options_layout.setHorizontalSpacing(12)
        output_options_layout.setVerticalSpacing(4)
        self.continuous_strides_spin = QSpinBox()
        self.continuous_strides_spin.setRange(1, 50)
        self.continuous_strides_spin.setValue(self._defaults.n_continuous_strides)
        self.stickplot_checkbox = QCheckBox("Generate stickplot SVG")
        self.stickplot_checkbox.setChecked(True)
        self.rustlab1_checkbox = QCheckBox("Generate RustLab1 30-parameter + merged CSVs")
        self.rustlab1_checkbox.setChecked(self._defaults.generate_rustlab1_parameters)
        set_tooltip(self.continuous_strides_spin, "Number of continuous strides used for ALMA outputs.")
        set_tooltip(self.stickplot_checkbox, "Generate an SVG stickplot output.")
        set_tooltip(self.rustlab1_checkbox, "Calculate the SOP's 30 RustLab1 parameters on ALMA gait cycles when multi-view labels are present.")
        output_options_layout.addWidget(QLabel("Continuous strides"), 0, 0)
        output_options_layout.addWidget(self.continuous_strides_spin, 0, 1)
        output_options_layout.addWidget(self.stickplot_checkbox, 1, 0, 1, 2)
        output_tab_layout.addWidget(output_options_box)

        rustlab_box = QGroupBox("RustLab1 multi-view")
        rustlab_layout = QVBoxLayout(rustlab_box)
        rustlab_layout.setSpacing(6)
        rustlab_layout.addWidget(self.rustlab1_checkbox)
        self.rustlab_status_label = QLabel("RustLab1 needs paired left, right, and bottom CSVs.")
        self.rustlab_status_label.setObjectName("MutedLabel")
        self.rustlab_status_label.setWordWrap(True)
        rustlab_layout.addWidget(self.rustlab_status_label)
        output_tab_layout.addWidget(rustlab_box)
        output_tab_layout.addStretch(1)

        left_layout.addWidget(settings_tabs, 1)

        self.export_manifest_button = QPushButton("Export analysis manifest")
        set_tooltip(
            self.export_manifest_button,
            "Export the current gait-analysis settings for an automated pipeline profile.",
            "Ctrl+Shift+E",
        )
        left_layout.addWidget(self.export_manifest_button)

        self.preview_button = QPushButton("1. Generate stick-plot preview")
        set_tooltip(
            self.preview_button,
            "Generate and inspect an ALMA stick plot from the selected left-view CSV before running the full analysis.",
            "Ctrl+P",
        )
        left_layout.addWidget(self.preview_button)

        self.run_button = QPushButton("2. Run gait analysis")
        self.run_button.setObjectName("PrimaryButton")
        set_tooltip(self.run_button, "Run ALMA gait analysis after reviewing the stick plot.", "Ctrl+R")
        left_layout.addWidget(self.run_button)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        self.status_label = QLabel("Select matched left/right/bottom CSV files to begin.")
        self.status_label.setObjectName("PreviewTitle")
        right_layout.addWidget(self.status_label)
        self.progress = DynamicProgressBar(accent_role="tool_1")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)
        right_layout.addWidget(file_box, 2)

        self.preview_stack = QStackedWidget()
        self.preview_stack.setObjectName("StickPlotPreview")
        self.preview_stack.setMinimumHeight(150)
        self.preview_stack.setMaximumHeight(220)
        self.preview_placeholder = QLabel("Select left/right/bottom CSVs, then generate a stick-plot preview.")
        self.preview_placeholder.setAlignment(Qt.AlignCenter)
        self.preview_placeholder.setWordWrap(True)
        self.preview_placeholder.setObjectName("MutedLabel")
        self.stickplot_view = StickPlotPairPreviewWidget()
        self.stickplot_view.setObjectName("StickPlotPairPreview")
        self.stickplot_view.setMinimumSize(320, 150)
        self.stickplot_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        set_tooltip(self.stickplot_view, "Open a larger stick-plot preview.")
        self.preview_stack.addWidget(self.preview_placeholder)
        self.preview_stack.addWidget(self.stickplot_view)
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        right_layout.addWidget(self.preview_stack, 1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setMaximumHeight(220)
        right_layout.addWidget(self.log)

        mapping_box = QGroupBox("Body part mapping")
        mapping_box.setMinimumHeight(220)
        mapping_layout = QVBoxLayout(mapping_box)
        mapping_layout.setSpacing(10)
        mapping_header = QHBoxLayout()
        self.use_custom_mapping_checkbox = QCheckBox("Use custom mapping")
        self.reload_mapping_button = QPushButton("Load from CSV")
        self.auto_mapping_button = QPushButton("Auto detect")
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
        self.mapping_status_label.setWordWrap(True)
        mapping_layout.addWidget(self.mapping_status_label)

        mapping_grid = QGridLayout()
        mapping_grid.setHorizontalSpacing(12)
        mapping_grid.setVerticalSpacing(8)
        for index, standard_bodypart in enumerate(STANDARD_BODYPARTS):
            row = index // 2
            column = (index % 2) * 2
            label = QLabel(standard_bodypart)
            combo = QComboBox()
            combo.setMinimumWidth(150)
            combo.setEnabled(False)
            set_tooltip(combo, f"Raw DLC label to use as {standard_bodypart}.")
            self._bodypart_combos[standard_bodypart] = combo
            mapping_grid.addWidget(label, row, column)
            mapping_grid.addWidget(combo, row, column + 1)
        mapping_layout.addLayout(mapping_grid)
        mapping_tab_layout.addWidget(mapping_box)
        mapping_tab_layout.addStretch(1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 760])

    def _install_interactions(self) -> None:
        self._shortcuts = [
            add_shortcut(self, "Ctrl+O", self._add_file),
            add_shortcut(self, "Ctrl+Shift+O", self._add_folder),
            add_shortcut(self, "Ctrl+L", self._clear_files),
            add_shortcut(self, "Ctrl+Shift+S", self._select_output_folder),
            add_shortcut(self, "Ctrl+F", self._load_frame_rate_from_video),
            add_shortcut(self, "Ctrl+M", self._import_calibration_map),
            add_shortcut(self, "Ctrl+Shift+E", self._export_analysis_manifest),
            add_shortcut(self, "Ctrl+P", self._generate_stickplot_preview),
            add_shortcut(self, "Ctrl+R", self._run_analysis),
        ]
        self._wheel_value_guard = install_wheel_value_guard(self)

    def _connect_signals(self) -> None:
        self.add_file_button.clicked.connect(self._add_file)
        self.add_folder_button.clicked.connect(self._add_folder)
        self.clear_files_button.clicked.connect(self._clear_files)
        self.edit_pairing_button.clicked.connect(self._open_csv_pairing_dialog)
        self.label_matching_button.clicked.connect(self._open_label_matching_dialog)
        self.output_folder_button.clicked.connect(self._select_output_folder)
        self.output_folder_edit.textChanged.connect(self._update_run_state)
        self.preview_button.clicked.connect(self._generate_stickplot_preview)
        self.run_button.clicked.connect(self._run_analysis)
        self.analysis_type_combo.currentTextChanged.connect(self._update_analysis_mode)
        self.calibration_method_combo.currentTextChanged.connect(self._update_calibration_method)
        self.load_fps_button.clicked.connect(self._load_frame_rate_from_video)
        self.import_calibration_map_button.clicked.connect(self._import_calibration_map)
        self.export_manifest_button.clicked.connect(self._export_analysis_manifest)
        self.stickplot_view.double_clicked.connect(self._open_large_stickplot_preview)
        self.use_custom_mapping_checkbox.toggled.connect(self._update_mapping_enabled)
        self.reload_mapping_button.clicked.connect(self._load_bodypart_mapping_from_first_file)
        self.auto_mapping_button.clicked.connect(self._apply_auto_bodypart_mapping)
        self.file_list.model().rowsInserted.connect(self._update_run_state)
        self.file_list.model().rowsRemoved.connect(self._update_run_state)
        self.file_list.currentRowChanged.connect(self._preview_file_changed)
        self.view_set_table.currentItemChanged.connect(self._preview_view_set_changed)
        self.input_mode_combo.currentTextChanged.connect(self._update_input_mode)

        preview_controls = (
            self.input_mode_combo,
            self.analysis_type_combo,
            self.calibration_method_combo,
            self.reference_segment_combo,
            self.direction_combo,
        )
        for combo in preview_controls:
            combo.currentTextChanged.connect(self._invalidate_stickplot_preview)

        preview_spins = (
            self.treadmill_speed_spin,
            self.frame_rate_spin,
            self.reference_length_spin,
            self.pixels_per_cm_spin,
            self.filter_cutoff_spin,
            self.drag_clearance_spin,
            self.drag_frames_spin,
            self.step_height_min_spin,
            self.step_height_max_spin,
            self.stride_length_min_spin,
            self.stride_length_max_spin,
            self.likelihood_threshold_spin,
        )
        for spin in preview_spins:
            spin.valueChanged.connect(self._invalidate_stickplot_preview)

        for checkbox in (
            self.no_outlier_checkbox,
            self.dragging_filter_checkbox,
            self.use_custom_mapping_checkbox,
        ):
            checkbox.toggled.connect(self._invalidate_stickplot_preview)
        for combo in self._bodypart_combos.values():
            combo.currentTextChanged.connect(self._invalidate_stickplot_preview)

    def _add_file(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Select left/right/bottom coordinate CSVs",
            str(self._project_root),
            "CSV files (*.csv);;All files (*)",
        )
        if filenames:
            self._add_csv_paths([Path(filename) for filename in filenames])

    def _add_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select folder containing CSV files", str(self._project_root))
        if directory:
            self._add_csv_paths(sorted(Path(directory).glob("*.csv")))

    def _add_csv_paths(self, paths: list[Path]) -> None:
        previous_count = len(self._selected_files)
        existing = {str(path) for path in self._selected_files}
        for path in paths:
            resolved = path.expanduser().resolve()
            if resolved.suffix.lower() != ".csv" or str(resolved) in existing:
                continue
            self._selected_files.append(resolved)
            self.file_list.addItem(str(resolved))
            existing.add(str(resolved))
        if self._selected_files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)
        self._refresh_view_sets()
        if self._selected_files and not self._raw_bodyparts:
            self._load_bodypart_mapping_from_first_file()
        if len(self._selected_files) != previous_count:
            self._invalidate_stickplot_preview()
        self._update_run_state()

    def _clear_files(self) -> None:
        self._selected_files.clear()
        self.file_list.clear()
        self._view_sets = []
        self._view_set_errors = []
        self._manual_view_sets = None
        self._raw_bodyparts = []
        self._refresh_bodypart_mapping_choices()
        self.view_set_table.clear()
        self.view_set_status_label.setText("Add matched left, right, and bottom CSVs.")
        self.rustlab_status_label.setText("RustLab1 needs paired left, right, and bottom CSVs.")
        self.mapping_status_label.setText("Add a complete CSV view set to detect labels.")
        self._invalidate_stickplot_preview("Select left/right/bottom CSVs, then generate a stick-plot preview.")
        self._update_run_state()

    def _refresh_view_sets(self) -> None:
        if self._manual_view_sets is not None:
            selected = {path for path in self._selected_files}
            self._manual_view_sets = [
                view_set
                for view_set in self._manual_view_sets
                if view_set.left_csv in selected and view_set.right_csv in selected and view_set.bottom_csv in selected
            ]
            self._view_sets = list(self._manual_view_sets)
            self._view_set_errors = []
        else:
            self._view_sets, self._view_set_errors = _build_alma_view_csv_sets(self._selected_files)
        self._refresh_view_set_table()
        if self._manual_view_sets is not None and self._view_sets:
            suffix = "" if len(self._view_sets) == 1 else "s"
            self.view_set_status_label.setText(f"Manual pairing: {len(self._view_sets)} complete CSV set{suffix}.")
            self.rustlab_status_label.setText(f"RustLab1 ready for {len(self._view_sets)} manually paired CSV set{suffix}.")
        elif self._manual_view_sets is not None:
            self.view_set_status_label.setText("Manual pairing has no complete left/right/bottom CSV sets.")
            self.rustlab_status_label.setText("RustLab1 waiting for complete manual CSV pairs.")
        elif self._view_sets and not self._view_set_errors:
            suffix = "" if len(self._view_sets) == 1 else "s"
            self.view_set_status_label.setText(
                f"Ready: {len(self._view_sets)} complete left/right/bottom CSV set{suffix}."
            )
            self.rustlab_status_label.setText(
                f"RustLab1 ready for {len(self._view_sets)} paired CSV set{suffix}."
            )
        elif self._view_sets:
            self.view_set_status_label.setText(
                f"{len(self._view_sets)} complete set(s); " + " ".join(self._view_set_errors)
            )
            self.rustlab_status_label.setText("RustLab1 ready for complete paired sets; unresolved rows will be ignored.")
        elif self._selected_files:
            self.view_set_status_label.setText(self._multiview_requirement_message())
            self.rustlab_status_label.setText("RustLab1 waiting for complete left/right/bottom pairs.")
        else:
            self.view_set_status_label.setText("Add matched left, right, and bottom CSVs.")
            self.rustlab_status_label.setText("RustLab1 needs paired left, right, and bottom CSVs.")

    def _refresh_view_set_table(self) -> None:
        if self._manual_view_sets is not None:
            rows = [
                {
                    "name": view_set.name,
                    "left": view_set.left_csv,
                    "right": view_set.right_csv,
                    "bottom": view_set.bottom_csv,
                    "status": "Manual",
                }
                for view_set in self._view_sets
            ]
        else:
            rows = _build_alma_view_pair_rows(self._selected_files)
        self.view_set_table.blockSignals(True)
        self.view_set_table.clear()
        complete_index = 0
        first_ready_item = None
        for row in rows:
            item = QTreeWidgetItem(
                [
                    row["name"],
                    _path_name(row.get("left")),
                    _path_name(row.get("right")),
                    _path_name(row.get("bottom")),
                    row["status"],
                ]
            )
            if row["status"] in {"Ready", "Manual"}:
                item.setData(0, Qt.UserRole, complete_index)
                complete_index += 1
                if first_ready_item is None:
                    first_ready_item = item
            else:
                item.setData(0, Qt.UserRole, -1)
            self.view_set_table.addTopLevelItem(item)
        if first_ready_item is not None:
            self.view_set_table.setCurrentItem(first_ready_item)
        self.view_set_table.blockSignals(False)

    def _multiview_requirement_message(self) -> str:
        details = " ".join(self._view_set_errors)
        base = "Gait analysis now requires matched left, right, and bottom/down CSV files."
        if details:
            return f"{base} {details}"
        return base

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
        self.calibration_method_combo.setCurrentText("Manual pixel-to-cm ratio")
        self.pixels_per_cm_spin.setValue(pixels_per_cm)
        self.calibration_map_label.setText(f"{path.name} | {source}: {pixels_per_cm:.3f} px/cm")
        self.status_label.setText("Calibration map imported.")
        self._append_log(f"Calibration map imported from {path}: {pixels_per_cm:.3f} px/cm ({source})")
        self._update_calibration_method()

    def _export_analysis_manifest(self) -> None:
        output_text = self.output_folder_edit.text().strip()
        output_folder = Path(output_text).expanduser() if output_text else self._default_output_root()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export gait analysis manifest",
            str(output_folder / "analysis_manifest.json"),
            "Analysis manifest (analysis_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if not filename:
            return

        destination = Path(filename)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")
        try:
            exported = write_analysis_manifest(destination, self._collect_settings())
        except OSError as exc:
            QMessageBox.critical(self, "Could not export analysis manifest", str(exc))
            return

        self.status_label.setText("Analysis manifest exported.")
        self._append_log(f"Analysis manifest exported to {exported}")
        QMessageBox.information(
            self,
            "Analysis manifest exported",
            f"Saved the current gait-analysis settings to:\n{exported}",
        )

    def _load_bodypart_mapping_from_first_file(self) -> None:
        if not self._selected_files:
            QMessageBox.information(self, "No input files", "Add left/right/bottom CSV files before loading body part labels.")
            return

        csv_path = self._selected_preview_file()
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

    def _open_label_matching_dialog(self) -> None:
        if not self._is_three_view_mode():
            self.settings_tabs.setCurrentWidget(self.mapping_tab)
            return

        view_set = self._selected_view_set()
        if view_set is None:
            QMessageBox.information(self, "CSV set required", self._input_requirement_message())
            return

        try:
            labels_by_view = {
                "left": _read_dlc_bodyparts(view_set.left_csv),
                "right": _read_dlc_bodyparts(view_set.right_csv),
                "bottom": _read_dlc_bodyparts(view_set.bottom_csv),
            }
        except Exception as exc:
            QMessageBox.critical(self, "Could not read labels", str(exc))
            return

        dialog = LabelMappingDialog(
            view_set,
            labels_by_view,
            self._view_label_mappings.get(view_set.name, {}),
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        mapping = dialog.mapping()
        if mapping:
            self._view_label_mappings[view_set.name] = mapping
        else:
            self._view_label_mappings.pop(view_set.name, None)
        selected_count = sum(len(view_mapping) for view_mapping in mapping.values())
        self.mapping_status_label.setText(f"{selected_count}/16 labels assigned for {view_set.name}.")
        self.rustlab_status_label.setText(f"RustLab1 label mapping updated for {view_set.name}.")
        self._invalidate_stickplot_preview(f"Generate a stick-plot preview for {view_set.name}.")

    def _open_csv_pairing_dialog(self) -> None:
        if not self._selected_files:
            QMessageBox.information(self, "CSV files required", "Add CSV files before editing CSV pairing.")
            return

        dialog = CsvPairingDialog(
            self._selected_files,
            self._manual_view_sets if self._manual_view_sets is not None else self._view_sets,
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        self._manual_view_sets = dialog.pairings()
        self._refresh_view_sets()
        if self._view_sets:
            self._select_view_set_row(0)
            self._invalidate_stickplot_preview(f"Generate a stick-plot preview for {self._view_sets[0].name}.")
        else:
            self._invalidate_stickplot_preview(self._multiview_requirement_message())
        self._update_run_state()

    def _preview_file_changed(self, row: int) -> None:
        if row < 0 or not self._selected_files:
            return
        selected = self._selected_files[row]
        if not self._is_three_view_mode():
            self._invalidate_stickplot_preview(f"Generate a stick-plot preview for {selected.name}.")
            return
        for index, view_set in enumerate(self._view_sets):
            if selected in (view_set.left_csv, view_set.right_csv, view_set.bottom_csv):
                self._select_view_set_row(index)
                break
        if self._has_valid_view_sets():
            self._invalidate_stickplot_preview(
                f"Generate a stick-plot preview for {self._selected_preview_file().name}."
            )
        else:
            self._invalidate_stickplot_preview(self._multiview_requirement_message())

    def _preview_view_set_changed(self, current, _previous) -> None:
        if current is None:
            return
        if self._selected_view_set() is not None:
            self._invalidate_stickplot_preview(
                f"Generate a stick-plot preview for {self._selected_preview_file().name}."
            )
        else:
            self._invalidate_stickplot_preview(self._multiview_requirement_message())

    def _select_view_set_row(self, view_set_index: int) -> None:
        for row in range(self.view_set_table.topLevelItemCount()):
            item = self.view_set_table.topLevelItem(row)
            if item.data(0, Qt.UserRole) == view_set_index:
                self.view_set_table.setCurrentItem(item)
                return

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

    def _update_input_mode(self) -> None:
        three_view = self._is_three_view_mode()
        self.view_set_table.setVisible(three_view)
        self.view_set_status_label.setVisible(three_view)
        self.edit_pairing_button.setVisible(three_view)
        self.label_matching_button.setVisible(three_view)
        self.file_list.setVisible(not three_view)
        self.rustlab1_checkbox.setEnabled(three_view)
        if not three_view:
            self.rustlab_status_label.setText("Single side view mode: RustLab1 multi side view output is disabled.")
        else:
            self._refresh_view_sets()
        self._invalidate_stickplot_preview()
        self._update_run_state()

    def _update_analysis_mode(self) -> None:
        treadmill = self.analysis_type_combo.currentText() == "Treadmill"
        self.treadmill_speed_label.setVisible(treadmill)
        self.treadmill_speed_spin.setVisible(treadmill)
        self.spontaneous_box.setVisible(not treadmill)

    def _update_calibration_method(self) -> None:
        reference = self.calibration_method_combo.currentText() == "Reference body segment"
        self.reference_settings_widget.setVisible(reference)
        self.manual_settings_widget.setVisible(not reference)

    def _update_run_state(self) -> None:
        has_files = self._has_valid_inputs()
        has_output = bool(self.output_folder_edit.text().strip())
        analysis_running = self._worker is not None and self._worker.isRunning()
        preview_running = self._preview_worker is not None and self._preview_worker.isRunning()
        running = analysis_running or preview_running
        self.preview_button.setEnabled(has_files and not running)
        self.run_button.setEnabled(
            has_files and has_output and self._stickplot_preview_ready and not running
        )

    def _invalidate_stickplot_preview(self, message=None, *_args) -> None:
        if isinstance(message, str) and message:
            placeholder_text = message
        elif self._is_three_view_mode() and self._selected_files and not self._has_valid_view_sets():
            placeholder_text = self._multiview_requirement_message()
        elif self._selected_files:
            placeholder_text = f"Settings changed. Regenerate the stick-plot preview for {self._selected_preview_file().name}."
        else:
            placeholder_text = (
                "Select left/right/bottom CSVs, then generate a stick-plot preview."
                if self._is_three_view_mode()
                else "Select one side-view CSV, then generate a stick-plot preview."
            )
        self._stickplot_preview_ready = False
        self._preview_svg_data = None
        self._preview_source_name = ""
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_invalidated_while_running = True
        elif self._has_valid_inputs():
            self.status_label.setText("Generate a stick-plot preview before gait analysis.")
        else:
            self.status_label.setText(
                "Select matched left/right/bottom CSV files to begin."
                if self._is_three_view_mode()
                else "Select a side-view CSV file to begin."
            )
        self.preview_placeholder.setText(placeholder_text)
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        self._update_run_state()

    def _generate_stickplot_preview(self) -> None:
        if not self._has_valid_inputs():
            QMessageBox.information(
                self,
                "Input CSVs required",
                self._input_requirement_message(),
            )
            return
        settings = self._collect_settings()
        if self._is_three_view_mode():
            view_set = self._selected_view_set()
            settings = replace(
                settings,
                view_bodypart_mapping=self._view_label_mappings.get(view_set.name) if view_set is not None else None,
            )
        if self.use_custom_mapping_checkbox.isChecked() and not settings.custom_bodypart_mapping:
            QMessageBox.warning(
                self,
                "No body part mapping",
                "Select at least one body part mapping or turn off custom mapping.",
            )
            return
        missing_bodyparts = self._missing_required_bodyparts(settings)
        if missing_bodyparts:
            if self._is_three_view_mode():
                self._open_label_matching_dialog()
            else:
                self.settings_tabs.setCurrentWidget(self.mapping_tab)
            self.mapping_status_label.setText(
                "Missing required ALMA body parts: " + ", ".join(missing_bodyparts)
            )
            QMessageBox.warning(
                self,
                "Body part mapping incomplete",
                "ALMA needs toe, mtp, ankle, knee, hip, and iliac crest coordinates for each side view. "
                "Open Label matching and assign the left, right, and bottom labels for the selected CSV set.",
            )
            return

        self._stickplot_preview_ready = False
        self._preview_invalidated_while_running = False
        self.progress.setValue(0)
        self.progress.set_active(True)
        self.log.clear()
        preview_inputs = self._preview_inputs()
        preview_names = ", ".join(path.name for _label, path in preview_inputs)
        self.status_label.setText(f"Generating stick-plot preview for {preview_names}...")
        self.preview_placeholder.setText(f"Generating ALMA stick plot for {preview_names}...")
        self.preview_stack.setCurrentWidget(self.preview_placeholder)

        preview_settings = replace(
            settings,
            generate_stickplot=True,
            generate_rustlab1_parameters=False,
        )
        self._preview_worker = StickPlotPreviewThread(
            preview_inputs,
            preview_settings,
            self._alma_root,
        )
        self._preview_worker.progress_updated.connect(self._update_progress)
        self._preview_worker.log_message.connect(self._append_log)
        self._preview_worker.preview_ready.connect(self._stickplot_preview_completed)
        self._preview_worker.preview_failed.connect(self._stickplot_preview_failed)
        self._preview_worker.finished.connect(self._preview_worker_finished)
        self._preview_worker.start()
        self._update_run_state()

    def _stickplot_preview_completed(self, plots, source_name: str) -> None:
        if self._preview_invalidated_while_running:
            self._stickplot_preview_ready = False
            self.preview_placeholder.setText(
                "Settings changed while the preview was running. Generate it again."
            )
            self.preview_stack.setCurrentWidget(self.preview_placeholder)
            self.status_label.setText("Stick-plot preview is out of date.")
            self._append_log("Preview discarded because its settings changed during generation.")
            return
        plot_tuple = tuple(plots)
        if not plot_tuple:
            self._stickplot_preview_failed("Stick-plot preview did not return any SVG plots.")
            return
        self.stickplot_view.load_plots(plot_tuple)
        self.preview_stack.setCurrentWidget(self.stickplot_view)
        self._stickplot_preview_ready = True
        self._preview_svg_data = plot_tuple
        self._preview_source_name = source_name
        self.progress.setValue(100)
        self.status_label.setText("Stick-plot preview ready. Review it, then run gait analysis.")
        self._append_log(f"Stick-plot preview generated from {source_name}.")

    def _open_large_stickplot_preview(self) -> None:
        if not self._preview_svg_data:
            return
        if self._large_stickplot_dialog is not None:
            self._large_stickplot_dialog.raise_()
            self._large_stickplot_dialog.activateWindow()
            return

        dialog = StickPlotPreviewDialog(self._preview_svg_data, self._preview_source_name, self)
        self._large_stickplot_dialog = dialog
        dialog.finished.connect(lambda _result: self._large_stickplot_dialog_closed(dialog))
        dialog.show()

    def _large_stickplot_dialog_closed(self, dialog: "StickPlotPreviewDialog") -> None:
        if self._large_stickplot_dialog is dialog:
            self._large_stickplot_dialog = None

    def _stickplot_preview_failed(self, message: str) -> None:
        self._stickplot_preview_ready = False
        self._preview_svg_data = None
        self._preview_source_name = ""
        self.preview_placeholder.setText("Stick-plot preview could not be generated.")
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        self.status_label.setText("Stick-plot preview failed.")
        self.progress.set_active(False)
        self._append_log(message)
        QMessageBox.critical(self, "Stick-plot preview failed", message)

    def _preview_worker_finished(self) -> None:
        self._preview_worker = None
        self.progress.set_active(False)
        self._update_run_state()

    def _run_analysis(self) -> None:
        output_folder = Path(self.output_folder_edit.text()).expanduser().resolve()
        if not self._has_valid_inputs():
            QMessageBox.information(
                self,
                "Input CSVs required",
                self._input_requirement_message(),
            )
            return
        if not self._stickplot_preview_ready:
            QMessageBox.information(
                self,
                "Stick-plot preview required",
                "Generate and review the stick-plot preview before running gait analysis.",
            )
            return

        settings = self._collect_settings()
        if self.use_custom_mapping_checkbox.isChecked() and not settings.custom_bodypart_mapping:
            QMessageBox.warning(self, "No body part mapping", "Select at least one body part mapping or turn off custom mapping.")
            return
        self.progress.setValue(0)
        self.progress.set_active(True)
        self.log.clear()
        self.status_label.setText("Running ALMA gait analysis...")
        self.run_button.setEnabled(False)

        analysis_inputs = self._view_sets if self._is_three_view_mode() else self._selected_files
        self._worker = AlmaAnalysisThread(analysis_inputs, output_folder, settings, self._alma_root)
        self._worker.progress_updated.connect(self._update_progress)
        self._worker.log_message.connect(self._append_log)
        self._worker.analysis_completed.connect(self._analysis_completed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()
        self._update_run_state()

    def _collect_settings(self) -> AlmaSettings:
        if self.direction_combo.currentText() == "Auto-detect":
            right_to_left: bool | str = "auto"
        elif self.direction_combo.currentText() == "Right-to-Left":
            right_to_left = True
        else:
            right_to_left = False

        return AlmaSettings(
            input_mode=MULTI_SIDE_VIEW_MODE_LABEL if self._is_three_view_mode() else SINGLE_SIDE_VIEW_MODE_LABEL,
            analysis_type=self.analysis_type_combo.currentText(),
            frame_rate=self.frame_rate_spin.value(),
            filter_cutoff=self.filter_cutoff_spin.value(),
            treadmill_speed_cm_s=self.treadmill_speed_spin.value(),
            calibration_method="reference" if self.calibration_method_combo.currentText() == "Reference body segment" else "manual",
            reference_segment=self.reference_segment_combo.currentText().split(" ", 1)[0],
            reference_length_cm=self.reference_length_spin.value(),
            calibration_map_path=self._calibration_map_path,
            right_to_left=right_to_left,
            pixels_per_cm=self.pixels_per_cm_spin.value()
            if self.calibration_method_combo.currentText() == "Manual pixel-to-cm ratio"
            else None,
            no_outlier_filter=self.no_outlier_checkbox.isChecked(),
            dragging_filter=self.dragging_filter_checkbox.isChecked(),
            likelihood_threshold=self.likelihood_threshold_spin.value(),
            drag_clearance_cm=self.drag_clearance_spin.value(),
            drag_min_consecutive_frames=self.drag_frames_spin.value(),
            step_height_min_cm=self.step_height_min_spin.value(),
            step_height_max_cm=self.step_height_max_spin.value(),
            stride_length_min_cm=self.stride_length_min_spin.value(),
            stride_length_max_cm=self.stride_length_max_spin.value(),
            n_continuous_strides=self.continuous_strides_spin.value(),
            generate_stickplot=self.stickplot_checkbox.isChecked(),
            generate_rustlab1_parameters=self.rustlab1_checkbox.isChecked() and self._is_three_view_mode(),
            custom_bodypart_mapping=self._collect_bodypart_mapping(),
            view_bodypart_mapping=self._collect_view_bodypart_mapping(),
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

    def _collect_view_bodypart_mapping(self) -> dict[str, object] | None:
        if not self._is_three_view_mode():
            return None
        return self._view_label_mappings or None

    def _preview_inputs(self) -> tuple[tuple[str, Path], ...]:
        if self._is_three_view_mode():
            view_set = self._selected_view_set()
            if view_set is not None:
                return (("Left", view_set.left_csv), ("Right", view_set.right_csv))
            return ()
        return (("Single", self._selected_preview_file()),)

    def _selected_preview_file(self) -> Path:
        view_set = self._selected_view_set()
        if self._is_three_view_mode() and view_set is not None:
            return view_set.alma_csv
        row = self.file_list.currentRow()
        if 0 <= row < len(self._selected_files):
            return self._selected_files[row]
        return self._selected_files[0]

    def _has_valid_inputs(self) -> bool:
        if self._is_three_view_mode():
            return self._selected_view_set() is not None
        return bool(self._selected_files)

    def _has_valid_view_sets(self) -> bool:
        return bool(self._view_sets)

    def _is_three_view_mode(self) -> bool:
        return self.input_mode_combo.currentText() == MULTI_SIDE_VIEW_MODE_LABEL

    def _input_requirement_message(self) -> str:
        if self._is_three_view_mode():
            return self._multiview_requirement_message()
        return "Single side view mode requires at least one side-view CSV."

    def _selected_view_set(self) -> AlmaViewCsvSet | None:
        item = self.view_set_table.currentItem()
        if item is not None:
            index = item.data(0, Qt.UserRole)
            if isinstance(index, int) and 0 <= index < len(self._view_sets):
                return self._view_sets[index]
            return None
        if self._view_sets:
            return self._view_sets[0]
        return None

    def _missing_required_bodyparts(self, settings: AlmaSettings) -> list[str]:
        if self._is_three_view_mode():
            view_set = self._selected_view_set()
            if view_set is None:
                return []
            missing: list[str] = []
            view_mapping = settings.view_bodypart_mapping or {}
            for view, csv_path, required_labels in (
                ("left", view_set.left_csv, SIDE_VIEW_LABELS),
                ("right", view_set.right_csv, SIDE_VIEW_LABELS),
                ("bottom", view_set.bottom_csv, BOTTOM_VIEW_LABELS[:3]),
            ):
                try:
                    raw_bodyparts = _read_dlc_bodyparts(csv_path)
                except Exception:
                    missing.extend(f"{view} {label}" for label in required_labels)
                    continue
                mapped_bodyparts = set((view_mapping.get(view) or {}).values())
                for standard_bodypart in required_labels:
                    if standard_bodypart in mapped_bodyparts:
                        continue
                    if _auto_bodypart_label(raw_bodyparts, standard_bodypart) is None:
                        missing.append(f"{view} {standard_bodypart}")
            return missing

        if not self._raw_bodyparts:
            return []

        mapped_bodyparts = set(settings.custom_bodypart_mapping.values()) if settings.custom_bodypart_mapping else set()
        missing: list[str] = []
        for standard_bodypart in STANDARD_BODYPARTS:
            if standard_bodypart in mapped_bodyparts:
                continue
            if _auto_bodypart_label(self._raw_bodyparts, standard_bodypart) is None:
                missing.append(standard_bodypart)
        return missing

    def _update_progress(self, value: int, text: str) -> None:
        self.progress.setValue(value)
        self.status_label.setText(text)

    def _append_log(self, text: str) -> None:
        self.log.append(text)

    def _analysis_completed(self, success: bool, message: str) -> None:
        self.status_label.setText(message)
        self.progress.set_active(False)
        self.progress.setValue(100 if success else self.progress.value())
        if success:
            QMessageBox.information(self, "ALMA gait analysis complete", message)
        else:
            QMessageBox.critical(self, "ALMA gait analysis failed", message)

    def _worker_finished(self) -> None:
        self._worker = None
        self.progress.set_active(False)
        self._update_run_state()

    def _default_output_root(self) -> Path:
        return manual_pipeline_output_folders(self._project_root).gait_analysis

    def _apply_style(self) -> None:
        runway_tab_style = """
            QTabWidget#RunwaySettingsTabs {
                background: {theme.PANEL};
            }
            QTabWidget#RunwaySettingsTabs::pane {
                background: {theme.BACKGROUND};
                border: 0;
                border-top: 1px solid {theme.BORDER};
            }
            QTabWidget#RunwaySettingsTabs QTabBar::tab {
                background: {theme.PANEL};
            }
            QTabWidget#RunwaySettingsTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
            }
        """
        self.setStyleSheet(
            theme.workspace_stylesheet(
                "GaitAnalysisWidget",
                runway_tab_style
                + """
            QStackedWidget#StickPlotPreview {
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
                background: white;
            }
            QSvgWidget#StickPlotSvg,
            DoubleClickSvgWidget#StickPlotSvg {
                background: white;
            }
            """
            )
        )


class GaitAnalysisWidget(QWidget):
    """Primary gait-analysis workspace, opening directly to Runway."""

    def __init__(self):
        super().__init__()
        self.setObjectName("GaitAnalysisContainer")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.kinematics_widget = AlmaKinematicsWidget()
        root.addWidget(self.kinematics_widget)

    def can_close(self, parent=None) -> bool:
        return self.kinematics_widget.can_close(parent or self)

    def release_resources(self) -> None:
        pass

    def _apply_style(self) -> None:
        self.kinematics_widget._apply_style()


class StickPlotPreviewDialog(QDialog):
    def __init__(self, plots: tuple[tuple[str, bytes], ...], source_name: str, parent=None):
        super().__init__(parent)
        title = "Stick-plot preview"
        if source_name:
            title = f"{title}: {source_name}"
        self.setWindowTitle(title)
        self.resize(1180, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setObjectName("LargeStickPlotScroll")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(14)
        self.previews: list[QSvgWidget] = []
        for plot_label, svg_data in plots:
            label = QLabel(plot_label)
            label.setObjectName("PreviewTitle")
            content_layout.addWidget(label)
            preview = QSvgWidget()
            preview.setObjectName("LargeStickPlotSvg")
            preview.load(QByteArray(_qt_safe_svg_bytes(svg_data)))
            width, height = _expanded_svg_size(preview)
            preview.setFixedSize(width, height)
            content_layout.addWidget(preview)
            self.previews.append(preview)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        self.setStyleSheet(
            theme.workspace_stylesheet(
                "StickPlotPreviewDialog",
                """
                QScrollArea#LargeStickPlotScroll {
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    background: white;
                }
                QSvgWidget#LargeStickPlotSvg {
                    background: white;
                }
                """
            )
        )


class CsvPairingDialog(QDialog):
    def __init__(self, csv_files: list[Path], initial_sets: list[AlmaViewCsvSet], parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV pairing")
        self.resize(980, 520)
        self._csv_files = list(csv_files)
        self._rows: list[dict[str, object]] = []
        self._pairings: list[AlmaViewCsvSet] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._row_container = QWidget()
        self._row_layout = QVBoxLayout(self._row_container)
        self._row_layout.setContentsMargins(0, 0, 0, 0)
        self._row_layout.setSpacing(8)
        scroll.setWidget(self._row_container)
        layout.addWidget(scroll, 1)

        source_sets = list(initial_sets)
        if not source_sets and len(self._csv_files) >= 3:
            source_sets = [_suggest_view_set_from_files(self._csv_files)]
        for view_set in source_sets:
            self._add_row(view_set)
        if not self._rows:
            self._add_row()

        action_row = QHBoxLayout()
        self.add_set_button = QPushButton("Add CSV set")
        self.auto_pair_button = QPushButton("Use filename pairs")
        set_tooltip(self.add_set_button, "Add another left/right/bottom CSV set.")
        set_tooltip(self.auto_pair_button, "Replace manual rows with pairs inferred from CSV filenames.")
        self.add_set_button.clicked.connect(lambda: self._add_row())
        self.auto_pair_button.clicked.connect(self._use_filename_pairs)
        action_row.addWidget(self.add_set_button)
        action_row.addWidget(self.auto_pair_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(theme.workspace_stylesheet("CsvPairingDialog", ""))

    def _add_row(self, view_set: AlmaViewCsvSet | None = None) -> None:
        frame = QFrame()
        frame.setObjectName("PairingRow")
        row_layout = QGridLayout(frame)
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setHorizontalSpacing(10)
        row_layout.setVerticalSpacing(6)

        name_edit = QLineEdit(view_set.name if view_set is not None else f"set_{len(self._rows) + 1}")
        left_combo = self._path_combo(view_set.left_csv if view_set is not None else None)
        right_combo = self._path_combo(view_set.right_csv if view_set is not None else None)
        bottom_combo = self._path_combo(view_set.bottom_csv if view_set is not None else None)
        remove_button = QPushButton("Remove")

        row_layout.addWidget(QLabel("CSV set name"), 0, 0)
        row_layout.addWidget(name_edit, 0, 1, 1, 3)
        row_layout.addWidget(remove_button, 0, 4)
        row_layout.addWidget(QLabel("Left side view CSV"), 1, 0)
        row_layout.addWidget(left_combo, 1, 1)
        row_layout.addWidget(QLabel("Right side view CSV"), 1, 2)
        row_layout.addWidget(right_combo, 1, 3)
        row_layout.addWidget(QLabel("Bottom view CSV"), 2, 0)
        row_layout.addWidget(bottom_combo, 2, 1, 1, 3)

        row = {
            "frame": frame,
            "name": name_edit,
            "left": left_combo,
            "right": right_combo,
            "bottom": bottom_combo,
        }
        remove_button.clicked.connect(lambda _checked=False, row=row: self._remove_row(row))
        self._rows.append(row)
        self._row_layout.addWidget(frame)

    def _remove_row(self, row: dict[str, object]) -> None:
        if row not in self._rows:
            return
        self._rows.remove(row)
        frame = row["frame"]
        if isinstance(frame, QWidget):
            frame.setParent(None)
            frame.deleteLater()
        if not self._rows:
            self._add_row()

    def _path_combo(self, selected: Path | None = None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("(none)", "")
        selected_text = str(Path(selected).expanduser().resolve()) if selected is not None else ""
        for path in self._csv_files:
            combo.addItem(_csv_choice_label(path, self._csv_files), str(path))
        if selected_text:
            index = combo.findData(selected_text)
            if index >= 0:
                combo.setCurrentIndex(index)
        return combo

    def _use_filename_pairs(self) -> None:
        view_sets, _errors = _build_alma_view_csv_sets(self._csv_files)
        for row in list(self._rows):
            self._remove_row(row)
        for view_set in view_sets:
            self._add_row(view_set)
        if not self._rows:
            self._add_row()

    def accept(self) -> None:
        try:
            self._pairings = self._collect_pairings()
        except ValueError as exc:
            QMessageBox.warning(self, "CSV pairing incomplete", str(exc))
            return
        super().accept()

    def _collect_pairings(self) -> list[AlmaViewCsvSet]:
        pairings: list[AlmaViewCsvSet] = []
        used_paths: dict[Path, str] = {}
        used_names: set[str] = set()
        for index, row in enumerate(self._rows, start=1):
            name_edit = row["name"]
            left_combo = row["left"]
            right_combo = row["right"]
            bottom_combo = row["bottom"]
            if not isinstance(name_edit, QLineEdit) or not isinstance(left_combo, QComboBox):
                continue
            if not isinstance(right_combo, QComboBox) or not isinstance(bottom_combo, QComboBox):
                continue

            name = name_edit.text().strip() or f"set_{index}"
            selected = {
                "left": _combo_path(left_combo),
                "right": _combo_path(right_combo),
                "bottom": _combo_path(bottom_combo),
            }
            if not any(selected.values()):
                continue
            missing = [view for view, path in selected.items() if path is None]
            if missing:
                raise ValueError(f"{name}: missing " + ", ".join(missing) + " CSV.")
            row_paths = [path for path in selected.values() if path is not None]
            if len(set(row_paths)) != len(row_paths):
                raise ValueError(f"{name}: each view must use a different CSV file.")
            if name in used_names:
                raise ValueError(f"{name}: CSV set names must be unique.")
            used_names.add(name)
            for view, path in selected.items():
                if path is None:
                    continue
                previous = used_paths.get(path)
                if previous is not None:
                    raise ValueError(f"{path.name} is already assigned to {previous}.")
                used_paths[path] = f"{name} {view}"
            pairings.append(
                AlmaViewCsvSet(
                    name=name,
                    left_csv=selected["left"],
                    right_csv=selected["right"],
                    bottom_csv=selected["bottom"],
                )
            )
        if not pairings:
            raise ValueError("Create at least one complete left/right/bottom CSV set.")
        return pairings

    def pairings(self) -> list[AlmaViewCsvSet]:
        return list(self._pairings)


class LabelMappingDialog(QDialog):
    def __init__(
        self,
        view_set: AlmaViewCsvSet,
        labels_by_view: dict[str, list[str]],
        existing_mapping: dict[str, dict[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Label matching: {view_set.name}")
        self.resize(820, 560)
        self._combos: dict[tuple[str, str], QComboBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)

        for view, title, csv_path, required_labels in (
            ("left", "Left hindlimb", view_set.left_csv, SIDE_VIEW_LABELS),
            ("right", "Right hindlimb", view_set.right_csv, SIDE_VIEW_LABELS),
            ("bottom", "Bottom view", view_set.bottom_csv, BOTTOM_VIEW_LABELS),
        ):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(8, 8, 8, 8)
            page_layout.setSpacing(10)
            file_label = QLabel(csv_path.name)
            file_label.setObjectName("MutedLabel")
            page_layout.addWidget(file_label)

            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            raw_labels = labels_by_view.get(view, [])
            choices = ["(none)", *raw_labels]
            existing_for_view = existing_mapping.get(view, {})
            for row, standard_label in enumerate(required_labels):
                combo = QComboBox()
                combo.addItems(choices)
                selected = _raw_label_for_standard(existing_for_view, standard_label)
                if selected not in raw_labels:
                    selected = _auto_bodypart_label(raw_labels, standard_label)
                combo.setCurrentText(selected or "(none)")
                set_tooltip(combo, f"Raw DLC label to use as {standard_label}.")
                self._combos[(view, standard_label)] = combo
                grid.addWidget(QLabel(standard_label), row, 0)
                grid.addWidget(combo, row, 1)
            page_layout.addLayout(grid)
            page_layout.addStretch(1)
            tabs.addTab(page, title)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(theme.workspace_stylesheet("LabelMappingDialog", ""))

    def mapping(self) -> dict[str, dict[str, str]]:
        mapping: dict[str, dict[str, str]] = {"left": {}, "right": {}, "bottom": {}}
        for (view, standard_label), combo in self._combos.items():
            raw_label = combo.currentText()
            if raw_label and raw_label != "(none)":
                mapping[view][raw_label] = standard_label
        return {view: view_mapping for view, view_mapping in mapping.items() if view_mapping}


def _expanded_svg_size(svg_widget: QSvgWidget) -> tuple[int, int]:
    default_size = svg_widget.renderer().defaultSize()
    if default_size.isValid() and default_size.width() > 0 and default_size.height() > 0:
        aspect = default_size.width() / default_size.height()
        width = max(default_size.width(), 1200)
        height = max(default_size.height(), int(width / aspect))
        if height < 700:
            height = 700
            width = max(width, int(height * aspect))
        return width, height
    return 1200, 700


class StickPlotPreviewThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    preview_ready = Signal(object, str)
    preview_failed = Signal(str)

    def __init__(self, csv_files: tuple[tuple[str, Path], ...], settings: AlmaSettings, alma_root: Path):
        super().__init__()
        self._csv_files = tuple((label, Path(csv_file)) for label, csv_file in csv_files)
        self._settings = settings
        self._alma_root = alma_root

    def run(self) -> None:
        try:
            source_name = ", ".join(csv_file.name for _label, csv_file in self._csv_files)
            self.log_message.emit(f"Generating preview from {source_name}")

            def progress(index: int, total: int, message: str) -> None:
                value = 10 + int(index * 75 / max(1, total))
                self.progress_updated.emit(value, message)
                self.log_message.emit(message)

            temp_root = Path("/private/tmp") if Path("/private/tmp").is_dir() else None
            with tempfile.TemporaryDirectory(prefix="dlc-gait-stickplot-", dir=temp_root) as temp_dir:
                plots: list[tuple[str, bytes]] = []
                for input_index, (label, csv_file) in enumerate(self._csv_files, start=1):
                    side_mapping = None
                    if self._settings.view_bodypart_mapping:
                        side_mapping = self._settings.view_bodypart_mapping.get(label.lower())
                    side_settings = replace(
                        self._settings,
                        custom_bodypart_mapping=side_mapping or self._settings.custom_bodypart_mapping,
                        view_bodypart_mapping=None,
                    )

                    def side_progress(index: int, total: int, message: str) -> None:
                        overall_index = ((input_index - 1) * max(1, total)) + index
                        overall_total = max(1, len(self._csv_files) * max(1, total))
                        progress(overall_index, overall_total, message)

                    results = run_alma_gait_analysis(
                        [csv_file],
                        Path(temp_dir),
                        side_settings,
                        self._alma_root,
                        progress_callback=side_progress,
                    )
                    for result in results:
                        for message in result.messages:
                            self.log_message.emit(message)
                    svg_path = next(
                        (
                            path
                            for result in results
                            for path in result.output_files
                            if path.suffix.lower() == ".svg" and path.exists()
                        ),
                        None,
                    )
                    if svg_path is not None:
                        plots.append((label, svg_path.read_bytes()))

                if not plots:
                    raise RuntimeError(
                        "ALMA did not find a valid stride for the stick plot. Check body-part mapping, "
                        "walking direction, calibration, and stride filters."
                    )
            self.preview_ready.emit(tuple(plots), source_name)
        except Exception as exc:
            csv_file = self._csv_files[0][1] if self._csv_files else Path("")
            self.preview_failed.emit(_format_stickplot_failure(exc, csv_file, self._settings))


class AlmaAnalysisThread(QThread):
    progress_updated = Signal(int, str)
    log_message = Signal(str)
    analysis_completed = Signal(bool, str)

    def __init__(self, files: list[Path | AlmaViewCsvSet], output_folder: Path, settings: AlmaSettings, alma_root: Path):
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
                for message in result.messages:
                    self.log_message.emit(f"  {message}")
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


def _format_stickplot_failure(exc: Exception, csv_file: Path, settings: AlmaSettings) -> str:
    message = str(exc)
    try:
        bodyparts = ", ".join(_read_dlc_bodyparts(csv_file))
    except Exception:
        bodyparts = "could not read body-part labels"

    hints = [
        f"Input CSV: {csv_file.name}",
        f"Detected body parts: {bodyparts}",
        f"Likelihood min: {settings.likelihood_threshold:.2f}",
        "Check Label matching for three-view sets, or the Mapping tab in single-side ALMA mode.",
        "If the confidence cutoff is too strict, lower Likelihood min or set it to 0.",
        "If no stride is found, try Auto-detect direction or relax stride height/length filters.",
    ]
    return message + "\n\n" + "\n".join(hints)


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
    aliases = {
        _normalized_bodypart_label(alias)
        for alias in BODY_PART_ALIASES.get(standard_bodypart, (standard_bodypart,))
    }
    for raw_bodypart in raw_bodyparts:
        if _normalized_bodypart_label(raw_bodypart) in aliases:
            return raw_bodypart
    return None


def _raw_label_for_standard(mapping: dict[str, str], standard_bodypart: str) -> str | None:
    for raw_bodypart, mapped_bodypart in mapping.items():
        if mapped_bodypart == standard_bodypart:
            return raw_bodypart
    return None


def _combo_path(combo: QComboBox) -> Path | None:
    value = combo.currentData()
    if not value:
        return None
    return Path(str(value))


def _csv_choice_label(path: Path, all_paths: list[Path]) -> str:
    if sum(1 for candidate in all_paths if candidate.name == path.name) <= 1:
        return path.name
    return f"{path.name}  ({path.parent.name})"


def _qt_safe_svg_bytes(svg_data: bytes) -> bytes:
    try:
        root = ET.fromstring(svg_data)
    except ET.ParseError:
        return svg_data

    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    defined_ids = {
        element_id
        for element in root.iter()
        if (element_id := element.attrib.get("id"))
    }
    unusable_ids = {
        element.attrib["id"]
        for element in root.iter()
        if _xml_local_name(element.tag) == "path"
        and element.attrib.get("id")
        and not element.attrib.get("d", "").strip()
    }
    removed = False
    for element in list(root.iter()):
        parent = parent_by_child.get(element)
        if parent is None:
            continue
        tag = _xml_local_name(element.tag)
        if tag == "path":
            path_data = element.attrib.get("d", "")
            if not path_data.strip() or _svg_path_has_nonfinite_values(path_data):
                parent.remove(element)
                removed = True
                continue
        if tag == "use":
            href = (
                element.attrib.get("{http://www.w3.org/1999/xlink}href")
                or element.attrib.get("href")
                or ""
            )
            if href.startswith("#") and (href[1:] not in defined_ids or href[1:] in unusable_ids):
                parent.remove(element)
                removed = True
    if not removed:
        return svg_data
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _svg_path_has_nonfinite_values(path_data: str) -> bool:
    return bool(re.search(r"(?i)(?:^|[^a-z])(?:nan|inf|-inf|infinity|-infinity)(?:$|[^a-z])", path_data))


def _suggest_view_set_from_files(paths: list[Path]) -> AlmaViewCsvSet:
    by_view: dict[str, Path] = {}
    for path in paths:
        view = _csv_view_from_name(path)
        if view is not None and view not in by_view:
            by_view[view] = path
    remaining = [path for path in paths if path not in by_view.values()]
    for view in ("left", "right", "bottom"):
        if view not in by_view and remaining:
            by_view[view] = remaining.pop(0)
    return AlmaViewCsvSet(
        name=_csv_view_group_key(by_view.get("left", paths[0])) if paths else "set_1",
        left_csv=by_view.get("left", paths[0]),
        right_csv=by_view.get("right", paths[min(1, len(paths) - 1)]),
        bottom_csv=by_view.get("bottom", paths[min(2, len(paths) - 1)]),
    )


def _normalized_bodypart_label(label: str) -> str:
    return " ".join(label.strip().lower().replace("_", " ").replace("-", " ").split())


def _build_alma_view_csv_sets(paths: list[Path]) -> tuple[list[AlmaViewCsvSet], list[str]]:
    rows = _build_alma_view_pair_rows(paths)
    view_sets: list[AlmaViewCsvSet] = []
    errors: list[str] = []
    for row in rows:
        if row["status"] != "Ready":
            errors.append(f"{row['name']}: {row['status']}.")
            continue
        view_sets.append(
            AlmaViewCsvSet(
                name=row["name"],
                left_csv=row["left"],
                right_csv=row["right"],
                bottom_csv=row["bottom"],
            )
        )
    return view_sets, errors


def _build_alma_view_pair_rows(paths: list[Path]) -> list[dict[str, object]]:
    grouped: dict[tuple[Path, str], dict[str, Path]] = {}
    rows: list[dict[str, object]] = []
    for path in paths:
        view = _csv_view_from_name(path)
        if view is None:
            rows.append(
                {
                    "name": path.stem,
                    "left": None,
                    "right": None,
                    "bottom": None,
                    "status": "Unclassified view",
                }
            )
            continue
        group_key = (path.parent, _csv_view_group_key(path))
        group = grouped.setdefault(group_key, {})
        if view in group:
            rows.append(
                {
                    "name": _view_group_label(group_key),
                    "left": path if view == "left" else None,
                    "right": path if view == "right" else None,
                    "bottom": path if view == "bottom" else None,
                    "status": f"Duplicate {view}",
                }
            )
            continue
        group[view] = path

    for group_key, group in sorted(grouped.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        missing = [view for view in ("left", "right", "bottom") if view not in group]
        rows.append(
            {
                "name": _view_group_label(group_key),
                "left": group.get("left"),
                "right": group.get("right"),
                "bottom": group.get("bottom"),
                "status": "Ready" if not missing else "Missing " + ", ".join(missing),
            }
        )
    return rows


def _path_name(path) -> str:
    return Path(path).name if path is not None else "-"


def _csv_view_from_name(path: Path) -> str | None:
    tokens = _filename_tokens(path)
    stem = path.stem.lower()
    if tokens & {"left", "lhs", "lview"} or "leftview" in stem:
        return "left"
    if tokens & {"right", "rhs", "rview"} or "rightview" in stem:
        return "right"
    if tokens & {"bottom", "down", "ventral", "below", "bview", "dview"} or "bottomview" in stem or "downview" in stem:
        return "bottom"
    return None


def _csv_view_group_key(path: Path) -> str:
    view_tokens = {
        "left",
        "lhs",
        "lview",
        "right",
        "rhs",
        "rview",
        "bottom",
        "down",
        "ventral",
        "below",
        "bview",
        "dview",
    }
    tokens = [token for token in _filename_token_list(path) if token not in view_tokens]
    return "_".join(tokens) or path.stem.lower()


def _view_group_label(group_key: tuple[Path, str]) -> str:
    _parent, key = group_key
    return key or "view_set"


def _filename_tokens(path: Path) -> set[str]:
    return set(_filename_token_list(path))


def _filename_token_list(path: Path) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", path.stem.lower()) if token]
