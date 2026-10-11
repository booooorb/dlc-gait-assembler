"""Present DeepLabCut availability, running, and failure states and enabled actions."""

from __future__ import annotations

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_controller import (
    DEEPLABCUT_INSTALL_COMMAND,
    DEEPLABCUT_LAUNCH_COMMAND,
)
from dlc_gait_assembly.shared.client.qt_input_behaviors import animate_button_emphasis
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class DeepLabCutEnvironmentStatus:
    """DeepLabCutEnvironmentStatus operates on its explicitly supplied DeepLabCutWidget view."""

    def __init__(self, view):
        self.view = view

    def _set_running(self, running: bool) -> None:
        self.view.launch_button.setText("Running..." if running else "Launch DeepLabCut")
        self.view.install_button.setText(
            "Installing..."
            if running and self.view._running_command == DEEPLABCUT_INSTALL_COMMAND
            else "Install DeepLabCut"
        )
        if running:
            self._set_status("Running", "running")
        else:
            self._set_environment_status()
            self._set_progress_idle()
        self.view.status_label.setProperty("running", running)
        self.view.status_label.style().unpolish(self.view.status_label)
        self.view.status_label.style().polish(self.view.status_label)
        self.view._terminal.set_process_running(running)
        self._sync_environment_buttons()

    def _set_status(self, text: str, state: str = "other") -> None:
        self.view.status_label.setText(f"Status: {text}")
        self.view.status_label.setProperty("statusState", state)
        self.view.status_label.style().unpolish(self.view.status_label)
        self.view.status_label.style().polish(self.view.status_label)

    def _sync_environment_buttons(self) -> None:
        running = self.view.terminal_controller._is_process_running()
        checking = self.view._probe_process is not None
        installable = self.view._installable
        self.view.launch_button.setEnabled(self.view._deeplabcut_available and (not running) and (not checking))
        self.view.install_button.setEnabled(
            not self.view._deeplabcut_available and installable and (not running) and (not checking)
        )
        self.view.install_button.setVisible(not self.view._deeplabcut_available)

    def _set_environment_status(self) -> None:
        if self.view._deeplabcut_available:
            self._set_status("Detected", "ready")
        elif self.view._installable:
            self._set_status("Not detected", "error")
        else:
            self._set_status("Missing YAML", "error")

    def _set_progress_busy(self, text: str) -> None:
        self.view.progress.setRange(0, 0)
        self.view.progress.setFormat(text)
        self.view.progress.set_active(True)
        if self.view._running_command == DEEPLABCUT_LAUNCH_COMMAND:
            self.view.launch_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
            animate_button_emphasis(self.view.launch_button, True)
            animate_button_emphasis(self.view.install_button, False)
        elif self.view._running_command == DEEPLABCUT_INSTALL_COMMAND:
            self.view.install_button.setIcon(interface_icon("download", theme.TEXT))
            animate_button_emphasis(self.view.install_button, True)
            animate_button_emphasis(self.view.launch_button, False)

    def _set_progress_idle(self) -> None:
        if self.view.terminal_controller._is_process_running() or self.view._probe_process is not None:
            return
        self.view.progress.setRange(0, 100)
        self.view.progress.setValue(0)
        self.view.progress.setFormat("Ready" if self.view._deeplabcut_available else "Idle")
        self.view.progress.set_active(False)

    def _set_progress_done(self, text: str) -> None:
        self.view.progress.setRange(0, 100)
        self.view.progress.setValue(100)
        self.view.progress.setFormat(text)
        self.view.progress.set_active(False)
        animate_button_emphasis(self.view.launch_button, False)
        animate_button_emphasis(self.view.install_button, False)

    def _set_progress_error(self, text: str) -> None:
        self.view.progress.setRange(0, 100)
        self.view.progress.setValue(0)
        self.view.progress.setFormat(text)
        self.view.progress.set_active(False)
        animate_button_emphasis(self.view.launch_button, False)
        animate_button_emphasis(self.view.install_button, False)
