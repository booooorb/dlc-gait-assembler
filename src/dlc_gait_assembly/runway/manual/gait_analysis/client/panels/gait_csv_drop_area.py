"""Large native CSV drop target with a useful empty state."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QGroupBox, QTreeWidget


class CsvDropArea(QGroupBox):
    paths_dropped = Signal(list)

    def __init__(self, title):
        super().__init__(title)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".csv" for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()
                 if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".csv"]
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()


class RecordingFilesTree(QTreeWidget):
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.topLevelItemCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            font = painter.font()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(self.viewport().rect().adjusted(24, 16, -24, -16), Qt.AlignCenter | Qt.TextWordWrap,
                             "Drop CSV files here\n\nor use Add CSVs / Add folder above\n\nLeft, right, and underside views are matched by recording.")
