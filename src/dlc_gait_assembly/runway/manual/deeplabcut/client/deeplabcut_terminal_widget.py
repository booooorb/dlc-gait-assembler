"""Present DeepLabCut terminal output and command entry with input history."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from dlc_gait_assembly.shared.client.theme.theme_font_loader import (
    fixed_width_font as _dependency_theme_fixed_width_font,
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
        self.setFont(_dependency_theme_fixed_width_font())
        self.setMaximumBlockCount(5000)
        self._prompt_position = 0
        self._history: list[str] = []
        self._history_index = 0
        self._process_running = False

    def write_intro(self, cwd: Path) -> None:
        self.clear()
        self.appendPlainText("DeepLabCut terminal")
        self.appendPlainText(
            "Use install-dlc to create the DEEPLABCUT environment, activate-dlc to launch, check-dlc to detect it, clear to reset, cd to change folders, Ctrl+C to interrupt."
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
