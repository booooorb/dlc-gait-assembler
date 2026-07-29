from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.interaction import set_tooltip
from dlc_gait_assembly.services.pipeline.stroke_analysis import run_stroke_cohort_analysis
from dlc_gait_assembly.services.project_paths import find_project_root


class _CohortAnalysisThread(QThread):
    completed = Signal(bool, str)
    log_message = Signal(str)

    def __init__(self, files, output_folder, run_pca, run_random_forest, run_mixed_effects):
        super().__init__()
        self._files = tuple(files)
        self._output_folder = Path(output_folder)
        self._run_pca = run_pca
        self._run_random_forest = run_random_forest
        self._run_mixed_effects = run_mixed_effects

    def run(self) -> None:
        try:
            result = run_stroke_cohort_analysis(
                self._files,
                self._output_folder,
                run_pca=self._run_pca,
                run_random_forest=self._run_random_forest,
                run_mixed_effects=self._run_mixed_effects,
            )
            for message in result.messages:
                self.log_message.emit(message)
            for path in result.output_files:
                self.log_message.emit(str(path))
            self.completed.emit(True, f"Analysis complete. Results saved to:\n{self._output_folder}")
        except Exception as exc:
            self.completed.emit(False, str(exc))


class PcaRandomForestWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("PcaRandomForestWidget")
        self._project_root = find_project_root(__file__)
        self._files: list[Path] = []
        self._worker: _CohortAnalysisThread | None = None
        self._build_ui()
        self._apply_style()
        self._update_run_state()

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
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(10)
        title = QLabel("PCA, grouped random forest, and repeated-measures analysis")
        title.setObjectName("TitleLabel")
        root.addWidget(title)
        subtitle = QLabel(
            "Analyze synchronized *_session_summary.csv files. Splits are grouped by animal, "
            "and mixed-effects models use animal-level repeated measurements."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("MutedLabel")
        root.addWidget(subtitle)

        input_box = QGroupBox("Animal-session summaries")
        input_layout = QVBoxLayout(input_box)
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(130)
        input_layout.addWidget(self.file_list)
        choose_button = QPushButton("Add session-summary CSVs")
        clear_button = QPushButton("Clear")
        choose_button.clicked.connect(self._choose_files)
        clear_button.clicked.connect(self._clear_files)
        input_layout.addWidget(choose_button)
        input_layout.addWidget(clear_button)
        root.addWidget(input_box)

        settings_box = QGroupBox("Analysis")
        settings_layout = QGridLayout(settings_box)
        self.pca_checkbox = QCheckBox("PCA on animal-session summaries")
        self.pca_checkbox.setChecked(True)
        self.random_forest_checkbox = QCheckBox("Animal-grouped Random Forest")
        self.random_forest_checkbox.setChecked(True)
        self.mixed_effects_checkbox = QCheckBox("Mixed-effects primary-outcome models")
        self.mixed_effects_checkbox.setChecked(True)
        self.output_edit = QLineEdit(
            str(self._project_root / "outputs" / "stroke_cohort_analysis")
        )
        output_button = QPushButton("Browse")
        output_button.clicked.connect(self._choose_output)
        settings_layout.addWidget(self.pca_checkbox, 0, 0, 1, 2)
        settings_layout.addWidget(self.random_forest_checkbox, 1, 0, 1, 2)
        settings_layout.addWidget(self.mixed_effects_checkbox, 2, 0, 1, 2)
        settings_layout.addWidget(QLabel("Output folder"), 3, 0)
        settings_layout.addWidget(self.output_edit, 3, 1)
        settings_layout.addWidget(output_button, 3, 2)
        root.addWidget(settings_box)

        self.run_button = QPushButton("Run cohort analysis")
        self.run_button.clicked.connect(self._run_analysis)
        set_tooltip(
            self.run_button,
            "Run redundancy control, PCA, grouped Random Forest, and repeated-measures models.",
        )
        root.addWidget(self.run_button)
        self.status_label = QLabel("Add synchronized session summaries.")
        self.status_label.setObjectName("StatusLabel")
        root.addWidget(self.status_label)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        root.addWidget(self.log, 1)

    def _choose_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Select synchronized session summaries",
            str(self._project_root / "outputs"),
            "Session summaries (*_session_summary.csv);;CSV files (*.csv)",
        )
        for filename in filenames:
            path = Path(filename).expanduser().resolve()
            if path not in self._files:
                self._files.append(path)
                self.file_list.addItem(str(path))
        self._update_run_state()

    def _clear_files(self) -> None:
        self._files.clear()
        self.file_list.clear()
        self._update_run_state()

    def _choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select cohort-analysis output folder",
            self.output_edit.text(),
        )
        if selected:
            self.output_edit.setText(selected)

    def _run_analysis(self) -> None:
        if not self._files:
            return
        if not any(
            (
                self.pca_checkbox.isChecked(),
                self.random_forest_checkbox.isChecked(),
                self.mixed_effects_checkbox.isChecked(),
            )
        ):
            QMessageBox.warning(self, "No analysis selected", "Select at least one analysis.")
            return
        output_folder = Path(self.output_edit.text()).expanduser().resolve()
        self.log.clear()
        self.status_label.setText("Running animal-grouped cohort analysis...")
        self.run_button.setEnabled(False)
        self._worker = _CohortAnalysisThread(
            self._files,
            output_folder,
            self.pca_checkbox.isChecked(),
            self.random_forest_checkbox.isChecked(),
            self.mixed_effects_checkbox.isChecked(),
        )
        self._worker.log_message.connect(self.log.append)
        self._worker.completed.connect(self._analysis_completed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _analysis_completed(self, success: bool, message: str) -> None:
        self.status_label.setText("Analysis complete." if success else "Analysis failed.")
        if success:
            QMessageBox.information(self, "Cohort analysis complete", message)
        else:
            self.log.append(message)
            QMessageBox.critical(self, "Cohort analysis failed", message)

    def _worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._update_run_state()

    def _update_run_state(self) -> None:
        running = self._worker is not None and self._worker.isRunning()
        self.run_button.setEnabled(bool(self._files) and not running)
        if not running and self._files:
            self.status_label.setText(
                f"Ready: {len(self._files)} animal-session summary file(s)."
            )

    def _apply_style(self) -> None:
        self.setStyleSheet(theme.workspace_stylesheet("PcaRandomForestWidget"))
