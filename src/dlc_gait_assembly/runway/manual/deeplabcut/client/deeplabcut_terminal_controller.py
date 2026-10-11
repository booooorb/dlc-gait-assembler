"""Connect terminal commands and command-session events to DeepLabCut presentation state."""

from PySide6.QtCore import QTimer

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_environment_use_cases import (
    DEEPLABCUT_CHECK_COMMAND,
    DEEPLABCUT_INSTALL_COMMAND,
    DEEPLABCUT_LAUNCH_COMMAND,
)
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_job_worker import DeepLabCutJobWorker
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class DeepLabCutTerminalController:
    def __init__(self, view):
        self.view = view

    def _run_terminal_command(self, command):
        command = command.strip()
        if self._is_process_running():
            self.view._process.send_input(command)
            return
        if not command:
            self.view._terminal.append_prompt(self.view._cwd)
            return
        if command == "clear":
            self.view._terminal.clear_terminal(self.view._cwd)
            return
        if command == "cd" or command.startswith("cd "):
            self._change_directory(command)
            return
        try:
            display, request = self.view.environment.prepare_command(command, self.view._cwd)
        except (OSError, ValueError) as exc:
            self.view._terminal.append_output(str(exc) + "\n")
            self.view._terminal.append_prompt(self.view._cwd)
            return
        if display != command:
            self.view._terminal.append_output(display + "\n")
        worker = DeepLabCutJobWorker(self.view.environment.new_session(), request, self.view)
        self.view._process, self.view._running_command = worker, command
        worker.output_received.connect(self.view._terminal.append_output)
        worker.completed.connect(self._on_process_finished)
        worker.failed.connect(self._on_process_error)
        worker.finished.connect(worker.deleteLater)
        self.view.status_presenter._set_running(True)
        progress = (
            "Installing DeepLabCut…"
            if command == DEEPLABCUT_INSTALL_COMMAND
            else "Checking for DeepLabCut…"
            if command == DEEPLABCUT_CHECK_COMMAND
            else f"Running {display}"
        )
        self.view.status_presenter._set_progress_busy(progress)
        worker.start()
        self.view.status_presenter._sync_environment_buttons()

    def _change_directory(self, command):
        try:
            self.view._cwd = self.view.environment.change_directory(command, self.view._cwd)
        except (OSError, ValueError) as exc:
            self.view._terminal.append_output(str(exc) + "\n")
        self.view._terminal.append_prompt(self.view._cwd)

    def _is_process_running(self):
        return self.view._process is not None

    def _on_process_error(self, message):
        self.view._terminal.append_output(f"\nProcess error: {message}\n")
        self.view._process = None
        self.view._running_command = None
        self.view.status_presenter._set_running(False)
        self.view.status_presenter._set_status("Command stopped", "error")
        self.view.status_presenter._set_progress_error("Command stopped")
        self.view._terminal.append_prompt(self.view._cwd)

    def _on_process_finished(self, result):
        self.view._terminal.append_output(f"\nProcess exited with code {result.returncode}.\n")
        completed_command = self.view._running_command
        self.view._process = None
        self.view._running_command = None
        self.view.status_presenter._set_running(False)
        if result.returncode == 0:
            self.view.status_presenter._set_progress_done("Command complete")
            if completed_command == DEEPLABCUT_LAUNCH_COMMAND:
                self.view.launch_button.setIcon(interface_icon("check", theme.PRIMARY_TEXT))
            elif completed_command == DEEPLABCUT_INSTALL_COMMAND:
                self.view.install_button.setIcon(interface_icon("check", theme.STATUS_READY))
            organized = self.view.environment.command_completed(completed_command, result)
            if organized is not None:
                count = len(organized.analyzed_files) + len(organized.labeled_videos)
                if count:
                    self.view._terminal.append_output(f"Organized {count} DeepLabCut output file(s).\n")
        else:
            self.view.status_presenter._set_progress_error("Command stopped")
            self.view.launch_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
            self.view.install_button.setIcon(interface_icon("download", theme.TEXT))
        self.view._terminal.append_prompt(self.view._cwd)
        if completed_command in {DEEPLABCUT_INSTALL_COMMAND, DEEPLABCUT_CHECK_COMMAND}:
            QTimer.singleShot(0, self.view.controller._check_deeplabcut_available)

    def _interrupt_process(self):
        if self.view._process is not None:
            self.view._terminal.append_output("^C\n")
            self.view._process.cancel()
