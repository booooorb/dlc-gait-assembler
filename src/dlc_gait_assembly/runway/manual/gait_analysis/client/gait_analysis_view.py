"""Assemble the input, settings, preview/results, documentation, and run-log surfaces."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_reference_dialog import (
    GaitParameterReferenceWidget,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_controller import GaitAnalysisController
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_styles import GaitAnalysisStyle
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_worker import (
    AlmaAnalysisThread,
    RustLab1AnalysisThread,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_client_state import GaitClientState
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_preview_worker import (
    RustLab1PreviewThread,
    StickPlotPreviewThread,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_analysis_settings_panel import (
    build_gait_movement_settings,
    build_gait_stride_detection,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_calibration_panel import (
    GaitCalibrationPanel,
    build_gait_calibration,
    build_gait_timing,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_filter_panel import (
    GaitFilterPanel,
    build_gait_filters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_input_panel import (
    GaitInputPanel,
    build_gait_inputs,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_mapping_panel import (
    GaitMappingPanel,
    build_gait_marker_mapping,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_output_panel import (
    GaitOutputPanel,
    build_gait_output_settings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_parameter_panel import (
    GaitParameterSelectionWidget,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_setup_panel import (
    ALMA_WORKFLOW_LABEL,
    RUSTLAB1_WORKFLOW_LABEL,
    GaitSetupPanel,
    build_gait_setup,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_stickplot_panel import build_gait_preview_pages
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar
from dlc_gait_assembly.shared.client.qt_sliding_tabs import SlidingTabBar, install_sliding_tab_bar


class AlmaKinematicsWidget(QWidget):
    def __init__(self, *, preview, analysis, workspace):
        super().__init__()
        self.workspace = workspace
        self.analysis = analysis
        self.state = GaitClientState()
        self.preview = preview
        self.controller = GaitAnalysisController(self)
        self.inputs = GaitInputPanel(self)
        self.outputs = GaitOutputPanel(self)
        self.mapping = GaitMappingPanel(self)
        self.setup = GaitSetupPanel(self)
        self.calibration = GaitCalibrationPanel(self)
        self.filters = GaitFilterPanel(self)
        self.styling = GaitAnalysisStyle(self)
        self.setObjectName("GaitAnalysisWidget")
        self._project_root = self.workspace.root
        self._worker: AlmaAnalysisThread | RustLab1AnalysisThread | None = None
        self._preview_worker: StickPlotPreviewThread | RustLab1PreviewThread | None = None
        self._defaults = self.analysis.defaults
        self._bodypart_combos: dict[str, QComboBox] = {}
        self._build_ui()
        self.controller._install_interactions()
        self.controller._connect_signals()
        self.styling._apply_style()
        self.setup._update_workflow()
        self.setup._update_input_mode()
        self.setup._update_limb_scope()
        self.setup._update_analysis_mode()
        self.calibration._update_calibration_method()
        self.filters._update_rustlab_filter_range()
        self.filters._update_rustlab_speed_range()
        self.controller._update_run_state()

    def can_close(self, parent=None) -> bool:
        analysis_running = self._worker is not None and self._worker.isRunning()
        preview_running = self._preview_worker is not None and self._preview_worker.isRunning()
        if analysis_running or preview_running:
            workflow = "RustLab1" if self.setup._is_rustlab1_workflow() else "gait"
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
        file_box = build_gait_inputs(self)
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
            self._defaults.enabled_parameter_names, multiside=initial_multiside
        )
        settings_tabs.addTab(setup_tab, "Setup")
        settings_tabs.addTab(calibration_tab, "Calibration")
        settings_tabs.addTab(analysis_tab, "Analysis")
        settings_tabs.addTab(filters_tab, "Filters")
        settings_tabs.addTab(mapping_tab, "Mapping")
        settings_tabs.addTab(parameters_tab, "Parameters")
        settings_tabs.addTab(output_tab, "Output")
        self.stride_detection_tab = QWidget()
        stride_layout = QVBoxLayout(self.stride_detection_tab)
        stride_layout.setContentsMargins(6, 6, 6, 6)
        settings_tabs.addTab(self.stride_detection_tab, "Stride detection")
        self.settings_navigation_indices = ((0, 1, 7, 3), (2, 4, 5, 6))
        self.settings_section_rows = (SlidingTabBar(theme.TOOL_3), SlidingTabBar(theme.TOOL_3))
        for row, indices in zip(self.settings_section_rows, self.settings_navigation_indices, strict=True):
            for index in indices:
                row.addTab(settings_tabs.tabText(index))
            row.tabBarClicked.connect(lambda local, indices=indices: settings_tabs.setCurrentIndex(indices[local]))

        def sync_settings_rows(index: int) -> None:
            for row, indices in zip(self.settings_section_rows, self.settings_navigation_indices, strict=True):
                row.set_active_row(index in indices)
                row.blockSignals(True)
                row.setCurrentIndex(indices.index(index) if index in indices else -1)
                row.blockSignals(False)

        settings_tabs.currentChanged.connect(sync_settings_rows)
        sync_settings_rows(0)
        self.mapping_tab = mapping_tab
        self.setup_tab = setup_tab
        self.calibration_tab = calibration_tab
        self.parameter_selection = parameters_tab
        build_gait_setup(self, initial_multiside, setup_tab_layout)
        build_gait_stride_detection(self, stride_layout)
        stride_layout.addStretch(1)
        build_gait_calibration(self, calibration_tab_layout, setup_tab_layout)
        build_gait_timing(self, setup_tab_layout)
        build_gait_movement_settings(self, analysis_tab_layout)
        build_gait_filters(self, analysis_tab_layout, filters_tab_layout)
        build_gait_output_settings(self, output_tab_layout)
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
        build_gait_preview_pages(self)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(280)
        self.log.setPlaceholderText("Preview and analysis messages will appear here.")
        self.log_page = QWidget()
        log_layout = QVBoxLayout(self.log_page)
        log_layout.setContentsMargins(8, 10, 8, 8)
        log_layout.addWidget(self.log, 1)
        self.workspace_tabs.addTab(self.log_page, "3. Run log")
        build_gait_marker_mapping(self, mapping_tab_layout)
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
        manifest_actions = QHBoxLayout()
        self.import_manifest_button = QPushButton("Import analysis manifest")
        set_tooltip(
            self.import_manifest_button, "Load saved gait-analysis settings from an analysis manifest JSON file."
        )
        manifest_actions.addWidget(self.import_manifest_button)
        manifest_actions.addWidget(self.export_manifest_button)
        action_layout.addLayout(manifest_actions)
        action_layout.addWidget(self.preview_button)
        action_layout.addWidget(self.run_button)
        left_column_layout.addWidget(action_footer, 0)
        splitter.addWidget(left_column)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 780])
        self.parameter_reference = GaitParameterReferenceWidget(reader=self.analysis.results)
        self.parameter_reference.set_multiside(initial_multiside)
        self.workspace_stack.addWidget(self.parameter_reference)

    def profile_analysis_manifest_path(self) -> Path | None:
        """Return the analysis manifest most recently exported in this workspace."""
        return self.state.profile_analysis_manifest_path

    def settings_snapshot(self):
        return self.setup._collect_settings()

    def profile_calibration_map_path(self) -> Path | None:
        return self.state.calibration_map_path

    def _default_output_root(self) -> Path:
        return self.workspace.manual / "gait_analysis"

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()

    def release_resources(self) -> None:
        """Release completed workers and cached preview artifacts when the page closes."""
        workers = (self._worker, self._preview_worker) if hasattr(self, "_preview_worker") else (self._worker,)
        for worker in workers:
            if worker is not None:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.wait()
                worker.deleteLater()
        self._worker = None
        self._preview_worker = None
        self.state.preview_svg_data = None
        self.state.output_preview_paths = ()


class GaitAnalysisWidget(QWidget):
    """Primary gait-analysis workspace, opening directly to Runway."""

    def __init__(self, *, preview, analysis, workspace):
        super().__init__()
        self.workspace = workspace
        self.analysis = analysis
        self.preview = preview
        self.setObjectName("GaitAnalysisContainer")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.kinematics_widget = AlmaKinematicsWidget(
            preview=self.preview, analysis=self.analysis, workspace=self.workspace
        )
        root.addWidget(self.kinematics_widget)

    def can_close(self, parent=None) -> bool:
        return self.kinematics_widget.can_close(parent or self)

    def release_resources(self) -> None:
        self.kinematics_widget.release_resources()

    def apply_theme(self) -> None:
        self.kinematics_widget.apply_theme()

    def profile_analysis_manifest_path(self) -> Path | None:
        return self.kinematics_widget.profile_analysis_manifest_path()

    def settings_snapshot(self):
        return self.kinematics_widget.settings_snapshot()

    def profile_calibration_map_path(self) -> Path | None:
        return self.kinematics_widget.profile_calibration_map_path()
