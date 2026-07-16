from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.interaction import add_shortcut, set_tooltip
from dlc_gait_assembly.gui.shared.progress import DynamicProgressBar
from dlc_gait_assembly.services.imports import (
    deeplabcut_environment_file,
    deeplabcut_install_command,
    deeplabcut_install_display_command,
    deeplabcut_launch_command,
    deeplabcut_launch_display_command,
    deeplabcut_probe_command,
)
from dlc_gait_assembly.services.manual_outputs import organize_manual_deeplabcut_outputs
from dlc_gait_assembly.services.project_paths import (
    find_project_root,
    manual_pipeline_output_folders,
)


DEEPLABCUT_DOCS_URL = "https://deeplabcut.github.io/DeepLabCut/"
DEEPLABCUT_INSTALL_URL = "https://deeplabcut.github.io/DeepLabCut/docs/installation"
DEEPLABCUT_GITHUB_URL = "https://github.com/DeepLabCut/DeepLabCut"
DEEPLABCUT_PAPER_URL = "https://www.nature.com/articles/s41596-019-0176-0"
DEEPLABCUT_LAUNCH_COMMAND = "activate-dlc"
DEEPLABCUT_INSTALL_COMMAND = "install-dlc"
DEEPLABCUT_CHECK_COMMAND = "check-dlc"


class DeepLabCutWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("DeepLabCutWidget")
        self._process: QProcess | None = None
        self._probe_process: QProcess | None = None
        self._running_command: str | None = None
        self._deeplabcut_available = False
        self._project_root = find_project_root(__file__)
        self._manual_outputs = manual_pipeline_output_folders(self._project_root)
        self._environment_file = deeplabcut_environment_file(self._project_root)
        self._cwd = self._manual_outputs.root
        self._build_ui()
        self._install_shortcuts()
        self._connect_signals()
        self._apply_style()
        self._terminal.write_intro(self._cwd)
        self._set_status("Checking", "other")
        self._sync_environment_buttons()
        QTimer.singleShot(0, self._check_deeplabcut_available)

    def can_close(self, parent=None) -> bool:
        if self._is_process_running():
            QMessageBox.information(
                parent or self,
                "DeepLabCut command is still running",
                "Stop the active DeepLabCut command before closing DLC Gait Assembler.",
            )
            return False
        return True

    def release_resources(self) -> None:
        if self._probe_process is not None:
            self._probe_process.terminate()
            if not self._probe_process.waitForFinished(750):
                self._probe_process.kill()
                self._probe_process.waitForFinished(750)
            self._probe_process = None

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
            self.outputs_button,
            "Open the manual pipeline folders for analyzed data, labeled videos, and gait results.",
        )
        toolbar_layout.addWidget(self.outputs_button)

        self.install_button = QPushButton("Install DeepLabCut")
        self.install_button.setObjectName("InstallButton")
        set_tooltip(
            self.install_button,
            f"Install DeepLabCut from {self._environment_file.name} in the imports folder.",
            "Ctrl+I",
        )
        toolbar_layout.addWidget(self.install_button)

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
        self.progress.set_indeterminate_animated(False)
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

    def _install_shortcuts(self) -> None:
        self._shortcuts = [
            add_shortcut(self, "Ctrl+R", lambda: self._terminal.submit_command(DEEPLABCUT_LAUNCH_COMMAND)),
            add_shortcut(self, "Ctrl+I", lambda: self._terminal.submit_command(DEEPLABCUT_INSTALL_COMMAND)),
            add_shortcut(self, "Ctrl+Shift+I", lambda: _open_url(DEEPLABCUT_INSTALL_URL)),
            add_shortcut(self, "Ctrl+D", lambda: _open_url(DEEPLABCUT_DOCS_URL)),
            add_shortcut(self, "Ctrl+G", lambda: _open_url(DEEPLABCUT_GITHUB_URL)),
            add_shortcut(self, "Ctrl+P", lambda: _open_url(DEEPLABCUT_PAPER_URL)),
        ]

    def _connect_signals(self) -> None:
        self.launch_button.clicked.connect(lambda: self._terminal.submit_command(DEEPLABCUT_LAUNCH_COMMAND))
        self.outputs_button.clicked.connect(self._open_manual_outputs)
        self.install_button.clicked.connect(lambda: self._terminal.submit_command(DEEPLABCUT_INSTALL_COMMAND))
        self._terminal.command_submitted.connect(self._run_terminal_command)
        self._terminal.interrupt_requested.connect(self._interrupt_process)
        self.install_docs_button.clicked.connect(lambda: _open_url(DEEPLABCUT_INSTALL_URL))
        self.user_docs_button.clicked.connect(lambda: _open_url(DEEPLABCUT_DOCS_URL))
        self.github_button.clicked.connect(lambda: _open_url(DEEPLABCUT_GITHUB_URL))
        self.paper_button.clicked.connect(lambda: _open_url(DEEPLABCUT_PAPER_URL))

    def _open_manual_outputs(self) -> None:
        if not self._is_process_running():
            organized = organize_manual_deeplabcut_outputs(self._manual_outputs)
            moved_count = len(organized.analyzed_files) + len(organized.labeled_videos)
            if moved_count:
                self._terminal.append_output(f"Organized {moved_count} DeepLabCut output file(s).\n")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._manual_outputs.root)))

    def _run_terminal_command(self, command: str) -> None:
        command = command.strip()
        if not command:
            self._terminal.append_prompt(self._cwd)
            return

        if self._is_process_running():
            self._process.write((command + os.linesep).encode())
            return

        if command == "clear":
            self._terminal.clear_terminal(self._cwd)
            return

        if command == "cd" or command.startswith("cd "):
            self._change_directory(command)
            return

        command_info = self._terminal_command_info(command)
        if command_info is None:
            self._terminal.append_prompt(self._cwd)
            return

        display_command, shell_command = command_info
        program, arguments = _shell_command(shell_command)
        if display_command != command:
            self._terminal.append_output(f"{display_command}\n")
        self._process = QProcess(self)
        self._running_command = command
        self._process.setProgram(program)
        self._process.setArguments(arguments)
        self._process.setWorkingDirectory(str(self._cwd))
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.started.connect(self._on_process_started)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.finished.connect(self._on_process_finished)

        self._set_running(True)
        self._set_progress_busy(f"Running {display_command}")
        self._process.start()

    def _terminal_command_info(self, command: str) -> tuple[str, str] | None:
        if command == DEEPLABCUT_LAUNCH_COMMAND:
            return deeplabcut_launch_display_command(), deeplabcut_launch_command()

        if command == DEEPLABCUT_INSTALL_COMMAND:
            if not self._environment_file.exists():
                self._terminal.append_output(
                    f"DeepLabCut environment file was not found at {self._environment_file}.\n"
                )
                self._set_status("Missing YAML", "error")
                return None
            return (
                deeplabcut_install_display_command(self._environment_file),
                deeplabcut_install_command(self._environment_file),
            )

        if command == DEEPLABCUT_CHECK_COMMAND:
            return "conda run -n DEEPLABCUT --no-capture-output python -c 'import deeplabcut'", deeplabcut_probe_command()

        return command, command

    def _change_directory(self, command: str) -> None:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            self._terminal.append_output(f"cd: {exc}\n")
            self._terminal.append_prompt(self._cwd)
            return

        target = Path.home() if len(parts) == 1 else Path(parts[1]).expanduser()
        if not target.is_absolute():
            target = self._cwd / target
        target = target.resolve()
        if not target.exists() or not target.is_dir():
            self._terminal.append_output(f"cd: no such directory: {target}\n")
        else:
            self._cwd = target
        self._terminal.append_prompt(self._cwd)

    def _is_process_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.NotRunning

    def _set_running(self, running: bool) -> None:
        self.launch_button.setText("Running..." if running else "Launch DeepLabCut")
        if running:
            self._set_status("Running", "running")
        else:
            self._set_environment_status()
            self._set_progress_idle()
        self.status_label.setProperty("running", running)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._terminal.set_process_running(running)
        self._sync_environment_buttons()

    def _set_status(self, text: str, state: str = "other") -> None:
        self.status_label.setText(f"Status: {text}")
        self.status_label.setProperty("statusState", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _sync_environment_buttons(self) -> None:
        running = self._is_process_running()
        checking = self._probe_process is not None
        installable = self._environment_file.exists()
        self.launch_button.setEnabled(self._deeplabcut_available and not running and not checking)
        self.install_button.setEnabled(not self._deeplabcut_available and installable and not running and not checking)
        self.install_button.setVisible(not self._deeplabcut_available)

    def _set_environment_status(self) -> None:
        if self._deeplabcut_available:
            self._set_status("Detected", "ready")
        elif self._environment_file.exists():
            self._set_status("Not detected", "error")
        else:
            self._set_status("Missing YAML", "error")

    def _check_deeplabcut_available(self) -> None:
        if self._probe_process is not None or self._is_process_running():
            return

        program, arguments = _shell_command(deeplabcut_probe_command())
        self._probe_process = QProcess(self)
        self._probe_process.setProgram(program)
        self._probe_process.setArguments(arguments)
        self._probe_process.setWorkingDirectory(str(self._project_root))
        self._probe_process.setProcessChannelMode(QProcess.MergedChannels)
        self._probe_process.errorOccurred.connect(self._on_probe_error)
        self._probe_process.finished.connect(self._on_probe_finished)
        self._set_status("Checking", "other")
        self._set_progress_busy("Checking DeepLabCut environment")
        self._sync_environment_buttons()
        self._probe_process.start()

    def _on_probe_error(self, _error: QProcess.ProcessError) -> None:
        self._probe_process = None
        self._set_deeplabcut_available(False)

    def _on_probe_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._probe_process = None
        self._set_deeplabcut_available(exit_status == QProcess.NormalExit and exit_code == 0)

    def _set_deeplabcut_available(self, available: bool) -> None:
        self._deeplabcut_available = available
        self._set_environment_status()
        self._set_progress_idle()
        self._sync_environment_buttons()

    def _read_stdout(self) -> None:
        if self._process is None:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        self._terminal.append_output(output)

    def _on_process_started(self) -> None:
        self._set_status("Running", "running")

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        self._terminal.append_output(f"\nProcess error: {self._process.errorString() if self._process else error}\n")
        if error == QProcess.FailedToStart:
            if self._process is not None:
                self._process.deleteLater()
            self._process = None
            self._running_command = None
            self._set_running(False)
            self._set_status("Launch failed.", "error")
            self._set_progress_error("Launch failed")
            self._terminal.append_prompt(self._cwd)
        else:
            self._set_status("Process error.", "error")
            self._set_progress_error("Process error")

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if exit_status == QProcess.NormalExit:
            self._terminal.append_output(f"\nProcess exited with code {exit_code}.\n")
        else:
            self._terminal.append_output("\nProcess crashed or was interrupted.\n")
        completed_command = self._running_command
        self._process = None
        self._running_command = None
        self._set_running(False)
        if exit_status == QProcess.NormalExit and exit_code == 0:
            self._set_progress_done("Command complete")
            if completed_command == DEEPLABCUT_LAUNCH_COMMAND:
                organized = organize_manual_deeplabcut_outputs(self._manual_outputs)
                moved_count = len(organized.analyzed_files) + len(organized.labeled_videos)
                if moved_count:
                    self._terminal.append_output(
                        f"Organized {moved_count} DeepLabCut output file(s).\n"
                    )
        else:
            self._set_progress_error("Command stopped")
        self._terminal.append_prompt(self._cwd)
        if completed_command in {DEEPLABCUT_INSTALL_COMMAND, DEEPLABCUT_CHECK_COMMAND}:
            QTimer.singleShot(0, self._check_deeplabcut_available)

    def _interrupt_process(self) -> None:
        if not self._is_process_running() or self._process is None:
            return
        self._terminal.append_output("^C\n")
        self._process.terminate()

    def _set_progress_busy(self, text: str) -> None:
        self.progress.setRange(0, 0)
        self.progress.setFormat(text)
        self.progress.set_active(True)

    def _set_progress_idle(self) -> None:
        if self._is_process_running() or self._probe_process is not None:
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Ready" if self._deeplabcut_available else "Idle")
        self.progress.set_active(False)

    def _set_progress_done(self, text: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat(text)
        self.progress.set_active(False)

    def _set_progress_error(self, text: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat(text)
        self.progress.set_active(False)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.workspace_stylesheet(
                "DeepLabCutWidget",
                """
            QWidget#StatusGroup {
                background: transparent;
            }
            QLabel#StatusLabel {
                background: transparent;
                border: 0;
                color: {theme.CONNECTOR};
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#StatusLabel[statusState="ready"] {
                color: {theme.STATUS_READY};
            }
            QLabel#StatusLabel[statusState="running"] {
                color: {theme.STATUS_RUNNING};
            }
            QLabel#StatusLabel[statusState="error"] {
                color: {theme.STATUS_ERROR};
            }
            QFrame#TerminalFrame {
                background: {theme.CANVAS};
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
            }
            QFrame#TerminalHeader {
                background: {theme.CANVAS};
                border-radius: 0;
            }
            QLabel#TerminalHeaderLabel {
                color: {theme.CANVAS_TEXT};
                font-size: 12px;
                font-weight: 700;
            }
            QPlainTextEdit#TerminalPane {
                border: 0;
                border-top: 1px solid {theme.BORDER};
                border-radius: 0;
                background: {theme.CANVAS};
                color: {theme.CANVAS_TEXT};
                font-size: 13px;
                padding: 12px;
                selection-background-color: {theme.SOFT};
            }
            QWidget#TerminalViewport {
                background: {theme.CANVAS};
            }
            """
            )
        )


class TerminalPane(QPlainTextEdit):
    command_submitted = Signal(str)
    interrupt_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("TerminalPane")
        self.viewport().setObjectName("TerminalViewport")
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(theme.fixed_width_font())
        self.setMaximumBlockCount(5000)
        self._prompt_position = 0
        self._history: list[str] = []
        self._history_index = 0
        self._process_running = False

    def write_intro(self, cwd: Path) -> None:
        self.clear()
        self.appendPlainText("DeepLabCut terminal")
        self.appendPlainText(
            "Use install-dlc to create the DEEPLABCUT environment, activate-dlc to launch, "
            "check-dlc to detect it, clear to reset, cd to change folders, Ctrl+C to interrupt."
        )
        self.append_prompt(cwd)

    def clear_terminal(self, cwd: Path) -> None:
        self.clear()
        self.append_prompt(cwd)

    def append_prompt(self, cwd: Path) -> None:
        if not self.toPlainText().endswith("\n"):
            self.insertPlainText("\n")
        self.insertPlainText(f"{cwd} $ ")
        self._prompt_position = self.textCursor().position()
        self.moveCursor(QTextCursor.End)
        self.setFocus()

    def append_output(self, output: str) -> None:
        if not output:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(output)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        if self._process_running:
            self._prompt_position = self.textCursor().position()

    def submit_command(self, command: str) -> None:
        self._replace_current_input(command)
        self._submit_current_line()

    def set_process_running(self, running: bool) -> None:
        self._process_running = running
        self._prompt_position = self.textCursor().position()

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Copy):
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.interrupt_requested.emit()
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._submit_current_line()
            return

        if event.key() == Qt.Key_Backspace and self.textCursor().position() <= self._prompt_position:
            return

        if event.key() == Qt.Key_Home:
            cursor = self.textCursor()
            cursor.setPosition(self._prompt_position)
            self.setTextCursor(cursor)
            return

        if event.key() == Qt.Key_Up:
            self._show_previous_history()
            return

        if event.key() == Qt.Key_Down:
            self._show_next_history()
            return

        if self.textCursor().position() < self._prompt_position:
            cursor = self.textCursor()
            cursor.setPosition(self._prompt_position)
            self.setTextCursor(cursor)

        super().keyPressEvent(event)

    def _submit_current_line(self) -> None:
        command = self._current_input()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n")
        self.setTextCursor(cursor)
        if command:
            self._history.append(command)
        self._history_index = len(self._history)
        self._prompt_position = self.textCursor().position()
        self.command_submitted.emit(command)

    def _current_input(self) -> str:
        cursor = self.textCursor()
        cursor.setPosition(self._prompt_position)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        return cursor.selectedText().replace("\u2029", "\n")

    def _replace_current_input(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.setPosition(self._prompt_position)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def _show_previous_history(self) -> None:
        if not self._history:
            return
        self._history_index = max(0, self._history_index - 1)
        self._replace_current_input(self._history[self._history_index])

    def _show_next_history(self) -> None:
        if not self._history:
            return
        self._history_index = min(len(self._history), self._history_index + 1)
        text = "" if self._history_index == len(self._history) else self._history[self._history_index]
        self._replace_current_input(text)


def _open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def _shell_command(command: str) -> tuple[str, list[str]]:
    if sys.platform.startswith("win"):
        return "cmd.exe", ["/d", "/s", "/c", command]
    return "/bin/zsh", ["-lc", command]
