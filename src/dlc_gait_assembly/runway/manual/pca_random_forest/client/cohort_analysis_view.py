"""Assemble cohort inputs, selected analysis options, execution controls, and results."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QSizePolicy, QSplitter, QTextEdit, QVBoxLayout, QWidget

from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_controller import CohortAnalysisController
from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_options import build_cohort_options
from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_styles import CohortAnalysisStyle
from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_worker import CohortAnalysisThread
from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_input_panel import (
    CohortInputPanel,
    build_cohort_inputs,
)


class PcaRandomForestWidget(QWidget):
    def __init__(self, *, outputs, workspace):
        super().__init__()
        self.workspace = workspace
        self.outputs = outputs
        self.controller = CohortAnalysisController(self)
        self.inputs = CohortInputPanel(self)
        self.styling = CohortAnalysisStyle(self)
        self.setObjectName("PcaRandomForestWidget")
        self._project_root = self.workspace.root
        self._files: list[Path] = []
        self._worker: CohortAnalysisThread | None = None
        self._build_ui()
        self.styling._apply_style()
        self.controller._update_run_state()

    def can_close(self, parent=None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                parent or self,
                "Cohort analysis is running",
                "Wait for the current PCA, Random Forest, or mixed-effects analysis to finish.",
            )
            return False
        return True

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setObjectName("WorkspaceHeader")
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 14)
        header_layout.setSpacing(5)
        title = QLabel("PCA, random forest, and repeated-measures analysis")
        title.setObjectName("TitleLabel")
        header_layout.addWidget(title)
        subtitle = QLabel(
            "Analyze synchronized *_session_summary.csv files. Splits are grouped by animal, and mixed-effects models use animal-level repeated measurements."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("MutedLabel")
        header_layout.addWidget(subtitle)
        root.addWidget(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("CohortAnalysisSplitter")
        splitter.setChildrenCollapsible(False)
        self.analysis_splitter = splitter
        root.addWidget(splitter, 1)
        controls = QWidget()
        controls.setObjectName("WorkspaceSidebar")
        controls.setMinimumWidth(390)
        controls.setMaximumWidth(520)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(16, 16, 16, 16)
        controls_layout.setSpacing(12)
        build_cohort_inputs(self, controls_layout)
        build_cohort_options(self, controls, controls_layout, splitter)
        results = QWidget()
        results.setObjectName("WorkspaceCanvas")
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(18, 16, 18, 18)
        results_layout.setSpacing(10)
        results_title = QLabel("Analysis activity and results")
        results_title.setObjectName("PreviewTitle")
        results_layout.addWidget(results_title)
        self.status_label = QLabel("Add synchronized session summaries.")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        results_layout.addWidget(self.status_label)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumSize(420, 280)
        self.log.setPlaceholderText("Run messages and generated output paths will appear here.")
        results_layout.addWidget(self.log, 1)
        splitter.addWidget(results)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([470, 760])

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
