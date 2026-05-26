from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MergingWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Merging tools will live here."))
