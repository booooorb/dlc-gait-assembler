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
        title = QLabel("PCA and Random Forest Analysis")
        title.setObjectName("TitleLabel")
        root.addWidget(title)
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
            QLabel#TitleLabel {
                font-size: 19px;
                font-weight: 800;
            }
            """
            )
        )
