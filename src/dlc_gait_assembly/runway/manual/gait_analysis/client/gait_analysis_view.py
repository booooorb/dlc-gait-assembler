"""Assemble the input, settings, preview/results, documentation, and run-log surfaces."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
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
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_settings_navigation import GaitSettingsNavigation
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_setup_panel import (
    ALMA_SIDE_RUST_BOTTOM_LABEL,
    ALMA_WORKFLOW_LABEL,
    RUSTLAB1_WORKFLOW_LABEL,
    GaitSetupPanel,
    build_gait_setup,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_stickplot_panel import build_gait_preview_pages
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar
from dlc_gait_assembly.shared.client.qt_sliding_tabs import install_sliding_tab_bar


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
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(12)
        title = QLabel("Gait analysis")
        title.setObjectName("TitleLabel")
        header_layout.addWidget(title)
        self.workspace_title = title
        workflow_label = QLabel("Workflow")
        workflow_label.setObjectName("MutedLabel")
        header_layout.addWidget(workflow_label)
        self.workflow_combo = QComboBox()
        self.workflow_combo.setObjectName("GaitWorkflowSelector")
        self.workflow_combo.addItems((ALMA_WORKFLOW_LABEL, ALMA_SIDE_RUST_BOTTOM_LABEL, RUSTLAB1_WORKFLOW_LABEL))
        self.workflow_combo.setAccessibleName("Gait analysis workflow")
        set_tooltip(
            self.workflow_combo,
            "ALMA exports native side strides. ALMA side + rust bottom adds 20 underside R measures and "
            "session ALMA means and standard deviations in RustLab CSV format. Standalone RustLab1 remains available.",
        )
        header_layout.addWidget(self.workflow_combo)
        header_layout.addStretch(1)
        self.help_button = QToolButton()
        self.help_button.setText("Help")
        self.help_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        help_menu = QMenu(self.help_button)
        self.figure_reference_action = QAction("Figure guide", self)
        self.parameter_reference_action = QAction("Parameter guide", self)
        help_menu.addAction(self.figure_reference_action)
        help_menu.addAction(self.parameter_reference_action)
        self.help_button.setMenu(help_menu)
        header_layout.addWidget(self.help_button)
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
        splitter.setHandleWidth(8)
        splitter.setAccessibleName("Resize gait settings and results")
        self.workspace_splitter = splitter
        self.workspace_stack.addWidget(splitter)
        left_panel = QWidget()
        left_panel.setObjectName("WorkspaceSidebar")
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
        settings_tabs.addTab(mapping_tab, "Labels")
        settings_tabs.addTab(parameters_tab, "Parameters")
        settings_tabs.addTab(output_tab, "Output")
        self.stride_detection_tab = QWidget()
        stride_layout = QVBoxLayout(self.stride_detection_tab)
        stride_layout.setContentsMargins(6, 6, 6, 6)
        settings_tabs.addTab(self.stride_detection_tab, "Stride detection")
        self.settings_navigation = GaitSettingsNavigation(settings_tabs)
        self.settings_navigation_indices = self.settings_navigation.section_indices
        self.settings_section_rows = self.settings_navigation.rows
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
        self.import_manifest_button = QPushButton("Load settings…")
        set_tooltip(self.import_manifest_button, "Load saved gait-analysis settings from a JSON manifest.")
        self.export_manifest_button = QPushButton("Save settings…")
        set_tooltip(
            self.export_manifest_button,
            "Save the current settings as a JSON manifest for reuse or an automatic profile.",
            "Ctrl+Shift+E",
        )
        build_gait_output_settings(self, output_tab_layout)
        left_layout.addWidget(self.settings_navigation)
        left_layout.addWidget(settings_tabs, 1)
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
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        self.progress = DynamicProgressBar(accent_role="tool_1")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
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
        inputs_layout.addWidget(file_box, 1)
        self.workspace_tabs.addTab(self.inputs_page, "Files")
        build_gait_preview_pages(self)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(280)
        self.log.setPlaceholderText("Preview and analysis messages will appear here.")
        self.log_page = QWidget()
        log_layout = QVBoxLayout(self.log_page)
        log_layout.setContentsMargins(8, 10, 8, 8)
        log_layout.addWidget(self.log, 1)
        self.workspace_tabs.addTab(self.log_page, "Log")
        build_gait_marker_mapping(self, mapping_tab_layout)
        self.settings_scrolls = {}
        for index in range(settings_tabs.count()):
            page = settings_tabs.widget(index)
            content = QWidget()
            content.setLayout(page.layout())
            for label in content.findChildren(QLabel):
                label.setWordWrap(True)
            for combo in content.findChildren(QComboBox):
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                combo.setMinimumContentsLength(8)
            scroll = QScrollArea()
            scroll.setObjectName("RunwayControlsScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.addWidget(scroll)
            self.settings_scrolls[page] = scroll
        left_layout.removeWidget(self.preview_button)
        left_layout.removeWidget(self.run_button)
        left_column = QWidget()
        left_column.setObjectName("WorkspaceSidebar")
        left_column.setMinimumWidth(380)
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(0)
        left_layout.removeWidget(self.settings_navigation)
        left_column_layout.addWidget(self.settings_navigation, 0)
        left_column_layout.addWidget(left_panel, 1)
        action_footer = QWidget()
        action_footer.setObjectName("RunwayActionFooter")
        action_layout = QVBoxLayout(action_footer)
        action_layout.setContentsMargins(16, 8, 16, 16)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.preview_button)
        action_layout.addWidget(self.run_button)
        left_column_layout.addWidget(action_footer, 0)
        splitter.addWidget(left_column)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 860])
        self.parameter_reference = GaitParameterReferenceWidget(reader=self.analysis.results)
        self.parameter_reference.set_multiside(initial_multiside)
        self.workspace_stack.addWidget(self.parameter_reference)

    def profile_analysis_manifest_path(self) -> Path | None:
        """Return the analysis manifest most recently exported in this workspace."""
        return self.state.profile_analysis_manifest_path

    @property
    def controls_scroll(self) -> QScrollArea:
        return self.settings_scrolls[self.settings_tabs.currentWidget()]

    def settings_snapshot(self):
        return self.setup._collect_settings()

    def apply_profile_settings(self, settings):
        from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_manifest_import import (
            apply_manifest_settings,
        )

        apply_manifest_settings(self, settings)

    def profile_calibration_map_path(self) -> Path | None:
        return self.state.calibration_map_path if self.calibration_method_combo.currentData() == "map" else None

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
