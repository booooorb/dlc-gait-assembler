from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl, Signal
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
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        toolbar = QFrame()
        toolbar.setObjectName("TerminalToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 11, 14, 11)
        toolbar_layout.setSpacing(10)

        title_block = QWidget()
        title_block.setObjectName("TitleBlock")
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        title = QLabel("DeepLabCut Terminal")
        title.setObjectName("TitleLabel")
        title_layout.addWidget(title)

        subtitle = QLabel("DEEPLABCUT conda environment")
        subtitle.setObjectName("SubtitleLabel")
        title_layout.addWidget(subtitle)

        toolbar_layout.addWidget(title_block)
        toolbar_layout.addStretch(1)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusPill")
        self.status_label.setProperty("running", False)
        toolbar_layout.addWidget(self.status_label)

        self.launch_button = QPushButton("Launch DeepLabCut")
        self.launch_button.setObjectName("PrimaryButton")
        toolbar_layout.addWidget(self.launch_button)

        self.install_docs_button = QPushButton("Install")
        self.user_docs_button = QPushButton("Docs")
        self.github_button = QPushButton("GitHub")
        self.paper_button = QPushButton("Paper")
        toolbar_layout.addWidget(self.install_docs_button)
        toolbar_layout.addWidget(self.user_docs_button)
        toolbar_layout.addWidget(self.github_button)
        toolbar_layout.addWidget(self.paper_button)

        root.addWidget(toolbar)

        terminal_frame = QFrame()
        terminal_frame.setObjectName("TerminalFrame")
        terminal_layout = QVBoxLayout(terminal_frame)
        terminal_layout.setContentsMargins(8, 8, 8, 8)
        terminal_layout.setSpacing(0)

        terminal_header = QFrame()
        terminal_header.setObjectName("TerminalHeader")
        terminal_header_layout = QHBoxLayout(terminal_header)
        terminal_header_layout.setContentsMargins(9, 7, 9, 7)
        terminal_header_layout.setSpacing(7)
        terminal_label = QLabel("Console")
        terminal_label.setObjectName("TerminalHeaderLabel")
        terminal_header_layout.addWidget(terminal_label)
        terminal_header_layout.addStretch(1)
        command_hint = QLabel("activate-dlc")
        command_hint.setObjectName("CommandHint")
        terminal_header_layout.addWidget(command_hint)
        terminal_layout.addWidget(terminal_header)

        self._terminal = TerminalPane()
        terminal_layout.addWidget(self._terminal, 1)
        root.addWidget(terminal_frame, 1)

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

        display_command = command
        if command == DEEPLABCUT_LAUNCH_COMMAND:
            display_command = _deeplabcut_display_command()

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
        if display_command != command:
            self._terminal.append_output(f"{display_command}\n")
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
        self.status_label.setText("Running" if running else "Ready")
        self.status_label.setProperty("running", running)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._terminal.set_process_running(running)

    def _read_stdout(self) -> None:
        if self._process is None:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        self._terminal.append_output(output)

    def _on_process_started(self) -> None:
        self.status_label.setText("Running")

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
            theme.stylesheet(
                """
            QWidget#DeepLabCutWidget {
                background: {theme.BACKGROUND};
                color: {theme.TEXT};
                font-size: 13px;
            }
            QWidget#TerminalToolbar {
                background: transparent;
            }
            QFrame#TerminalToolbar {
                background: {theme.PANEL};
                border: 1px solid {theme.ACCENT};
                border-radius: 8px;
            }
            QWidget#TitleBlock {
                background: transparent;
            }
            QLabel {
                background: transparent;
            }
            QLabel#TitleLabel {
                color: {theme.TEXT};
                font-size: 17px;
                font-weight: 800;
            }
            QLabel#SubtitleLabel {
                color: {theme.TEXT};
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#StatusPill {
                background: transparent;
                border: 0;
                color: {theme.TEXT};
                font-size: 11px;
                font-weight: 800;
                padding: 0 2px;
            }
            QLabel#StatusPill[running="true"] {
                background: transparent;
                border: 0;
                color: {theme.TEXT};
            }
            QFrame#TerminalFrame {
                background: {theme.TEXT};
                border: 1px solid {theme.ACCENT};
                border-radius: 8px;
            }
            QFrame#TerminalHeader {
                background: {theme.TEXT};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QLabel#TerminalHeaderLabel {
                color: {theme.BACKGROUND};
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#CommandHint {
                color: {theme.SURFACE};
                font-family: Menlo, Consolas, monospace;
                font-size: 11px;
                font-weight: 700;
            }
            QPlainTextEdit#TerminalPane {
                border: 0;
                border-top: 1px solid {theme.ACCENT};
                border-radius: 0;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                background: {theme.TEXT};
                color: {theme.BACKGROUND};
                font-family: Menlo, Consolas, monospace;
                font-size: 13px;
                padding: 12px;
                selection-background-color: {theme.ACCENT};
            }
            QWidget#TerminalViewport {
                background: {theme.TEXT};
            }
            QPushButton {
                border: 1px solid {theme.ACCENT};
                border-radius: 5px;
                padding: 7px 10px;
                background: {theme.SURFACE};
                color: {theme.TEXT};
                font-weight: 700;
            }
            QPushButton:hover {
                background: {theme.SOFT};
                border-color: {theme.TEXT};
                color: {theme.TEXT};
            }
            QPushButton:disabled {
                color: {theme.ACCENT};
                background: {theme.SURFACE};
            }
            QPushButton#PrimaryButton {
                background: {theme.TEXT};
                border-color: {theme.TEXT};
                color: {theme.BACKGROUND};
            }
            QPushButton#PrimaryButton:hover {
                background: {theme.SOFT};
                border-color: {theme.TEXT};
                color: {theme.TEXT};
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
        conda_candidates = [
            "%USERPROFILE%\\anaconda3\\condabin\\conda.bat",
            "%USERPROFILE%\\miniconda3\\condabin\\conda.bat",
            "%LOCALAPPDATA%\\anaconda3\\condabin\\conda.bat",
            "%LOCALAPPDATA%\\miniconda3\\condabin\\conda.bat",
            "C:\\ProgramData\\anaconda3\\condabin\\conda.bat",
            "C:\\ProgramData\\miniconda3\\condabin\\conda.bat",
        ]
        run_attempts = [
            'conda run -n DEEPLABCUT --no-capture-output python -u -m deeplabcut',
            *[
                f'if exist "{path}" call "{path}" run -n DEEPLABCUT --no-capture-output python -u -m deeplabcut'
                for path in conda_candidates
            ],
        ]
        return " || ".join(run_attempts)

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


def _deeplabcut_display_command() -> str:
    if sys.platform.startswith("win"):
        return "conda run -n DEEPLABCUT --no-capture-output python -u -m deeplabcut"
    return "conda activate DEEPLABCUT && python -u -m deeplabcut"
