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
        root.setContentsMargins(14, 14, 14, 14)
        status = QLabel("No analysis controls are available yet.")
        status.setObjectName("StatusLabel")
        root.addWidget(status)
        root.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
            QWidget#PcaRandomForestWidget {
                background: {theme.BACKGROUND};
                color: {theme.TEXT};
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QLabel#StatusLabel {
                color: {theme.CONNECTOR};
                font-size: 13px;
            }
            """
            )
        )
