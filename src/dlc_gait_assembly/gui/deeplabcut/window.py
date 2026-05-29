from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


DEEPLABCUT_DOCS_URL = "https://deeplabcut.github.io/DeepLabCut/"
DEEPLABCUT_INSTALL_URL = "https://deeplabcut.github.io/DeepLabCut/docs/installation"
DEEPLABCUT_GITHUB_URL = "https://github.com/DeepLabCut/DeepLabCut"
DEEPLABCUT_PAPER_URL = "https://www.nature.com/articles/s41596-019-0176-0"
DEEPLABCUT_LAUNCH_COMMAND = "activate-dlc"


class DeepLabCutWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("DeepLabCutWidget")
        self._process: QProcess | None = None
        self._cwd = Path.cwd()
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._terminal.write_intro(self._cwd)

    def can_close(self, parent=None) -> bool:
        if self._is_process_running():
            QMessageBox.information(
                parent or self,
                "DeepLabCut is still running",
                "Close DeepLabCut before closing DLC Gait Assembler.",
            )
            return False
        return True

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        toolbar = QWidget()
        toolbar.setObjectName("TerminalToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        title = QLabel("DeepLabCut Terminal")
        title.setObjectName("TitleLabel")
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch(1)

        self.status_label = QLabel("Expected conda environment: DEEPLABCUT")
        self.status_label.setObjectName("StatusLabel")
        toolbar_layout.addWidget(self.status_label)

        self.launch_button = QPushButton("Launch DeepLabCut")
        self.launch_button.setObjectName("PrimaryButton")
        toolbar_layout.addWidget(self.launch_button)

        self.install_docs_button = QPushButton("Install Guide")
        self.user_docs_button = QPushButton("Docs")
        self.github_button = QPushButton("GitHub")
        self.paper_button = QPushButton("Paper")
        toolbar_layout.addWidget(self.install_docs_button)
        toolbar_layout.addWidget(self.user_docs_button)
        toolbar_layout.addWidget(self.github_button)
        toolbar_layout.addWidget(self.paper_button)

        root.addWidget(toolbar)

        self._terminal = TerminalPane()
        root.addWidget(self._terminal, 1)

    def _connect_signals(self) -> None:
        self.launch_button.clicked.connect(lambda: self._terminal.submit_command(DEEPLABCUT_LAUNCH_COMMAND))
        self._terminal.command_submitted.connect(self._run_terminal_command)
        self._terminal.interrupt_requested.connect(self._interrupt_process)
        self.install_docs_button.clicked.connect(lambda: _open_url(DEEPLABCUT_INSTALL_URL))
        self.user_docs_button.clicked.connect(lambda: _open_url(DEEPLABCUT_DOCS_URL))
        self.github_button.clicked.connect(lambda: _open_url(DEEPLABCUT_GITHUB_URL))
        self.paper_button.clicked.connect(lambda: _open_url(DEEPLABCUT_PAPER_URL))

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

        program, arguments = _shell_command(command)
        self._process = QProcess(self)
        self._process.setProgram(program)
        self._process.setArguments(arguments)
        self._process.setWorkingDirectory(str(self._cwd))
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.started.connect(self._on_process_started)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.finished.connect(self._on_process_finished)

        self._set_running(True)
        self._process.start()

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
        self.launch_button.setEnabled(not running)
        self.launch_button.setText("Running..." if running else "Launch DeepLabCut")
        self.status_label.setText("Process running. Ctrl+C interrupts." if running else "Ready")
        self._terminal.set_process_running(running)

    def _read_stdout(self) -> None:
        if self._process is None:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        self._terminal.append_output(output)

    def _on_process_started(self) -> None:
        self.status_label.setText("Process running. Ctrl+C interrupts.")

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        self._terminal.append_output(f"\nProcess error: {self._process.errorString() if self._process else error}\n")
        self.status_label.setText("Launch failed.")
        if error == QProcess.FailedToStart:
            if self._process is not None:
                self._process.deleteLater()
            self._process = None
            self._set_running(False)
            self._terminal.append_prompt(self._cwd)

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if exit_status == QProcess.NormalExit:
            self._terminal.append_output(f"\nProcess exited with code {exit_code}.\n")
        else:
            self._terminal.append_output("\nProcess crashed or was interrupted.\n")
        self._process = None
        self._set_running(False)
        self._terminal.append_prompt(self._cwd)

    def _interrupt_process(self) -> None:
        if not self._is_process_running() or self._process is None:
            return
        self._terminal.append_output("^C\n")
        self._process.terminate()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#DeepLabCutWidget {
                background: #f7f8fa;
                color: #111827;
                font-size: 13px;
            }
            QWidget#TerminalToolbar {
                background: #ffffff;
            }
            QLabel {
                background: transparent;
            }
            QLabel#TitleLabel {
                color: #0f172a;
                font-size: 17px;
                font-weight: 800;
            }
            QLabel#StatusLabel {
                color: #475569;
                font-size: 12px;
                font-weight: 700;
            }
            QPlainTextEdit#TerminalPane {
                border: 1px solid #cfd7e3;
                border-radius: 6px;
                background: #020617;
                color: #e2e8f0;
                font-family: Menlo, Consolas, monospace;
                font-size: 13px;
                padding: 10px;
                selection-background-color: #2563eb;
            }
            QPushButton {
                border: 1px solid #c9d2df;
                border-radius: 5px;
                padding: 6px 9px;
                background: #ffffff;
                color: #334155;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #f1f8f8;
                border-color: #a8cfd0;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background: #f1f4f8;
            }
            QPushButton#PrimaryButton {
                background: #e8edff;
                border-color: #b8c2ff;
                color: #3730a3;
            }
            QPushButton#PrimaryButton:hover {
                background: #dfe6ff;
                border-color: #94a3ff;
            }
            """
        )


class TerminalPane(QPlainTextEdit):
    command_submitted = Signal(str)
    interrupt_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("TerminalPane")
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setMaximumBlockCount(5000)
        self._prompt_position = 0
        self._history: list[str] = []
        self._history_index = 0
        self._process_running = False

    def write_intro(self, cwd: Path) -> None:
        self.clear()
        self.appendPlainText("DeepLabCut terminal")
        self.appendPlainText(
            "Type commands here. Use activate-dlc to launch DeepLabCut, clear to reset, "
            "cd to change folders, Ctrl+C to interrupt."
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
    if command == DEEPLABCUT_LAUNCH_COMMAND:
        command = _deeplabcut_shell_command()
    if sys.platform.startswith("win"):
        return "cmd.exe", ["/d", "/s", "/c", command]
    return "/bin/zsh", ["-lc", command]


def _deeplabcut_shell_command() -> str:
    if sys.platform.startswith("win"):
        return (
            "call conda activate DEEPLABCUT "
            "|| call \"%USERPROFILE%\\anaconda3\\Scripts\\activate.bat\" DEEPLABCUT "
            "|| call \"%USERPROFILE%\\miniconda3\\Scripts\\activate.bat\" DEEPLABCUT "
            "&& python -u -m deeplabcut"
        )

    conda_candidates = [
        "$HOME/anaconda3/etc/profile.d/conda.sh",
        "$HOME/miniconda3/etc/profile.d/conda.sh",
        "/opt/anaconda3/etc/profile.d/conda.sh",
        "/opt/miniconda3/etc/profile.d/conda.sh",
    ]
    source_attempts = " || ".join(f'[ -f "{path}" ] && . "{path}"' for path in conda_candidates)
    return (
        f'eval "$(conda shell.zsh hook 2>/dev/null)" '
        f'|| eval "$(conda shell.bash hook 2>/dev/null)" '
        f'|| {source_attempts}; '
        "conda activate DEEPLABCUT && python -u -m deeplabcut"
    )
