"""Collect export location, quality, and encoding-preset choices."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class ExportSettingsDialog(QDialog):
    def __init__(self, video_count: int, default_output_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel(f"Process {video_count} video(s)")
        title.setObjectName("PreviewTitle")
        layout.addWidget(title)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        path_row = QHBoxLayout()
        self.output_root_edit = QLineEdit(str(default_output_root))
        self.output_root_edit.setMinimumWidth(280)
        set_tooltip(self.output_root_edit, "Folder where processed videos and session documents will be saved.")
        browse_button = QPushButton("Browse")
        set_tooltip(browse_button, "Choose the processed-video output folder.")
        browse_button.clicked.connect(self._browse_output_root)
        path_row.addWidget(self.output_root_edit, 1)
        path_row.addWidget(browse_button)
        form.addRow("Output folder", path_row)
        self.codec_combo = QComboBox()
        self.codec_combo.addItem("H.264 / MP4", "h264_mp4")
        set_tooltip(self.codec_combo, "Output container and video codec.")
        form.addRow("Format", self.codec_combo)
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("High detail (CRF 18)", (18, "slow"))
        self.quality_combo.addItem("Maximum detail (CRF 16)", (16, "slow"))
        self.quality_combo.addItem("Balanced (CRF 20)", (20, "medium"))
        set_tooltip(self.quality_combo, "Video quality and encode-speed preset.")
        form.addRow("Quality", self.quality_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Process files")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def output_root(self) -> Path:
        return Path(self.output_root_edit.text()).expanduser().resolve()

    def crf(self) -> int:
        (crf, _preset) = self.quality_combo.currentData()
        return int(crf)

    def preset(self) -> str:
        (_crf, preset) = self.quality_combo.currentData()
        return str(preset)

    def accept(self) -> None:
        if not self.output_root_edit.text().strip():
            QMessageBox.warning(self, "Output folder required", "Choose an output folder before processing.")
            return
        super().accept()

    def _browse_output_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose output folder", self.output_root_edit.text() or str(Path.home())
        )
        if directory:
            self.output_root_edit.setText(directory)
