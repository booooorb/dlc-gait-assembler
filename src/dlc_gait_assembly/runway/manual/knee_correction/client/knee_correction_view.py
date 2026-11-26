"""Assemble paired inputs, knee settings, coordinate preview, and execution controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
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
from dlc_gait_assembly.shared.client.qt_sliding_tabs import install_sliding_tab_bar

try:
    import cv2
except ImportError:
    cv2 = None


class KneeCorrectionWorkspace(QWidget):
    def __init__(self, *, use_cases, media_access: MediaAccessPort, workspace):
        super().__init__()
        self.setProperty("elevateGroupSurfaces", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Knee correction")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        self.side_tabs = QTabWidget()
        self.side_tabs.setAccessibleName("Knee correction side")
        self.side_tabs.setDocumentMode(True)
        install_sliding_tab_bar(self.side_tabs, theme.TOOL_3).setExpanding(False)
        self.editors = {}
        for side in ("left", "right"):
            editor = KneeCorrectionWidget(side=side, use_cases=use_cases, media_access=media_access, workspace=workspace)
            self.editors[side] = editor
            editor.correction_running.connect(self.side_tabs.tabBar().setDisabled)
            self.side_tabs.addTab(editor, side.capitalize())
        layout.addWidget(self.side_tabs, 1)

    @property
    def active_editor(self) -> KneeCorrectionWidget:
        return self.side_tabs.currentWidget()

    def can_close(self, parent=None) -> bool:
        return all(editor.can_close(parent or self) for editor in self.editors.values())

    def release_resources(self) -> None:
        for editor in self.editors.values():
            editor.release_resources()

    def apply_theme(self) -> None:
        for editor in self.editors.values():
            editor.apply_theme()


class KneeCorrectionWidget(QWidget):
    correction_running = Signal(bool)

    def __init__(self, *, use_cases, media_access: MediaAccessPort, workspace, side: str | None = None):
        super().__init__()
        self.setProperty("elevateGroupSurfaces", True)
        self.side = side
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
        root.setSpacing(8)
        if self.side is None:
            root.setContentsMargins(16, 12, 16, 12)
            title = QLabel("Knee correction")
            title.setObjectName("TitleLabel")
            root.addWidget(title)
        else:
            root.setContentsMargins(0, 8, 0, 0)
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
        self.preview_controller.release()

    def closeEvent(self, event) -> None:
        self.preview_controller.release()
        super().closeEvent(event)

    def _default_output_folder(self) -> Path:
        folder = self.workspace.manual / "knee_correction"
        return folder / self.side if self.side else folder

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()
