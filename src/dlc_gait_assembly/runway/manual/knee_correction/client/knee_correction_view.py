"""Assemble paired inputs, knee settings, coordinate preview, and execution controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_controller import KneeCorrectionController
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_styles import KneeCorrectionStyle
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_worker import KneeCorrectionThread
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_editor_state import KneeEditorState
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_input_panel import KneeInputPanel, build_knee_inputs
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_preview_canvas import build_knee_preview
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_preview_controller import KneePreviewController
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_result_panel import build_knee_outputs
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_settings_panel import build_knee_settings
from dlc_gait_assembly.shared.business.media_access_contracts import MediaAccessPort

try:
    import cv2
except ImportError:
    cv2 = None


class KneeCorrectionWidget(QWidget):
    def __init__(self, *, use_cases, media_access: MediaAccessPort, workspace):
        super().__init__()
        self.setProperty("elevateGroupSurfaces", True)
        self.workspace = workspace
        self.state = KneeEditorState()
        self.media_access = media_access
        self.use_cases = use_cases
        self.controller = KneeCorrectionController(self)
        self.inputs = KneeInputPanel(self)
        self.preview_controller = KneePreviewController(self)
        self.styling = KneeCorrectionStyle(self)
        self.setObjectName("KneeCorrectionWidget")
        self._project_root = self.workspace.root
        self._worker: KneeCorrectionThread | None = None
        self._preview_static_image: QImage | None = None
        self._preview_capture = None
        self._build_ui()
        self.controller._connect_signals()
        self.styling._apply_style()
        self.inputs._refresh_pairs()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        title = QLabel("Knee correction")
        title.setObjectName("TitleLabel")
        root.addWidget(title)
        files_box = build_knee_inputs(self)
        (left_column, right_column, workspace_row) = build_knee_preview(self, files_box)
        build_knee_settings(self, left_column)
        action_row = build_knee_outputs(self, left_column, right_column, root, workspace_row)
        self.status_label = QLabel("Add matching CSV, H5, and video files.")
        self.status_label.setObjectName("PreviewTitle")
        action_row.addWidget(self.status_label, 1)
        self.export_manifest_button = QPushButton("Export knee manifest")
        self.export_manifest_button.setToolTip(
            "Export the current knee lengths, labels, confidence cutoff, direction, and calibration scale."
        )
        action_row.addWidget(self.export_manifest_button)
        self.run_button = QPushButton("Correct knee labels")
        self.run_button.setObjectName("PrimaryButton")
        action_row.addWidget(self.run_button)
        root.addLayout(action_row)

    def profile_knee_manifest_path(self) -> Path | None:
        """Return the knee manifest most recently exported in this workspace."""
        return self.state.profile_knee_manifest_path

    def profile_calibration_map_path(self) -> Path | None:
        return self.state.calibration_map_path

    def settings_snapshot(self):
        return self.controller._settings() if self.state.pixels_per_cm is not None else None

    def can_close(self, parent=None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                parent or self,
                "Knee correction is running",
                "Wait for the paired label files to finish before leaving this tool.",
            )
            return False
        return True

    def release_resources(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait()
        self.preview_controller._release_preview_capture()

    def _default_output_folder(self) -> Path:
        return self.workspace.manual / "knee_correction"

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()
