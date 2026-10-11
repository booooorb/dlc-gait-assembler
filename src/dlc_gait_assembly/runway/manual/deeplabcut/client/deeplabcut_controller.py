"""Connect DeepLabCut environment checks, installation, launch, and command-session actions."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_environment_use_cases import (
    DEEPLABCUT_CHECK_COMMAND,
    DEEPLABCUT_INSTALL_COMMAND,
    DEEPLABCUT_LAUNCH_COMMAND,
)
from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_job_worker import DeepLabCutJobWorker
from dlc_gait_assembly.shared.client.qt_input_behaviors import add_shortcut


class DeepLabCutController:
    """DeepLabCutController operates on its explicitly supplied DeepLabCutWidget view."""

    def __init__(self, view):
        self.view = view

    def _install_shortcuts(self) -> None:
        self.view._shortcuts = [
            add_shortcut(self.view, "Ctrl+R", lambda: self.view._terminal.submit_command(DEEPLABCUT_LAUNCH_COMMAND)),
            add_shortcut(self.view, "Ctrl+I", lambda: self.view._terminal.submit_command(DEEPLABCUT_INSTALL_COMMAND)),
            add_shortcut(self.view, "Ctrl+Shift+I", lambda: open_url(DEEPLABCUT_INSTALL_URL)),
            add_shortcut(self.view, "Ctrl+D", lambda: open_url(DEEPLABCUT_DOCS_URL)),
            add_shortcut(self.view, "Ctrl+G", lambda: open_url(DEEPLABCUT_GITHUB_URL)),
            add_shortcut(self.view, "Ctrl+P", lambda: open_url(DEEPLABCUT_PAPER_URL)),
        ]

    def _connect_signals(self) -> None:
        self.view.launch_button.clicked.connect(lambda: self.view._terminal.submit_command(DEEPLABCUT_LAUNCH_COMMAND))
        self.view.outputs_button.clicked.connect(self._open_manual_outputs)
        self.view.install_button.clicked.connect(lambda: self.view._terminal.submit_command(DEEPLABCUT_INSTALL_COMMAND))
        self.view._terminal.command_submitted.connect(self.view.terminal_controller._run_terminal_command)
        self.view._terminal.interrupt_requested.connect(self.view.terminal_controller._interrupt_process)
        self.view.install_docs_button.clicked.connect(lambda: open_url(DEEPLABCUT_INSTALL_URL))
        self.view.user_docs_button.clicked.connect(lambda: open_url(DEEPLABCUT_DOCS_URL))
        self.view.github_button.clicked.connect(lambda: open_url(DEEPLABCUT_GITHUB_URL))
        self.view.paper_button.clicked.connect(lambda: open_url(DEEPLABCUT_PAPER_URL))

    def _open_manual_outputs(self) -> None:
        if not self.view.terminal_controller._is_process_running():
            organized = self.view.environment.organize_outputs()
            moved_count = len(organized.analyzed_files) + len(organized.labeled_videos)
            if moved_count:
                self.view._terminal.append_output(f"Organized {moved_count} DeepLabCut output file(s).\n")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.view._manual_outputs.root)))

    def _set_deeplabcut_available(self, available: bool) -> None:
        self.view._deeplabcut_available = available
        self.view.status_presenter._set_environment_status()
        self.view.status_presenter._set_progress_idle()
        self.view.status_presenter._sync_environment_buttons()

    def _check_deeplabcut_available(self):
        if (
            self.view._released
            or self.view._probe_process is not None
            or self.view.terminal_controller._is_process_running()
        ):
            return
        (_display, command) = self.view.environment.prepare_command(DEEPLABCUT_CHECK_COMMAND, self.view._cwd)
        worker = DeepLabCutJobWorker(self.view.environment.new_session(), command, self.view)
        self.view._probe_process = worker
        worker.completed.connect(lambda result: self._finish_probe(result.returncode == 0))
        worker.failed.connect(lambda _message: self._finish_probe(False))
        worker.finished.connect(worker.deleteLater)
        self.view.status_presenter._set_status("Checking", "other")
        self.view.status_presenter._set_progress_busy("Checking for DeepLabCut…")
        self.view.status_presenter._sync_environment_buttons()
        worker.start()

    def _finish_probe(self, available):
        self.view._probe_process = None
        if not self.view._released:
            self._set_deeplabcut_available(available)


DEEPLABCUT_DOCS_URL = "https://deeplabcut.github.io/DeepLabCut/"
DEEPLABCUT_INSTALL_URL = "https://deeplabcut.github.io/DeepLabCut/docs/installation"
DEEPLABCUT_GITHUB_URL = "https://github.com/DeepLabCut/DeepLabCut"
DEEPLABCUT_PAPER_URL = "https://www.nature.com/articles/s41596-019-0176-0"


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))
