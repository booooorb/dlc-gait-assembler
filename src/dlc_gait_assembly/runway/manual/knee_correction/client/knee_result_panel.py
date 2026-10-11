"""Present corrected coordinate files and marker-level reconstruction reports."""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout

from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar
from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    fixed_width_font as _dependency_theme_fixed_width_font,
)


def build_knee_outputs(self, left_column, right_column, root, workspace_row):
    output_box = QGroupBox("Output")
    output_layout = QVBoxLayout(output_box)
    output_line = QHBoxLayout()
    self.output_folder_edit = QLineEdit(str(self._default_output_folder()))
    self.output_folder_edit.setCursorPosition(0)
    self.output_folder_button = QPushButton("Choose folder")
    output_line.addWidget(self.output_folder_edit, 1)
    output_line.addWidget(self.output_folder_button)
    output_layout.addLayout(output_line)
    output_note = QLabel(
        "Each pair produces *_knee_corrected.csv and *_knee_corrected.h5. Original files are not modified."
    )
    output_note.setObjectName("MutedLabel")
    output_note.setWordWrap(True)
    output_layout.addWidget(output_note)
    output_layout.addStretch(1)
    right_column.addWidget(output_box)
    workspace_row.addLayout(left_column, 3)
    workspace_row.addLayout(right_column, 2)
    root.addLayout(workspace_row, 1)
    self.progress = DynamicProgressBar(accent_role="tool_3")
    self.progress.setRange(0, 100)
    root.addWidget(self.progress)
    self.log = QPlainTextEdit()
    self.log.setReadOnly(True)
    self.log.setMaximumHeight(58)
    self.log.setFont(_dependency_theme_fixed_width_font())
    root.addWidget(self.log)
    action_row = QHBoxLayout()
    return action_row
