from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QMainWindow, QWidget

from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    widget_factory: Callable[[], QWidget]


TOOL_SPECS = [
    ToolSpec("video_editor", "Video Editing", VideoEditorWidget),
]


class MainWindow(QMainWindow):
    def __init__(self, initial_tool_id: str = "video_editor"):
        super().__init__()
        self.setWindowTitle("DLC Gait Assembler")
        self.resize(1280, 820)
        self._active_tool: QWidget | None = None
        self._open_tool(initial_tool_id)

    def closeEvent(self, event):
        if self._active_tool is not None and hasattr(self._active_tool, "can_close"):
            if not self._active_tool.can_close(self):
                event.ignore()
                return

        if self._active_tool is not None and hasattr(self._active_tool, "release_resources"):
            self._active_tool.release_resources()

        super().closeEvent(event)

    def _open_tool(self, tool_id: str) -> None:
        spec = self._tool_spec(tool_id)
        tool = spec.widget_factory()
        self._active_tool = tool
        self.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self.setCentralWidget(tool)

    def _tool_spec(self, tool_id: str) -> ToolSpec:
        for spec in TOOL_SPECS:
            if spec.id == tool_id:
                return spec
        raise ValueError(f"Unknown tool: {tool_id}")
