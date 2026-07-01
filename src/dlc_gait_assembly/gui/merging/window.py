from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from dlc_gait_assembly.gui import theme


class MergingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("MergingWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        label = QLabel("No merging controls are available yet.")
        label.setObjectName("StatusLabel")
        layout.addWidget(label)
        layout.addStretch(1)
        self.setStyleSheet(theme.workspace_stylesheet("MergingWidget"))

    def can_close(self, parent=None) -> bool:
        return True
