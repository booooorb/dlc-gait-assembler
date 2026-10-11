"""Present selected session-summary files and their cohort inclusion controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QGroupBox, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout


class CohortInputPanel:
    """CohortInputPanel operates on its explicitly supplied PcaRandomForestWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_files(self) -> None:
        (filenames, _) = QFileDialog.getOpenFileNames(
            self.view,
            "Select synchronized session summaries",
            str(self.view.workspace.root),
            "Session summaries (*_session_summary.csv);;CSV files (*.csv)",
        )
        for filename in filenames:
            path = Path(filename).expanduser().resolve()
            if path not in self.view._files:
                self.view._files.append(path)
                self.view.file_list.addItem(str(path))
        self.view.controller._update_run_state()

    def _clear_files(self) -> None:
        self.view._files.clear()
        self.view.file_list.clear()
        self.view.controller._update_run_state()


def build_cohort_inputs(self, controls_layout):
    input_box = QGroupBox("Animal-session summaries")
    input_layout = QVBoxLayout(input_box)
    self.file_list = QListWidget()
    self.file_list.setMinimumHeight(180)
    input_layout.addWidget(self.file_list)
    choose_button = QPushButton("Add session-summary CSVs")
    clear_button = QPushButton("Clear")
    choose_button.clicked.connect(self.inputs._choose_files)
    clear_button.clicked.connect(self.inputs._clear_files)
    input_buttons = QHBoxLayout()
    input_buttons.addWidget(choose_button, 1)
    input_buttons.addWidget(clear_button)
    input_layout.addLayout(input_buttons)
    controls_layout.addWidget(input_box)
