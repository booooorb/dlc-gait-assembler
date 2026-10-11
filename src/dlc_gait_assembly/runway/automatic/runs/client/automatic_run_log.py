"""Present automatic pipeline messages, failures, and console status."""

from __future__ import annotations

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex as _dependency_theme_mix_hex


class AutomaticRunLog:
    """AutomaticRunLog operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _append_console(self, message: str) -> None:
        lowered = message.lower()
        if any(token in lowered for token in ("error", "failed", "changes required")):
            accent = theme.STATUS_ERROR
        elif any(token in lowered for token in ("complete", "confirmed", "ready")):
            accent = theme.STATUS_READY
        elif any(token in lowered for token in ("review", "manual check", "resume")):
            accent = theme.STATUS_RUNNING
        else:
            accent = theme.CANVAS_TEXT
        if accent != theme.CANVAS_TEXT:
            accent = _dependency_theme_mix_hex(accent, theme.CANVAS_TEXT, 0.22)
        cursor = self.view.automation_console.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        prefix_end = message.find("]") + 1
        if prefix_end > 0:
            prefix_format = QTextCharFormat()
            prefix_format.setForeground(QColor(accent))
            cursor.insertText(message[:prefix_end], prefix_format)
            body_format = QTextCharFormat()
            body_format.setForeground(QColor(theme.CANVAS_TEXT))
            cursor.insertText(message[prefix_end:], body_format)
        else:
            line_format = QTextCharFormat()
            line_format.setForeground(QColor(accent))
            cursor.insertText(message, line_format)
        self.view.automation_console.setTextCursor(cursor)
        self.view.automation_console.ensureCursorVisible()

    def _set_pipeline_log_state(self, text: str, state: str) -> None:
        self.view.pipeline_log_state.setText(f"●  {text}")
        self.view.pipeline_log_state.setProperty("logState", state)
        self.view.pipeline_log_state.style().unpolish(self.view.pipeline_log_state)
        self.view.pipeline_log_state.style().polish(self.view.pipeline_log_state)
