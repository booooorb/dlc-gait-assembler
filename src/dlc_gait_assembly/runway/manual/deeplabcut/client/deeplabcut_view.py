"""Assemble environment actions, installation status, terminal, and output controls."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_controller import DeepLabCutController
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_environment_status import DeepLabCutEnvironmentStatus
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_styles import DeepLabCutStyle
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_terminal_controller import (
    DeepLabCutTerminalController,
)
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_terminal_widget import TerminalPane
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar


class DeepLabCutWidget(QWidget):
    def __init__(self, *, environment):
        super().__init__()
        self.controller = DeepLabCutController(self)
        self.terminal_controller = DeepLabCutTerminalController(self)
        self.status_presenter = DeepLabCutEnvironmentStatus(self)
        self.styling = DeepLabCutStyle(self)
        self.setObjectName("DeepLabCutWidget")
        self.environment = environment
        self._released = False
        self._process = None
        self._probe_process = None
        self._running_command: str | None = None
        self._deeplabcut_available = False
        self._manual_outputs = environment.environment.folders
        self._environment_file = environment.environment.recipe
        self._installable = environment.environment.installable
        self._cwd = environment.environment.cwd
        self._build_ui()
        self.controller._install_shortcuts()
        self.controller._connect_signals()
        self.styling._apply_style()
        self._terminal.write_intro(self._cwd)
        self.status_presenter._set_status("Checking", "other")
        self.status_presenter._sync_environment_buttons()
        QTimer.singleShot(0, self.controller._check_deeplabcut_available)

    def can_close(self, parent=None) -> bool:
        if self.terminal_controller._is_process_running():
            QMessageBox.information(
                parent or self,
                "DeepLabCut command is still running",
                "Stop the active DeepLabCut command before closing DLC Gait Assembler.",
            )
            return False
        return True

    def release_resources(self) -> None:
        self._released = True
        for worker in (self._probe_process, self._process):
            if worker is not None:
                worker.cancel()
                worker.wait(4000)
        self._probe_process = None
        self._process = None

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        toolbar = QFrame()
        toolbar.setObjectName("TerminalToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 12, 12, 12)
        toolbar_layout.setSpacing(12)
        title = QLabel("DeepLabCut terminal")
        title.setObjectName("TitleLabel")
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch(1)
        status_group = QWidget()
        status_group.setObjectName("StatusGroup")
        status_layout = QHBoxLayout(status_group)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)
        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setProperty("statusState", "ready")
        self.status_label.setProperty("running", False)
        status_layout.addWidget(self.status_label)
        toolbar_layout.addWidget(status_group)
        self.launch_button = QPushButton("Launch DeepLabCut")
        self.launch_button.setObjectName("PrimaryButton")
        set_tooltip(self.launch_button, "Launch DeepLabCut from the DEEPLABCUT conda environment.", "Ctrl+R")
        toolbar_layout.addWidget(self.launch_button)
        self.outputs_button = QPushButton("Outputs")
        set_tooltip(
            self.outputs_button, "Open the manual pipeline folders for analyzed data, labeled videos, and gait results."
        )
        toolbar_layout.addWidget(self.outputs_button)
        self.install_button = QPushButton("Install DeepLabCut")
        self.install_button.setObjectName("InstallButton")
        set_tooltip(
            self.install_button,
            f"Install DeepLabCut from {self._environment_file.name} from the packaged environment recipe.",
            "Ctrl+I",
        )
        toolbar_layout.addWidget(self.install_button)
        reference_divider = QFrame()
        reference_divider.setObjectName("TerminalToolbarDivider")
        reference_divider.setFrameShape(QFrame.VLine)
        toolbar_layout.addWidget(reference_divider)
        self.install_docs_button = QPushButton("Guide")
        self.user_docs_button = QPushButton("Docs")
        self.github_button = QPushButton("GitHub")
        self.paper_button = QPushButton("Paper")
        set_tooltip(self.install_docs_button, "Open the DeepLabCut installation guide.", "Ctrl+Shift+I")
        set_tooltip(self.user_docs_button, "Open the DeepLabCut documentation.", "Ctrl+D")
        set_tooltip(self.github_button, "Open the DeepLabCut GitHub repository.", "Ctrl+G")
        set_tooltip(self.paper_button, "Open the DeepLabCut protocol paper.", "Ctrl+P")
        toolbar_layout.addWidget(self.install_docs_button)
        toolbar_layout.addWidget(self.user_docs_button)
        toolbar_layout.addWidget(self.github_button)
        toolbar_layout.addWidget(self.paper_button)
        root.addWidget(toolbar)
        self.progress = DynamicProgressBar(accent_role="running")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Ready")
        root.addWidget(self.progress)
        terminal_frame = QFrame()
        terminal_frame.setObjectName("TerminalFrame")
        terminal_layout = QVBoxLayout(terminal_frame)
        terminal_layout.setContentsMargins(8, 8, 8, 8)
        terminal_layout.setSpacing(0)
        terminal_header = QFrame()
        terminal_header.setObjectName("TerminalHeader")
        terminal_header_layout = QHBoxLayout(terminal_header)
        terminal_header_layout.setContentsMargins(12, 8, 12, 8)
        terminal_header_layout.setSpacing(8)
        terminal_label = QLabel("Console")
        terminal_label.setObjectName("TerminalHeaderLabel")
        terminal_header_layout.addWidget(terminal_label)
        terminal_header_layout.addStretch(1)
        terminal_layout.addWidget(terminal_header)
        self._terminal = TerminalPane()
        terminal_layout.addWidget(self._terminal, 1)
        root.addWidget(terminal_frame, 1)

    def apply_theme(self) -> None:
        """Refresh this page's feature styling after the application theme changes."""
        self.styling._apply_style()
