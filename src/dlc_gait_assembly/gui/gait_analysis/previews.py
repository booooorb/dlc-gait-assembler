"""Stick-plot preview widgets and dialogs."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.svg import qt_safe_svg_bytes


class DoubleClickSvgWidget(QSvgWidget):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()


class StickPlotPairPreviewWidget(QWidget):
    double_clicked = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        self._panels: list[tuple[QLabel, QSvgWidget]] = []
        for _index in range(2):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(4)
            label = QLabel("")
            label.setObjectName("MutedLabel")
            label.setAlignment(Qt.AlignCenter)
            svg = QSvgWidget()
            svg.setObjectName("StickPlotSvg")
            svg.setMinimumSize(150, 104)
            svg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            panel_layout.addWidget(label, 0)
            panel_layout.addWidget(svg, 1)
            layout.addWidget(panel, 1)
            panel.installEventFilter(self)
            label.installEventFilter(self)
            svg.installEventFilter(self)
            self._panels.append((label, svg))
        self._panels[1][0].parentWidget().hide()

    def load_plots(self, plots: tuple[tuple[str, bytes], ...]) -> None:
        for index, (label, svg) in enumerate(self._panels):
            panel = label.parentWidget()
            if index < len(plots):
                plot_label, svg_data = plots[index]
                label.setText(plot_label)
                svg.load(QByteArray(qt_safe_svg_bytes(svg_data)))
                panel.show()
            else:
                panel.hide()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.MouseButtonDblClick:
            self.double_clicked.emit()
            event.accept()
            return True
        return super().eventFilter(watched, event)


class StickPlotPreviewDialog(QDialog):
    def __init__(self, plots: tuple[tuple[str, bytes], ...], source_name: str, parent=None):
        super().__init__(parent)
        title = "Stick-plot preview"
        if source_name:
            title = f"{title}: {source_name}"
        self.setWindowTitle(title)
        self.resize(1180, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setObjectName("LargeStickPlotScroll")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(14)
        self.previews: list[QSvgWidget] = []
        for plot_label, svg_data in plots:
            label = QLabel(plot_label)
            label.setObjectName("PreviewTitle")
            content_layout.addWidget(label)
            preview = QSvgWidget()
            preview.setObjectName("LargeStickPlotSvg")
            preview.load(QByteArray(qt_safe_svg_bytes(svg_data)))
            width, height = expanded_svg_size(preview)
            preview.setFixedSize(width, height)
            content_layout.addWidget(preview)
            self.previews.append(preview)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.setStyleSheet(
            theme.workspace_stylesheet(
                "StickPlotPreviewDialog",
                """
                QScrollArea#LargeStickPlotScroll {
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    background: white;
                }
                QSvgWidget#LargeStickPlotSvg { background: white; }
                """,
            )
        )


def expanded_svg_size(svg_widget: QSvgWidget) -> tuple[int, int]:
    default_size = svg_widget.renderer().defaultSize()
    if default_size.isValid() and default_size.width() > 0 and default_size.height() > 0:
        aspect = default_size.width() / default_size.height()
        width = max(default_size.width(), 1200)
        height = max(default_size.height(), int(width / aspect))
        if height < 700:
            height = 700
            width = max(width, int(height * aspect))
        return width, height
    return 1200, 700
