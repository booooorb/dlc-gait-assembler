from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from dlc_gait_assembly.gui import theme


class MergingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("MergingWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        title = QLabel("Dataset merging")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        label = QLabel("Merging controls are not available in this build.")
        label.setObjectName("StatusLabel")
        layout.addWidget(label)
        layout.addStretch(1)
        self.setStyleSheet(theme.workspace_stylesheet("MergingWidget"))

    def can_close(self, parent=None) -> bool:
        return True
