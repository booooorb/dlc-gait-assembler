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
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(8)
        title = QLabel("PCA and random forest analysis")
        title.setObjectName("TitleLabel")
        root.addWidget(title)
        status = QLabel("Analysis controls are not available in this build.")
        status.setObjectName("StatusLabel")
        root.addWidget(status)
        root.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(theme.workspace_stylesheet("PcaRandomForestWidget"))
