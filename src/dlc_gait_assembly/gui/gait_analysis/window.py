from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.gait_analysis.dialogs import (
    CsvPairingDialog,
    LabelMappingDialog,
)
from dlc_gait_assembly.gui.gait_analysis.pairing import (
    build_view_csv_sets,
    build_view_pair_rows,
    path_name,
)
from dlc_gait_assembly.gui.gait_analysis.parameter_reference import (
    GaitParameterReferenceWidget,
    GaitParameterSelectionWidget,
)
from dlc_gait_assembly.gui.gait_analysis.previews import (
    OutputPreviewWidget,
    StickPlotPairPreviewWidget,
    previewable_output_paths,
)
from dlc_gait_assembly.gui.gait_analysis.settings import (
    BOTTOM_VIEW_LABELS,
    FORELIMB_BOTTOM_VIEW_LABELS,
    FORELIMB_SIDE_VIEW_LABELS,
    MULTI_SIDE_VIEW_MODE_LABEL,
    SIDE_VIEW_LABELS,
    SINGLE_SIDE_VIEW_MODE_LABEL,
    STANDARD_BODYPARTS,
    auto_bodypart_label,
    read_dlc_bodyparts,
    reference_segment_label,
)
from dlc_gait_assembly.gui.gait_analysis.workers import (
    AlmaAnalysisThread,
    RustLab1AnalysisThread,
    RustLab1PreviewThread,
    StickPlotPreviewThread,
)
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.interaction import (
    add_shortcut,
    animate_button_emphasis,
    install_wheel_value_guard,
    set_tooltip,
)
from dlc_gait_assembly.gui.shared.progress import DynamicProgressBar
from dlc_gait_assembly.gui.shared.widgets import SlidingTabBar, install_sliding_tab_bar
from dlc_gait_assembly.services.analysis_manifests import write_analysis_manifest
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.pipeline.alma import (
    AlmaSettings,
    AlmaViewCsvSet,
    default_alma_root,
    load_alma_config_defaults,
    pixels_per_cm_from_calibration_map,
    settings_from_alma_config,
)
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RustLab1StandaloneSettings,
)
from dlc_gait_assembly.services.project_paths import (
    find_project_root,
    manual_pipeline_output_folders,
)
from dlc_gait_assembly.services.video_processing import probe_video

ALMA_WORKFLOW_LABEL = "ALMA + post-ALMA features"
RUSTLAB1_WORKFLOW_LABEL = "RustLab1 standalone (three-view)"
RUSTLAB1_PAW_LABELS = {
    "Left hind paw": "d-back-left",
    "Right hind paw": "d-back-right",
    "Left front paw": "d-front-left",
    "Right front paw": "d-front-right",
}


class AlmaKinematicsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("GaitAnalysisWidget")
        self._project_root = find_project_root(__file__)
        self._profile_analysis_manifest_path: Path | None = None
        self._alma_root = default_alma_root(self._project_root)
        self._selected_files: list[Path] = []
        self._view_sets: list[AlmaViewCsvSet] = []
        self._view_set_errors: list[str] = []
        self._manual_view_sets: list[AlmaViewCsvSet] | None = None
        self._worker: AlmaAnalysisThread | RustLab1AnalysisThread | None = None
        self._preview_worker: StickPlotPreviewThread | RustLab1PreviewThread | None = None
        self._output_preview_paths: tuple[Path, ...] = ()
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
        self._update_workflow()
        self._update_input_mode()
        self._update_limb_scope()
        self._update_analysis_mode()
        self._update_calibration_method()
        self._update_run_state()

    def can_close(self, parent=None) -> bool:
        analysis_running = self._worker is not None and self._worker.isRunning()
        preview_running = self._preview_worker is not None and self._preview_worker.isRunning()
        if analysis_running or preview_running:
            workflow = "RustLab1" if self._is_rustlab1_workflow() else "gait"
            QMessageBox.information(
                parent or self,
                "Gait processing is running",
                f"Wait for the current preview or {workflow}-analysis run to finish before closing the window.",
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
        self.workspace_title = title
        workflow_label = QLabel("Workflow")
        workflow_label.setObjectName("MutedLabel")
        header_layout.addWidget(workflow_label)
        self.workflow_combo = QComboBox()
        self.workflow_combo.setObjectName("GaitWorkflowSelector")
        self.workflow_combo.addItems((ALMA_WORKFLOW_LABEL, RUSTLAB1_WORKFLOW_LABEL))
        self.workflow_combo.setAccessibleName("Gait analysis workflow")
        set_tooltip(
            self.workflow_combo,
            "Run ALMA with optional post-ALMA features, or run standalone RustLab1 stride detection on a three-view set.",
        )
        header_layout.addWidget(self.workflow_combo)
        header_layout.addStretch(1)
        self.figure_reference_button = QPushButton("Figure documentation")
        self.figure_reference_button.setObjectName("FigureReferenceButton")
        header_layout.addWidget(self.figure_reference_button)
        self.parameter_reference_button = QPushButton("Parameter documentation")
        self.parameter_reference_button.setObjectName("ParameterReferenceButton")
        header_layout.addWidget(self.parameter_reference_button)
        self.documentation_back_button = QPushButton("Back to analysis")
        self.documentation_back_button.setObjectName("DocumentationBackButton")
        self.documentation_back_button.hide()
        header_layout.addWidget(self.documentation_back_button)
        root.addWidget(header, 0)

        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setObjectName("GaitWorkspaceStack")
        root.addWidget(self.workspace_stack, 1)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.workspace_stack.addWidget(splitter)

        left_panel = QWidget()
        left_panel.setObjectName("WorkspaceSidebar")
        left_panel.setMinimumWidth(410)
        left_panel.setMaximumWidth(520)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        file_box = QGroupBox("Multi-view ALMA input and output")
        self.file_box = file_box
        file_layout = QVBoxLayout(file_box)
        button_row = QHBoxLayout()
        self.add_file_button = QPushButton("Add CSVs")
        set_tooltip(self.add_file_button, "Add left, right, and bottom DeepLabCut coordinate CSVs.", "Ctrl+O")
        self.add_folder_button = QPushButton("Add folder")
        set_tooltip(
            self.add_folder_button, "Add every CSV in a folder and group left/right/bottom views.", "Ctrl+Shift+O"
        )
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
        settings_tabs.tabBar().hide()
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
        initial_multiside = self._defaults.input_mode not in {"Single side view", "Single-side ALMA"}
        parameters_tab = GaitParameterSelectionWidget(
            self._defaults.enabled_parameter_names,
            multiside=initial_multiside,
        )
        settings_tabs.addTab(setup_tab, "Setup")
        settings_tabs.addTab(calibration_tab, "Calibration")
        settings_tabs.addTab(analysis_tab, "Analysis")
        settings_tabs.addTab(filters_tab, "Filters")
        settings_tabs.addTab(mapping_tab, "Mapping")
        settings_tabs.addTab(parameters_tab, "Parameters")
        settings_tabs.addTab(output_tab, "Output")
        section_labels = [settings_tabs.tabText(index) for index in range(settings_tabs.count())]
        self.settings_section_rows = (
            SlidingTabBar(theme.TOOL_3),
            SlidingTabBar(theme.TOOL_3),
        )
        for label in section_labels[:4]:
            self.settings_section_rows[0].addTab(label)
        for label in section_labels[4:]:
            self.settings_section_rows[1].addTab(label)
        # Drive navigation from explicit clicks rather than currentChanged. The
        # inactive row intentionally has index -1, and using currentChanged for
        # both user input and programmatic synchronization can drop rapid
        # top-to-bottom (or bottom-to-top) selections.
        self.settings_section_rows[0].tabBarClicked.connect(
            lambda index: settings_tabs.setCurrentIndex(index)
        )
        self.settings_section_rows[1].tabBarClicked.connect(
            lambda index: settings_tabs.setCurrentIndex(index + 4)
        )

        def sync_settings_rows(index: int) -> None:
            first_index = index if index < 4 else -1
            second_index = index - 4 if index >= 4 else -1
            self.settings_section_rows[0].set_active_row(index < 4)
            self.settings_section_rows[1].set_active_row(index >= 4)
            for row, row_index in zip(
                self.settings_section_rows,
                (first_index, second_index),
                strict=True,
            ):
                row.blockSignals(True)
                row.setCurrentIndex(row_index)
                row.blockSignals(False)

        settings_tabs.currentChanged.connect(sync_settings_rows)
        sync_settings_rows(0)
        self.mapping_tab = mapping_tab
        self.parameter_selection = parameters_tab

        setup_box = QGroupBox("Experimental setup")
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
        set_tooltip(
            self.input_mode_combo, "Switch between one side-view CSV and paired left/right/bottom CSV analysis."
        )
        set_tooltip(self.analysis_type_combo, "Choose treadmill or spontaneous-walking analysis.")
        set_tooltip(
            self.limb_scope_combo,
            "Choose the established hindlimb output or add RustLab1 forelimb and interlimb parameters and plots.",
        )
        setup_layout.addWidget(QLabel("Input mode"), 0, 0)
        setup_layout.addWidget(self.input_mode_combo, 0, 1)
        setup_layout.addWidget(QLabel("Analysis type"), 1, 0)
        setup_layout.addWidget(self.analysis_type_combo, 1, 1)
        setup_layout.addWidget(QLabel("Limb analysis"), 2, 0)
        setup_layout.addWidget(self.limb_scope_combo, 2, 1)
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
        self.reference_segment_combo.addItems(
            ["ankle_toe (1.5cm)", "hip_knee (2.5cm)", "knee_ankle (2.0cm)", "ankle_mtp (0.8cm)"]
        )
        self.reference_segment_combo.setCurrentText(reference_segment_label(self._defaults.reference_segment))
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

        stroke_calibration_widget = QWidget()
        stroke_calibration_layout = QGridLayout(stroke_calibration_widget)
        stroke_calibration_layout.setContentsMargins(16, 4, 0, 0)
        configured_bottom = (self._defaults.view_calibration or {}).get("bottom", {})
        if isinstance(configured_bottom, (int, float)):
            bottom_x_default = bottom_y_default = float(configured_bottom)
        elif isinstance(configured_bottom, dict):
            bottom_x_default = float(
                configured_bottom.get("x_pixels_per_cm", configured_bottom.get("pixels_per_cm", 0.0))
            )
            bottom_y_default = float(
                configured_bottom.get("y_pixels_per_cm", configured_bottom.get("pixels_per_cm", 0.0))
            )
        else:
            bottom_x_default = bottom_y_default = 0.0
        self.bottom_x_pixels_per_cm_spin = _double_spin(0.0, 2000.0, bottom_x_default, 3)
        self.bottom_y_pixels_per_cm_spin = _double_spin(0.0, 2000.0, bottom_y_default, 3)
        set_tooltip(
            self.bottom_x_pixels_per_cm_spin,
            "Bottom-view horizontal calibration. Set both bottom values; zero disables synchronized stroke outputs.",
        )
        set_tooltip(
            self.bottom_y_pixels_per_cm_spin,
            "Bottom-view vertical calibration. Axis-specific values account for mirror distortion.",
        )
        stroke_calibration_layout.addWidget(QLabel("Bottom X pixels per cm"), 0, 0)
        stroke_calibration_layout.addWidget(self.bottom_x_pixels_per_cm_spin, 0, 1)
        stroke_calibration_layout.addWidget(QLabel("Bottom Y pixels per cm"), 1, 0)
        stroke_calibration_layout.addWidget(self.bottom_y_pixels_per_cm_spin, 1, 1)
        calibration_layout.addWidget(stroke_calibration_widget)
        calibration_tab_layout.addWidget(calibration_box)
        calibration_tab_layout.addStretch(1)

        movement_box = QGroupBox("Movement analysis settings")
        self.movement_box = movement_box
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
        self.filter_box = filter_box
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

        stroke_filter_box = QGroupBox("Synchronized stroke-pilot QC")
        self.stroke_filter_box = stroke_filter_box
        stroke_filter_layout = QGridLayout(stroke_filter_box)
        self.stroke_likelihood_spin = _double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2)
        self.stroke_likelihood_spin.setEnabled(False)
        set_tooltip(
            self.stroke_likelihood_spin,
            "Synchronized outputs use the same likelihood threshold as ALMA.",
        )
        self.stroke_gap_spin = QSpinBox()
        self.stroke_gap_spin.setRange(0, 60)
        self.stroke_gap_spin.setSpecialValueText("ALMA full")
        self.stroke_gap_spin.setValue(0)
        self.stroke_gap_spin.setEnabled(False)
        set_tooltip(
            self.stroke_gap_spin,
            "Synchronized outputs use ALMA's linear interpolation in both directions.",
        )
        self.stroke_swing_speed_spin = _double_spin(0.1, 100.0, self._defaults.swing_speed_threshold_cm_s, 1)
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
        self.rustlab_likelihood_spin = _double_spin(0.0, 1.0, 0.95, 2)
        self.rustlab_likelihood_spin.setSingleStep(0.01)
        self.rustlab_stance_speed_spin = _double_spin(0.0, 100.0, 7.0, 1)
        self.rustlab_min_stance_spin = QSpinBox()
        self.rustlab_min_stance_spin.setRange(1, 120)
        self.rustlab_min_stance_spin.setValue(1)
        self.rustlab_min_swing_spin = QSpinBox()
        self.rustlab_min_swing_spin.setRange(1, 120)
        self.rustlab_min_swing_spin.setValue(1)
        set_tooltip(
            self.rustlab_reference_paw_combo,
            "Bottom-view paw whose stance onsets define standalone RustLab1 strides.",
        )
        set_tooltip(
            self.rustlab_likelihood_spin,
            "Minimum DLC likelihood for standalone RustLab1 coordinates. The upstream notebook uses 0.95.",
        )
        set_tooltip(
            self.rustlab_stance_speed_spin,
            "RustLab1 stance rule in pixels per frame. The upstream notebook uses 7.",
        )
        set_tooltip(
            self.rustlab_min_stance_spin,
            "Minimum consecutive stance frames; raise this to suppress short false contacts.",
        )
        set_tooltip(
            self.rustlab_min_swing_spin,
            "Minimum consecutive swing frames between stance periods.",
        )
        rustlab_detector_layout.addWidget(QLabel("Reference paw"), 0, 0)
        rustlab_detector_layout.addWidget(self.rustlab_reference_paw_combo, 0, 1)
        rustlab_detector_layout.addWidget(QLabel("Likelihood min"), 1, 0)
        rustlab_detector_layout.addWidget(self.rustlab_likelihood_spin, 1, 1)
        rustlab_detector_layout.addWidget(QLabel("Stance speed max (px/frame)"), 2, 0)
        rustlab_detector_layout.addWidget(self.rustlab_stance_speed_spin, 2, 1)
        rustlab_detector_layout.addWidget(QLabel("Minimum stance frames"), 3, 0)
        rustlab_detector_layout.addWidget(self.rustlab_min_stance_spin, 3, 1)
        rustlab_detector_layout.addWidget(QLabel("Minimum swing frames"), 4, 0)
        rustlab_detector_layout.addWidget(self.rustlab_min_swing_spin, 4, 1)
        rustlab_detector_box.hide()
        self.rustlab_detector_box = rustlab_detector_box
        filters_tab_layout.addWidget(rustlab_detector_box)
        filters_tab_layout.addStretch(1)
        analysis_tab_layout.addStretch(1)

        output_options_box = QGroupBox("Output options")
        self.output_options_box = output_options_box
        output_options_layout = QGridLayout(output_options_box)
        output_options_layout.setHorizontalSpacing(12)
        output_options_layout.setVerticalSpacing(4)
        self.continuous_strides_spin = QSpinBox()
        self.continuous_strides_spin.setRange(1, 50)
        self.continuous_strides_spin.setValue(self._defaults.n_continuous_strides)
        self.stickplot_checkbox = QCheckBox("Generate stickplot SVG")
        self.stickplot_checkbox.setChecked(True)
        self.alma_representations_checkbox = QCheckBox("Generate ALMA summary tables and diagnostic figures")
        self.alma_representations_checkbox.setChecked(self._defaults.generate_alma_representations)
        self.rustlab1_checkbox = QCheckBox("Generate RustLab1 and custom SOP parameters, merged CSV, and figures")
        self.rustlab1_checkbox.setChecked(self._defaults.generate_rustlab1_parameters)
        self.stroke_analysis_checkbox = QCheckBox("Generate synchronized stroke-pilot outputs (hindlimb-focused)")
        self.stroke_analysis_checkbox.setChecked(self._defaults.stroke_analysis_enabled)
        set_tooltip(self.continuous_strides_spin, "Number of continuous strides used for ALMA outputs.")
        set_tooltip(self.stickplot_checkbox, "Generate an SVG stickplot output.")
        set_tooltip(
            self.alma_representations_checkbox,
            "Write tidy and summary CSV tables plus eight ALMA timing, spatial, joint, trend, heatmap, correlation, variability, and drag figures.",
        )
        set_tooltip(
            self.rustlab1_checkbox,
            "Calculate 30 hindlimb RustLab1 parameters or 76 hindlimb/forelimb parameters, add 14 custom SOP parameters, merge them with ALMA cycles, and write 18 limb-aware runway SVG figures.",
        )
        output_options_layout.addWidget(QLabel("Continuous strides"), 0, 0)
        output_options_layout.addWidget(self.continuous_strides_spin, 0, 1)
        output_options_layout.addWidget(self.stickplot_checkbox, 1, 0, 1, 2)
        output_options_layout.addWidget(self.alma_representations_checkbox, 2, 0, 1, 2)
        output_options_layout.addWidget(self.stroke_analysis_checkbox, 3, 0, 1, 2)
        output_tab_layout.addWidget(output_options_box)

        rustlab_box = QGroupBox("RustLab1 multi-view")
        self.rustlab_box = rustlab_box
        rustlab_layout = QVBoxLayout(rustlab_box)
        rustlab_layout.setSpacing(6)
        rustlab_layout.addWidget(self.rustlab1_checkbox)
        self.rustlab_status_label = QLabel("RustLab1 needs paired left, right, and bottom CSVs.")
        self.rustlab_status_label.setObjectName("MutedLabel")
        self.rustlab_status_label.setWordWrap(True)
        rustlab_layout.addWidget(self.rustlab_status_label)
        output_tab_layout.addWidget(rustlab_box)
        output_tab_layout.addStretch(1)

        settings_navigation = QVBoxLayout()
        settings_navigation.setSpacing(2)
        for row in self.settings_section_rows:
            row.setObjectName("RunwaySettingsSectionRow")
            row.setExpanding(True)
            row.setDrawBase(False)
            settings_navigation.addWidget(row)
        left_layout.addLayout(settings_navigation)
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
        right_panel.setObjectName("WorkspaceCanvas")
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

        self.workspace_tabs = QTabWidget()
        install_sliding_tab_bar(self.workspace_tabs, theme.TOOL_3)
        self.workspace_tabs.setObjectName("RunwayWorkspaceTabs")
        self.workspace_tabs.setDocumentMode(True)
        self.workspace_tabs.tabBar().setExpanding(True)
        right_layout.addWidget(self.workspace_tabs, 1)

        self.inputs_page = QWidget()
        inputs_layout = QVBoxLayout(self.inputs_page)
        inputs_layout.setContentsMargins(8, 10, 8, 8)
        inputs_layout.addWidget(file_box)
        inputs_layout.addStretch(1)
        self.workspace_tabs.addTab(self.inputs_page, "1. Inputs")

        self.preview_stack = QStackedWidget()
        self.preview_stack.setObjectName("StickPlotPreview")
        self.preview_stack.setMinimumHeight(280)
        self.preview_placeholder = QLabel("Select left/right/bottom CSVs, then generate a stick-plot preview.")
        self.preview_placeholder.setAlignment(Qt.AlignCenter)
        self.preview_placeholder.setWordWrap(True)
        self.preview_placeholder.setObjectName("MutedLabel")
        self.stickplot_view = StickPlotPairPreviewWidget()
        self.stickplot_view.setObjectName("StickPlotPairPreview")
        self.stickplot_view.setMinimumSize(320, 260)
        self.stickplot_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output_preview_view = OutputPreviewWidget(
            max_csv_rows=7,
            max_csv_columns=10,
        )
        self.output_preview_view.setObjectName("GaitOutputPreview")
        self.preview_stack.addWidget(self.preview_placeholder)
        self.preview_stack.addWidget(self.stickplot_view)
        self.preview_stack.addWidget(self.output_preview_view)
        self.preview_stack.setCurrentWidget(self.preview_placeholder)

        self.preview_page = QWidget()
        preview_layout = QVBoxLayout(self.preview_page)
        preview_layout.setContentsMargins(8, 10, 8, 8)
        preview_layout.addWidget(self.preview_stack, 1)
        self.workspace_tabs.addTab(self.preview_page, "2. Preview / results")

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(280)
        self.log.setPlaceholderText("Preview and analysis messages will appear here.")
        self.log_page = QWidget()
        log_layout = QVBoxLayout(self.log_page)
        log_layout.setContentsMargins(8, 10, 8, 8)
        log_layout.addWidget(self.log, 1)
        self.workspace_tabs.addTab(self.log_page, "3. Run log")

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

        left_layout.removeWidget(self.export_manifest_button)
        left_layout.removeWidget(self.preview_button)
        left_layout.removeWidget(self.run_button)

        left_column = QWidget()
        left_column.setObjectName("WorkspaceSidebar")
        left_column.setMinimumWidth(430)
        left_column.setMaximumWidth(540)
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(0)

        for layout_index in range(left_layout.count()):
            item = left_layout.itemAt(layout_index)
            if item.layout() is settings_navigation:
                left_layout.takeAt(layout_index)
                break
        sticky_settings_navigation = QWidget()
        sticky_settings_navigation.setObjectName("RunwayStickySettingsNavigation")
        sticky_settings_layout = QVBoxLayout(sticky_settings_navigation)
        sticky_settings_layout.setContentsMargins(16, 10, 16, 6)
        sticky_settings_layout.setSpacing(0)
        sticky_settings_layout.addLayout(settings_navigation)
        left_column_layout.addWidget(sticky_settings_navigation, 0)

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("RunwayControlsScroll")
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setWidget(left_panel)
        left_column_layout.addWidget(self.controls_scroll, 1)

        action_footer = QWidget()
        action_footer.setObjectName("RunwayActionFooter")
        action_layout = QVBoxLayout(action_footer)
        action_layout.setContentsMargins(16, 8, 16, 16)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.export_manifest_button)
        action_layout.addWidget(self.preview_button)
        action_layout.addWidget(self.run_button)
        left_column_layout.addWidget(action_footer, 0)

        splitter.addWidget(left_column)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 780])
        self.parameter_reference = GaitParameterReferenceWidget()
        self.parameter_reference.set_multiside(initial_multiside)
        self.workspace_stack.addWidget(self.parameter_reference)

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
        self.figure_reference_button.clicked.connect(self._show_figure_documentation)
        self.parameter_reference_button.clicked.connect(self._show_parameter_documentation)
        self.documentation_back_button.clicked.connect(self._close_documentation)
        self.add_file_button.clicked.connect(self._add_file)
        self.add_folder_button.clicked.connect(self._add_folder)
        self.clear_files_button.clicked.connect(self._clear_files)
        self.edit_pairing_button.clicked.connect(self._open_csv_pairing_dialog)
        self.label_matching_button.clicked.connect(self._open_label_matching_dialog)
        self.output_folder_button.clicked.connect(self._select_output_folder)
        self.output_folder_edit.textChanged.connect(self._update_run_state)
        self.preview_button.clicked.connect(self._generate_stickplot_preview)
        self.run_button.clicked.connect(self._run_analysis)
        self.workflow_combo.currentTextChanged.connect(self._update_workflow)
        self.analysis_type_combo.currentTextChanged.connect(self._update_analysis_mode)
        self.limb_scope_combo.currentTextChanged.connect(self._update_limb_scope)
        self.likelihood_threshold_spin.valueChanged.connect(self.stroke_likelihood_spin.setValue)
        self.calibration_method_combo.currentTextChanged.connect(self._update_calibration_method)
        self.load_fps_button.clicked.connect(self._load_frame_rate_from_video)
        self.import_calibration_map_button.clicked.connect(self._import_calibration_map)
        self.export_manifest_button.clicked.connect(self._export_analysis_manifest)
        self.use_custom_mapping_checkbox.toggled.connect(self._update_mapping_enabled)
        self.reload_mapping_button.clicked.connect(self._load_bodypart_mapping_from_first_file)
        self.auto_mapping_button.clicked.connect(self._apply_auto_bodypart_mapping)
        self.file_list.model().rowsInserted.connect(self._update_run_state)
        self.file_list.model().rowsRemoved.connect(self._update_run_state)
        self.file_list.currentRowChanged.connect(self._preview_file_changed)
        self.view_set_table.currentItemChanged.connect(self._preview_view_set_changed)
        self.input_mode_combo.currentTextChanged.connect(self._update_input_mode)

        preview_controls = (
            self.workflow_combo,
            self.input_mode_combo,
            self.analysis_type_combo,
            self.limb_scope_combo,
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
            self.rustlab_likelihood_spin,
            self.rustlab_stance_speed_spin,
            self.rustlab_min_stance_spin,
            self.rustlab_min_swing_spin,
        )
        for spin in preview_spins:
            spin.valueChanged.connect(self._invalidate_stickplot_preview)

        self.rustlab_reference_paw_combo.currentTextChanged.connect(
            self._invalidate_stickplot_preview
        )

        for checkbox in (
            self.no_outlier_checkbox,
            self.dragging_filter_checkbox,
            self.use_custom_mapping_checkbox,
        ):
            checkbox.toggled.connect(self._invalidate_stickplot_preview)
        for combo in self._bodypart_combos.values():
            combo.currentTextChanged.connect(self._invalidate_stickplot_preview)

    def _show_figure_documentation(self) -> None:
        self.parameter_reference.figure_source_filter.setCurrentText(
            "RustLab1" if self._is_rustlab1_workflow() else "All figures"
        )
        self.parameter_reference.show_figure_documentation()
        self._show_documentation("Figure creator documentation")

    def _show_parameter_documentation(self) -> None:
        self.parameter_reference.set_multiside(self._is_three_view_mode())
        self.parameter_reference.source_filter.setCurrentText(
            "RustLab1" if self._is_rustlab1_workflow() else "All sources"
        )
        self.parameter_reference.show_parameter_documentation()
        self._show_documentation("Gait parameter documentation")

    def _show_documentation(self, title: str) -> None:
        self.workspace_stack.setCurrentWidget(self.parameter_reference)
        self.workspace_title.setText(title)
        self.documentation_back_button.show()

    def _close_documentation(self) -> None:
        self.workspace_stack.setCurrentIndex(0)
        self.workspace_title.setText(
            "RustLab1 standalone analysis"
            if self._is_rustlab1_workflow()
            else "Runway analysis"
        )
        self.documentation_back_button.hide()

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
        directory = QFileDialog.getExistingDirectory(
            self, "Select folder containing CSV files", str(self._project_root)
        )
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
        self._invalidate_stickplot_preview(
            "Select matched left/right/bottom CSVs, then generate a RustLab1 stride preview."
            if self._is_rustlab1_workflow()
            else "Select left/right/bottom CSVs, then generate a stick-plot preview."
        )
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
            self._view_sets, self._view_set_errors = build_view_csv_sets(self._selected_files)
        self._refresh_view_set_table()
        if self._manual_view_sets is not None and self._view_sets:
            suffix = "" if len(self._view_sets) == 1 else "s"
            self.view_set_status_label.setText(f"Manual pairing: {len(self._view_sets)} complete CSV set{suffix}.")
            self.rustlab_status_label.setText(
                f"RustLab1 ready for {len(self._view_sets)} manually paired CSV set{suffix}."
            )
        elif self._manual_view_sets is not None:
            self.view_set_status_label.setText("Manual pairing has no complete left/right/bottom CSV sets.")
            self.rustlab_status_label.setText("RustLab1 waiting for complete manual CSV pairs.")
        elif self._view_sets and not self._view_set_errors:
            suffix = "" if len(self._view_sets) == 1 else "s"
            self.view_set_status_label.setText(
                f"Ready: {len(self._view_sets)} complete left/right/bottom CSV set{suffix}."
            )
            self.rustlab_status_label.setText(f"RustLab1 ready for {len(self._view_sets)} paired CSV set{suffix}.")
        elif self._view_sets:
            self.view_set_status_label.setText(
                f"{len(self._view_sets)} complete set(s); " + " ".join(self._view_set_errors)
            )
            self.rustlab_status_label.setText(
                "RustLab1 ready for complete paired sets; unresolved rows will be ignored."
            )
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
            rows = build_view_pair_rows(self._selected_files)
        self.view_set_table.blockSignals(True)
        self.view_set_table.clear()
        complete_index = 0
        first_ready_item = None
        for row in rows:
            item = QTreeWidgetItem(
                [
                    row["name"],
                    path_name(row.get("left")),
                    path_name(row.get("right")),
                    path_name(row.get("bottom")),
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
        title = (
            "Select RustLab1 output folder"
            if self._is_rustlab1_workflow()
            else "Select ALMA output folder"
        )
        directory = QFileDialog.getExistingDirectory(self, title, self.output_folder_edit.text())
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
            QMessageBox.warning(
                self, "No frame rate detected", "The selected video did not report a usable frame rate."
            )
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
        self.bottom_x_pixels_per_cm_spin.setValue(pixels_per_cm)
        self.bottom_y_pixels_per_cm_spin.setValue(pixels_per_cm)
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

        self._profile_analysis_manifest_path = Path(exported).expanduser().resolve()
        self.status_label.setText("Analysis manifest exported.")
        self._append_log(f"Analysis manifest exported to {exported}")
        QMessageBox.information(
            self,
            "Analysis manifest exported",
            f"Saved the current gait-analysis settings to:\n{exported}",
        )

    def profile_analysis_manifest_path(self) -> Path | None:
        """Return the analysis manifest most recently exported in this workspace."""
        return self._profile_analysis_manifest_path

    def export_profile_preset(self, output_dir: Path) -> Path:
        """Serialize the current gait-analysis controls without opening a dialog."""
        return write_analysis_manifest(
            Path(output_dir) / "analysis_manifest.json",
            self._collect_settings(),
        )

    def profile_calibration_map_path(self) -> Path | None:
        return self._calibration_map_path

    def _load_bodypart_mapping_from_first_file(self) -> None:
        if not self._selected_files:
            QMessageBox.information(
                self, "No input files", "Add left/right/bottom CSV files before loading body part labels."
            )
            return

        csv_path = self._selected_preview_file()
        try:
            self._raw_bodyparts = read_dlc_bodyparts(csv_path)
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
                "left": read_dlc_bodyparts(view_set.left_csv),
                "right": read_dlc_bodyparts(view_set.right_csv),
                "bottom": read_dlc_bodyparts(view_set.bottom_csv),
            }
        except Exception as exc:
            QMessageBox.critical(self, "Could not read labels", str(exc))
            return

        dialog = LabelMappingDialog(
            view_set,
            labels_by_view,
            self._view_label_mappings.get(view_set.name, {}),
            self,
            include_forelimb=self.limb_scope_combo.currentText() == "Hindlimb + Forelimb",
        )
        if dialog.exec() != QDialog.Accepted:
            return

        mapping = dialog.mapping()
        if mapping:
            self._view_label_mappings[view_set.name] = mapping
        else:
            self._view_label_mappings.pop(view_set.name, None)
        selected_count = sum(len(view_mapping) for view_mapping in mapping.values())
        available_count = 27 if self.limb_scope_combo.currentText() == "Hindlimb + Forelimb" else 16
        self.mapping_status_label.setText(f"{selected_count}/{available_count} labels assigned for {view_set.name}.")
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

    def _is_rustlab1_workflow(self) -> bool:
        return self.workflow_combo.currentText() == RUSTLAB1_WORKFLOW_LABEL

    def _update_workflow(self) -> None:
        rustlab1_only = self._is_rustlab1_workflow()
        if rustlab1_only and self.input_mode_combo.currentText() != MULTI_SIDE_VIEW_MODE_LABEL:
            self.input_mode_combo.setCurrentText(MULTI_SIDE_VIEW_MODE_LABEL)
        self.input_mode_combo.setEnabled(not rustlab1_only)
        self.analysis_type_combo.setEnabled(not rustlab1_only)
        self.workspace_title.setText(
            "RustLab1 standalone analysis" if rustlab1_only else "Runway analysis"
        )
        self.file_box.setTitle(
            "Three-view RustLab1 input and output"
            if rustlab1_only
            else "Multi-view ALMA input and output"
        )
        self.movement_box.setTitle(
            "Coordinate smoothing (RustLab1)"
            if rustlab1_only
            else "Movement analysis settings"
        )
        for control in (self.direction_combo, self.drag_clearance_spin, self.drag_frames_spin):
            control.setEnabled(not rustlab1_only)
        self.filter_box.setVisible(not rustlab1_only)
        self.stroke_filter_box.setVisible(not rustlab1_only)
        self.rustlab_detector_box.setVisible(rustlab1_only)
        self.output_options_box.setVisible(not rustlab1_only)
        self.parameter_selection.set_source_filter("RustLab1" if rustlab1_only else None)
        self.rustlab_box.setTitle(
            "Standalone RustLab1 outputs" if rustlab1_only else "RustLab1 multi-view"
        )
        self.rustlab1_checkbox.setText(
            "Generate the 18 RustLab1 runway figures"
            if rustlab1_only
            else "Generate RustLab1 and custom SOP parameters, merged CSV, and figures"
        )
        self.rustlab1_checkbox.setEnabled(True)
        self.rustlab1_checkbox.setChecked(True if rustlab1_only else self.rustlab1_checkbox.isChecked())
        set_tooltip(
            self.rustlab1_checkbox,
            (
                "Write the optional adapted 18-figure RustLab1 runway bundle."
                if rustlab1_only
                else "Calculate RustLab1 and custom SOP features on ALMA cycles and write the merged outputs."
            ),
        )
        set_tooltip(
            self.output_folder_edit,
            (
                "Folder where standalone RustLab1 outputs will be saved."
                if rustlab1_only
                else "Folder where ALMA gait-analysis outputs will be saved."
            ),
        )
        self.rustlab_status_label.setText(
            "Standalone mode detects strides from the selected bottom-view paw and runs only RustLab1."
            if rustlab1_only
            else "RustLab1 needs paired left, right, and bottom CSVs."
        )
        self.export_manifest_button.setEnabled(not rustlab1_only)
        self.preview_button.setText(
            "1. Generate RustLab1 stride preview"
            if rustlab1_only
            else "1. Generate stick-plot preview"
        )
        self.run_button.setText(
            "2. Run RustLab1 analysis" if rustlab1_only else "2. Run gait analysis"
        )
        set_tooltip(
            self.preview_button,
            (
                "Detect RustLab1 stance-onset strides from the selected three-view set and preview the paw-speed trace."
                if rustlab1_only
                else "Generate and inspect an ALMA stick plot from the selected left-view CSV before running the full analysis."
            ),
            "Ctrl+P",
        )
        set_tooltip(
            self.run_button,
            (
                "Run standalone RustLab1 analysis after reviewing its stride preview."
                if rustlab1_only
                else "Run ALMA gait analysis after reviewing the stick plot."
            ),
            "Ctrl+R",
        )
        self._update_analysis_mode()
        self._update_limb_scope()
        self._invalidate_stickplot_preview()

    def _update_input_mode(self) -> None:
        three_view = self._is_three_view_mode()
        self.parameter_selection.set_multiside(three_view)
        self.parameter_reference.set_multiside(three_view)
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
        if self._is_rustlab1_workflow():
            self.treadmill_speed_label.hide()
            self.treadmill_speed_spin.hide()
            self.spontaneous_box.hide()
            return
        treadmill = self.analysis_type_combo.currentText() == "Treadmill"
        self.treadmill_speed_label.setVisible(treadmill)
        self.treadmill_speed_spin.setVisible(treadmill)
        self.spontaneous_box.setVisible(not treadmill)

    def _update_limb_scope(self) -> None:
        include_forelimb = self.limb_scope_combo.currentText() == "Hindlimb + Forelimb"
        self.parameter_selection.set_limb_scope(include_forelimb)
        if self._is_three_view_mode() and not self._is_rustlab1_workflow():
            detail = "76 RustLab1 parameters" if include_forelimb else "30 RustLab1 parameters"
            self.rustlab_status_label.setText(f"RustLab1 mode: {detail}; paired left, right, and bottom CSVs required.")

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
        self.run_button.setEnabled(has_files and has_output and self._stickplot_preview_ready and not running)

    def _invalidate_stickplot_preview(self, message=None, *_args) -> None:
        rustlab1_only = self._is_rustlab1_workflow()
        preview_name = "RustLab1 stride preview" if rustlab1_only else "stick-plot preview"
        if isinstance(message, str) and message:
            placeholder_text = message
        elif self._is_three_view_mode() and self._selected_files and not self._has_valid_view_sets():
            placeholder_text = self._multiview_requirement_message()
        elif self._selected_files:
            source_name = (
                self._selected_view_set().name
                if rustlab1_only and self._selected_view_set() is not None
                else self._selected_preview_file().name
            )
            placeholder_text = f"Settings changed. Regenerate the {preview_name} for {source_name}."
        else:
            if rustlab1_only:
                placeholder_text = (
                    "Select matched left/right/bottom CSVs, then generate a RustLab1 stride preview."
                )
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
            self.status_label.setText(f"Generate a {preview_name} before running the analysis.")
        else:
            self.status_label.setText(
                "Select matched left/right/bottom CSV files to begin."
                if self._is_three_view_mode()
                else "Select a side-view CSV file to begin."
            )
        self.preview_placeholder.setText(placeholder_text)
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        self.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        self._update_run_state()

    def _generate_stickplot_preview(self) -> None:
        if not self._has_valid_inputs():
            QMessageBox.information(
                self,
                "Input CSVs required",
                self._input_requirement_message(),
            )
            return
        if self._is_rustlab1_workflow():
            self._generate_rustlab1_preview()
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
            self.mapping_status_label.setText("Missing required ALMA body parts: " + ", ".join(missing_bodyparts))
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
        self.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        animate_button_emphasis(self.preview_button, True)
        animate_button_emphasis(self.run_button, False)
        self.log.clear()
        preview_inputs = self._preview_inputs()
        preview_names = ", ".join(path.name for _label, path in preview_inputs)
        self.status_label.setText(f"Generating stick-plot preview for {preview_names}...")
        self.preview_placeholder.setText(f"Generating ALMA stick plot for {preview_names}...")
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        self.workspace_tabs.setCurrentWidget(self.preview_page)

        preview_settings = replace(
            settings,
            generate_stickplot=True,
            generate_alma_representations=False,
            generate_rustlab1_parameters=False,
            stroke_analysis_enabled=False,
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

    def _generate_rustlab1_preview(self) -> None:
        view_set = self._selected_view_set()
        if view_set is None:
            QMessageBox.information(
                self,
                "Three-view CSV set required",
                self._multiview_requirement_message(),
            )
            return
        settings = replace(
            self._collect_rustlab1_settings(),
            view_bodypart_mapping=self._view_label_mappings.get(view_set.name),
        )
        missing_bodyparts = self._missing_rustlab1_bodyparts(view_set, settings)
        if missing_bodyparts:
            self._open_label_matching_dialog()
            self.mapping_status_label.setText(
                "Missing required RustLab1 body parts: " + ", ".join(missing_bodyparts)
            )
            QMessageBox.warning(
                self,
                "RustLab1 label mapping incomplete",
                "RustLab1 needs the side-view joints and bottom-view paw labels for the "
                "selected limb scope and reference paw. Open Label matching and assign "
                "the missing labels for this CSV set.",
            )
            return

        self._stickplot_preview_ready = False
        self._preview_invalidated_while_running = False
        self.progress.setValue(0)
        self.progress.set_active(True)
        self.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        animate_button_emphasis(self.preview_button, True)
        animate_button_emphasis(self.run_button, False)
        self.log.clear()
        self.status_label.setText(f"Detecting RustLab1 strides for {view_set.name}...")
        self.preview_placeholder.setText(
            f"Generating bottom-paw speed and stride preview for {view_set.name}..."
        )
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        self.workspace_tabs.setCurrentWidget(self.preview_page)

        self._preview_worker = RustLab1PreviewThread(view_set, settings, self._alma_root)
        self._preview_worker.progress_updated.connect(self._update_progress)
        self._preview_worker.log_message.connect(self._append_log)
        self._preview_worker.preview_ready.connect(self._stickplot_preview_completed)
        self._preview_worker.preview_failed.connect(self._stickplot_preview_failed)
        self._preview_worker.finished.connect(self._preview_worker_finished)
        self._preview_worker.start()
        self._update_run_state()

    def _stickplot_preview_completed(self, plots, source_name: str) -> None:
        rustlab1_only = self._is_rustlab1_workflow()
        preview_name = "RustLab1 stride preview" if rustlab1_only else "Stick-plot preview"
        if self._preview_invalidated_while_running:
            self._stickplot_preview_ready = False
            self.preview_placeholder.setText("Settings changed while the preview was running. Generate it again.")
            self.preview_stack.setCurrentWidget(self.preview_placeholder)
            self.status_label.setText(f"{preview_name} is out of date.")
            self._append_log("Preview discarded because its settings changed during generation.")
            return
        plot_tuple = tuple(plots)
        if not plot_tuple:
            self._stickplot_preview_failed(f"{preview_name} did not return any SVG plots.")
            return
        self.stickplot_view.load_plots(plot_tuple)
        self.preview_stack.setCurrentWidget(self.stickplot_view)
        self.workspace_tabs.setCurrentWidget(self.preview_page)
        self._stickplot_preview_ready = True
        self._preview_svg_data = plot_tuple
        self._preview_source_name = source_name
        self.progress.setValue(100)
        self.preview_button.setIcon(interface_icon("check", theme.STATUS_READY))
        animate_button_emphasis(self.preview_button, False)
        next_action = "run RustLab1 analysis" if rustlab1_only else "run gait analysis"
        self.status_label.setText(f"{preview_name} ready. Review it, then {next_action}.")
        self._append_log(f"{preview_name} generated from {source_name}.")

    def _stickplot_preview_failed(self, message: str) -> None:
        preview_name = (
            "RustLab1 stride preview" if self._is_rustlab1_workflow() else "Stick-plot preview"
        )
        self._stickplot_preview_ready = False
        self._preview_svg_data = None
        self._preview_source_name = ""
        self.preview_placeholder.setText(f"{preview_name} could not be generated.")
        self.preview_stack.setCurrentWidget(self.preview_placeholder)
        self.status_label.setText(f"{preview_name} failed.")
        self.progress.set_active(False)
        self.preview_button.setIcon(interface_icon("eye", theme.TEXT))
        animate_button_emphasis(self.preview_button, False)
        self._append_log(message)
        QMessageBox.critical(self, f"{preview_name} failed", message)

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
            preview_name = (
                "RustLab1 stride preview"
                if self._is_rustlab1_workflow()
                else "stick-plot preview"
            )
            QMessageBox.information(
                self,
                f"{preview_name.capitalize()} required",
                f"Generate and review the {preview_name} before running the analysis.",
            )
            return

        if self._is_rustlab1_workflow():
            self._run_rustlab1_analysis(output_folder)
            return

        settings = self._collect_settings()
        if self.use_custom_mapping_checkbox.isChecked() and not settings.custom_bodypart_mapping:
            QMessageBox.warning(
                self, "No body part mapping", "Select at least one body part mapping or turn off custom mapping."
            )
            return
        self.progress.setValue(0)
        self.progress.set_active(True)
        self.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        animate_button_emphasis(self.preview_button, False)
        animate_button_emphasis(self.run_button, True)
        self.log.clear()
        self.status_label.setText("Running ALMA gait analysis...")
        self.workspace_tabs.setCurrentWidget(self.log_page)
        self.run_button.setEnabled(False)

        analysis_inputs = self._view_sets if self._is_three_view_mode() else self._selected_files
        self._worker = AlmaAnalysisThread(analysis_inputs, output_folder, settings, self._alma_root)
        self._worker.progress_updated.connect(self._update_progress)
        self._worker.log_message.connect(self._append_log)
        self._worker.results_ready.connect(self._output_results_ready)
        self._worker.analysis_completed.connect(self._analysis_completed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()
        self._update_run_state()

    def _run_rustlab1_analysis(self, output_folder: Path) -> None:
        settings = self._collect_rustlab1_settings()
        self.progress.setValue(0)
        self.progress.set_active(True)
        self.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        animate_button_emphasis(self.preview_button, False)
        animate_button_emphasis(self.run_button, True)
        self.log.clear()
        self.status_label.setText("Running standalone RustLab1 analysis...")
        self.workspace_tabs.setCurrentWidget(self.log_page)
        self.run_button.setEnabled(False)

        self._worker = RustLab1AnalysisThread(
            self._view_sets,
            output_folder,
            settings,
            self._alma_root,
        )
        self._worker.progress_updated.connect(self._update_progress)
        self._worker.log_message.connect(self._append_log)
        self._worker.results_ready.connect(self._output_results_ready)
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
            limb_scope=self.limb_scope_combo.currentText(),
            analysis_type=self.analysis_type_combo.currentText(),
            frame_rate=self.frame_rate_spin.value(),
            filter_cutoff=self.filter_cutoff_spin.value(),
            treadmill_speed_cm_s=self.treadmill_speed_spin.value(),
            calibration_method="reference"
            if self.calibration_method_combo.currentText() == "Reference body segment"
            else "manual",
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
            generate_alma_representations=self.alma_representations_checkbox.isChecked(),
            generate_rustlab1_parameters=self.rustlab1_checkbox.isChecked() and self._is_three_view_mode(),
            custom_bodypart_mapping=self._collect_bodypart_mapping(),
            view_bodypart_mapping=self._collect_view_bodypart_mapping(),
            stroke_analysis_enabled=self.stroke_analysis_checkbox.isChecked() and self._is_three_view_mode(),
            stroke_likelihood_threshold=self.likelihood_threshold_spin.value(),
            max_interpolation_gap_frames=0,
            swing_speed_threshold_cm_s=self.stroke_swing_speed_spin.value(),
            minimum_synchronized_cycles=self.stroke_min_cycles_spin.value(),
            view_calibration=(
                {
                    "bottom": {
                        "x_pixels_per_cm": self.bottom_x_pixels_per_cm_spin.value(),
                        "y_pixels_per_cm": self.bottom_y_pixels_per_cm_spin.value(),
                    }
                }
                if self.bottom_x_pixels_per_cm_spin.value() > 0 and self.bottom_y_pixels_per_cm_spin.value() > 0
                else None
            ),
            enabled_parameter_names=self.parameter_selection.enabled_parameter_names(),
        )

    def _collect_rustlab1_settings(self) -> RustLab1StandaloneSettings:
        return RustLab1StandaloneSettings(
            frame_rate=self.frame_rate_spin.value(),
            filter_cutoff=self.filter_cutoff_spin.value(),
            likelihood_threshold=self.rustlab_likelihood_spin.value(),
            stance_speed_threshold_px_frame=self.rustlab_stance_speed_spin.value(),
            minimum_stance_frames=self.rustlab_min_stance_spin.value(),
            minimum_swing_frames=self.rustlab_min_swing_spin.value(),
            reference_paw=RUSTLAB1_PAW_LABELS[self.rustlab_reference_paw_combo.currentText()],
            limb_scope=self.limb_scope_combo.currentText(),
            calibration_method=(
                "reference"
                if self.calibration_method_combo.currentText() == "Reference body segment"
                else "manual"
            ),
            reference_segment=self.reference_segment_combo.currentText().split(" ", 1)[0],
            reference_length_cm=self.reference_length_spin.value(),
            pixels_per_cm=(
                self.pixels_per_cm_spin.value()
                if self.calibration_method_combo.currentText() == "Manual pixel-to-cm ratio"
                else None
            ),
            view_calibration=(
                {
                    "bottom": {
                        "x_pixels_per_cm": self.bottom_x_pixels_per_cm_spin.value(),
                        "y_pixels_per_cm": self.bottom_y_pixels_per_cm_spin.value(),
                    }
                }
                if self.bottom_x_pixels_per_cm_spin.value() > 0
                and self.bottom_y_pixels_per_cm_spin.value() > 0
                else None
            ),
            view_bodypart_mapping=self._collect_view_bodypart_mapping(),
            enabled_parameter_names=self.parameter_selection.enabled_parameter_names(),
            generate_figures=self.rustlab1_checkbox.isChecked(),
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

    def _missing_rustlab1_bodyparts(
        self,
        view_set: AlmaViewCsvSet,
        settings: RustLab1StandaloneSettings,
    ) -> list[str]:
        include_forelimb = settings.limb_scope == "Hindlimb + Forelimb"
        side_labels = ("ankle", "toe", "hip", "iliac crest")
        if include_forelimb:
            side_labels += FORELIMB_SIDE_VIEW_LABELS
        bottom_labels = list(BOTTOM_VIEW_LABELS[:3])
        if include_forelimb:
            bottom_labels.extend(FORELIMB_BOTTOM_VIEW_LABELS)
        reference_label = {
            "d-back-left": "back left",
            "d-back-right": "back right",
            "d-front-left": "front left",
            "d-front-right": "front right",
        }[settings.reference_paw]
        if reference_label not in bottom_labels:
            bottom_labels.append(reference_label)

        missing = []
        view_mapping = settings.view_bodypart_mapping or {}
        for view, csv_path, required_labels in (
            ("left", view_set.left_csv, side_labels),
            ("right", view_set.right_csv, side_labels),
            ("bottom", view_set.bottom_csv, tuple(bottom_labels)),
        ):
            try:
                raw_bodyparts = read_dlc_bodyparts(csv_path)
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

    def _missing_required_bodyparts(self, settings: AlmaSettings) -> list[str]:
        if self._is_three_view_mode():
            view_set = self._selected_view_set()
            if view_set is None:
                return []
            missing: list[str] = []
            view_mapping = settings.view_bodypart_mapping or {}
            include_forelimb = settings.limb_scope == "Hindlimb + Forelimb"
            side_labels = SIDE_VIEW_LABELS + (FORELIMB_SIDE_VIEW_LABELS if include_forelimb else ())
            bottom_labels = BOTTOM_VIEW_LABELS[:3] + (FORELIMB_BOTTOM_VIEW_LABELS if include_forelimb else ())
            for view, csv_path, required_labels in (
                ("left", view_set.left_csv, side_labels),
                ("right", view_set.right_csv, side_labels),
                ("bottom", view_set.bottom_csv, bottom_labels),
            ):
                try:
                    raw_bodyparts = read_dlc_bodyparts(csv_path)
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
        workflow_name = (
            "RustLab1 analysis" if self._is_rustlab1_workflow() else "ALMA gait analysis"
        )
        status_message = message
        if success and self._output_preview_paths:
            status_message += "\nPreview the generated figures and tables below."
        self.status_label.setText(status_message)
        self.progress.set_active(False)
        self.progress.setValue(100 if success else self.progress.value())
        animate_button_emphasis(self.run_button, False)
        if success:
            self.run_button.setIcon(interface_icon("check", theme.PRIMARY_TEXT))
            QMessageBox.information(self, f"{workflow_name} complete", message)
        else:
            self.run_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
            self.workspace_tabs.setCurrentWidget(self.log_page)
            QMessageBox.critical(self, f"{workflow_name} failed", message)

    def _output_results_ready(self, results) -> None:
        output_files = (output_file for result in results for output_file in getattr(result, "output_files", ()))
        self._output_preview_paths = previewable_output_paths(output_files)
        if not self._output_preview_paths:
            self._append_log("No SVG or CSV output previews were available.")
            return
        self.output_preview_view.load_paths(self._output_preview_paths)
        self.preview_stack.setCurrentWidget(self.output_preview_view)
        self.workspace_tabs.setCurrentWidget(self.preview_page)
        self._append_log(f"Loaded {len(self._output_preview_paths)} generated output previews.")

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
            QTabBar#RunwaySettingsSectionRow {
                background: {theme.PANEL};
                border: 0;
            }
            QWidget#RunwayStickySettingsNavigation {
                background: {theme.PANEL};
                border: 0;
                border-bottom: 1px solid {theme.BORDER};
            }
            QTabBar#RunwaySettingsSectionRow::tab {
                background: {theme.PANEL};
                border: 0;
                color: {theme.CONNECTOR};
                font-size: 12px;
                min-height: 30px;
                padding: 0 8px;
            }
            QTabBar#RunwaySettingsSectionRow::tab:hover {
                background: {theme.SOFT};
                color: {theme.TEXT};
            }
            QTabBar#RunwaySettingsSectionRow::tab:selected {
                background: {theme.SURFACE};
                color: {theme.TEXT};
                font-weight: 700;
            }
            QTabBar#RunwaySettingsSectionRow[activeRow="false"]::tab:selected {
                background: {theme.PANEL};
                color: {theme.CONNECTOR};
                font-weight: 400;
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
            QTabWidget#RunwayWorkspaceTabs::pane {
                border: 1px solid {theme.BORDER};
                background: {theme.SURFACE};
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar {
                background: {theme.PANEL};
                border-bottom: 1px solid {theme.BORDER};
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar::tab {
                background: {theme.PANEL};
                color: {theme.CONNECTOR};
                border: 0;
                border-bottom: 3px solid transparent;
                min-width: 120px;
                padding: 8px 12px;
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar::tab:hover {
                background: {theme.SOFT};
                color: {theme.TEXT};
            }
            QTabWidget#RunwayWorkspaceTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
                color: {theme.TEXT};
                border-bottom-color: transparent;
                font-weight: 700;
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
            QSvgWidget#StickPlotSvg {
                background: white;
            }
            QScrollArea#RunwayControlsScroll,
            QScrollArea#RunwayControlsScroll > QWidget,
            QScrollArea#RunwayControlsScroll > QWidget > QWidget {
                border: 0;
                background: {theme.PANEL};
            }
            QWidget#RunwayActionFooter {
                border-top: 1px solid {theme.BORDER};
                background: {theme.PANEL};
            }
            QWidget#GaitParameterReference {
                background: {theme.BACKGROUND};
                background-image: url({theme.BACKGROUND_TEXTURE});
            }
            QLabel#ParameterReferenceTitle {
                color: {theme.TEXT};
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#ParameterReferenceSubtitle {
                color: {theme.CONNECTOR};
                font-size: 13px;
                padding-bottom: 6px;
            }
            QFrame#FigureCreatorIndex,
            QFrame#FigureCreatorDetails {
                background: {theme.SURFACE};
                border: 1px solid {theme.BORDER};
                border-radius: 6px;
            }
            QLabel#FigureCreatorTitle {
                color: {theme.TEXT};
                font-size: 20px;
                font-weight: 700;
                border: 0;
            }
            QLabel#FigureCreatorIntro {
                color: {theme.CONNECTOR};
                font-size: 12px;
                border: 0;
            }
            QLabel#FigureCountLabel {
                color: {theme.CONNECTOR};
                font-size: 11px;
                border: 0;
            }
            QLabel#FigureIndexHeading {
                color: {theme.TEXT};
                font-size: 13px;
                font-weight: 700;
                border: 0;
            }
            QListWidget#FigureCreatorList {
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
                padding: 3px;
            }
            QListWidget#FigureCreatorList::item {
                color: {theme.TEXT};
                padding: 6px 7px;
                border-radius: 3px;
            }
            QListWidget#FigureCreatorList::item:selected {
                background: {theme.PRIMARY};
                color: white;
            }
            QSvgWidget#FigureCreatorPreview {
                background: white;
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
            }
            QLabel#FigureSourceBadge {
                color: {theme.PRIMARY};
                background: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 9px;
                font-size: 10px;
                font-weight: 700;
                padding: 2px 8px;
            }
            QLabel#FigurePreviewNote {
                color: {theme.CONNECTOR};
                font-size: 11px;
                border: 0;
            }
            QScrollArea#FigureExplanationScroll,
            QScrollArea#FigureExplanationScroll > QWidget,
            QScrollArea#FigureExplanationScroll > QWidget > QWidget {
                background: transparent;
                border: 0;
            }
            QLabel#FigureExplanationTitle {
                color: {theme.TEXT};
                font-size: 16px;
                font-weight: 700;
                border: 0;
            }
            QLabel#FigureDetailHeading {
                color: {theme.TEXT};
                font-size: 11px;
                font-weight: 700;
                border: 0;
            }
            QLabel#FigureDetailValue {
                color: {theme.CONNECTOR};
                font-size: 11px;
                border: 0;
            }
            QTreeWidget#GaitParameterTree {
                background: {theme.SURFACE};
                alternate-background-color: {theme.PANEL};
                border: 1px solid {theme.BORDER};
                border-radius: 4px;
            }
            QFrame#ParameterDetails {
                background: {theme.SURFACE};
                border: 1px solid {theme.BORDER};
                border-radius: 5px;
            }
            QLabel#ParameterName {
                color: {theme.TEXT};
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#ParameterDetailHeading {
                color: {theme.TEXT};
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#ParameterDetailValue {
                color: {theme.CONNECTOR};
                font-size: 13px;
            }
            QLabel#ParameterCalculationFocus {
                color: {theme.TEXT};
                font-size: 15px;
                font-weight: 600;
                padding: 6px 0 10px 0;
            }
            QTreeWidget#GaitParameterSelectionTree {
                background: {theme.SURFACE};
                alternate-background-color: {theme.PANEL};
                border: 1px solid {theme.BORDER};
            }
            """,
            )
        )
        icon_specs = (
            (self.add_file_button, "plus", theme.TEXT),
            (self.add_folder_button, "folder", theme.TEXT),
            (self.clear_files_button, "clear", theme.STATUS_ERROR),
            (self.output_folder_button, "folder", theme.TEXT),
            (self.load_fps_button, "upload", theme.TEXT),
            (self.import_calibration_map_button, "upload", theme.TEXT),
            (self.export_manifest_button, "download", theme.TEXT),
            (self.preview_button, "eye", theme.TEXT),
            (self.run_button, "play", theme.PRIMARY_TEXT),
            (self.figure_reference_button, "chart", theme.TEXT),
            (self.parameter_reference_button, "document", theme.TEXT),
            (self.documentation_back_button, "arrow-left", theme.TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))


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

    def profile_analysis_manifest_path(self) -> Path | None:
        return self.kinematics_widget.profile_analysis_manifest_path()

    def export_profile_preset(self, output_dir: Path) -> Path:
        return self.kinematics_widget.export_profile_preset(output_dir)

    def profile_calibration_map_path(self) -> Path | None:
        return self.kinematics_widget.profile_calibration_map_path()


def _double_spin(minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    spin.setDecimals(decimals)
    return spin


_auto_bodypart_label = auto_bodypart_label
