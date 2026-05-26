from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class GaitAnalysisWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Gait analysis tools will live here."))
