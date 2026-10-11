"""Display supported SVG/image artifacts and manage enlarged preview dialogs."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet as _dependency_theme_stylesheet
from dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer import qt_safe_svg_bytes


class ClickableSvgWidget(QSvgWidget):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to open a larger figure preview.")

    def load(self, contents) -> None:
        super().load(contents)
        self.renderer().setAspectRatioMode(Qt.KeepAspectRatio)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SvgPreviewDialog(QDialog):
    """Large, aspect-ratio-preserving viewer for one or more SVG figures."""

    def __init__(self, title: str, plots: tuple[tuple[str, bytes], ...], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(820, 560)
        self.resize(1100, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("FigurePreviewTitle")
        layout.addWidget(heading)
        note = QLabel("Full-size figure preview • original proportions preserved")
        note.setObjectName("FigurePreviewNote")
        layout.addWidget(note)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabBarAutoHide(True)
        self.figures: list[QSvgWidget] = []
        for index, (label, svg_data) in enumerate(plots):
            figure = QSvgWidget()
            figure.setObjectName("LargeFigurePreview")
            figure.setMinimumSize(720, 420)
            figure.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            figure.load(QByteArray(qt_safe_svg_bytes(svg_data)))
            figure.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
            self.tabs.addTab(figure, label or f"Figure {index + 1}")
            self.figures.append(figure)
        layout.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            _dependency_theme_stylesheet(
                "\n                QLabel#FigurePreviewTitle {\n                    color: {theme.TEXT};\n                    font-size: 16px;\n                    font-weight: 700;\n                }\n                QLabel#FigurePreviewNote {\n                    color: {theme.CONNECTOR};\n                    font-size: 11px;\n                }\n                QSvgWidget#LargeFigurePreview {\n                    background: white;\n                    border: 1px solid {theme.BORDER};\n                }\n                "
            )
        )
