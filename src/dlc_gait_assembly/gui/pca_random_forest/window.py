from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from dlc_gait_assembly.gui import theme


class PcaRandomForestWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("PcaRandomForestWidget")
        self._build_ui()
        self._apply_style()

    def can_close(self, parent=None) -> bool:
        return True

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        status = QLabel("No analysis controls are available yet.")
        status.setObjectName("StatusLabel")
        root.addWidget(status)
        root.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(theme.workspace_stylesheet("PcaRandomForestWidget"))
