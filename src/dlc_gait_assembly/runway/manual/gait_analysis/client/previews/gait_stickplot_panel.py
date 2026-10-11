"""Display single-side or synchronized stickplots with frame and detector-selection controls."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, Qt, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout, QWidget

from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_result_browser import OutputPreviewWidget
from dlc_gait_assembly.shared.client.qt_svg_preview import ClickableSvgWidget, SvgPreviewDialog
from dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer import qt_safe_svg_bytes


class StickPlotPairPreviewWidget(QWidget):
    double_clicked = Signal()

    def __init__(self):
        super().__init__()
        self._plots: tuple[tuple[str, bytes], ...] = ()
        self._large_preview_dialog: SvgPreviewDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabBarAutoHide(True)
        layout.addWidget(self.tabs, 1)
        self._panels: list[tuple[QLabel, ClickableSvgWidget]] = []
        self._add_panel()
        self._add_panel()
        self.tabs.setTabVisible(1, False)

    def _add_panel(self):
        _index = len(self._panels)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(4)
        label = QLabel("")
        label.setObjectName("MutedLabel")
        label.setAlignment(Qt.AlignCenter)
        label.hide()
        svg = ClickableSvgWidget()
        svg.setObjectName("StickPlotSvg")
        svg.setMinimumSize(300, 210)
        svg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel_layout.addWidget(label, 0)
        panel_layout.addWidget(svg, 1)
        self.tabs.addTab(panel, f"Figure {_index + 1}")
        panel.installEventFilter(self)
        label.installEventFilter(self)
        svg.installEventFilter(self)
        svg.clicked.connect(self._show_large_preview)
        self._panels.append((label, svg))

    def load_plots(self, plots: tuple[tuple[str, bytes], ...]) -> None:
        self._plots = plots
        while len(self._panels) < len(plots):
            self._add_panel()
        for index, (label, svg) in enumerate(self._panels):
            if index < len(plots):
                (plot_label, svg_data) = plots[index]
                label.setText(plot_label)
                svg.load(QByteArray(qt_safe_svg_bytes(svg_data)))
                self.tabs.setTabText(index, plot_label or f"Figure {index + 1}")
                self.tabs.setTabVisible(index, True)
            else:
                self.tabs.setTabVisible(index, False)
        self.tabs.setCurrentIndex(0)

    def _show_large_preview(self) -> None:
        if not self._plots:
            return
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        dialog = SvgPreviewDialog("Stickplot preview", self._plots, self)
        self._large_preview_dialog = dialog
        dialog.finished.connect(lambda _result, closed=dialog: self._large_preview_closed(closed))
        dialog.show()

    def _large_preview_closed(self, dialog: SvgPreviewDialog) -> None:
        if self._large_preview_dialog is dialog:
            self._large_preview_dialog = None

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        self._show_large_preview()
        event.accept()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.MouseButtonDblClick:
            self.double_clicked.emit()
            self._show_large_preview()
            event.accept()
            return True
        return super().eventFilter(watched, event)


def build_gait_preview_pages(self):
    self.preview_stack = QStackedWidget()
    self.preview_stack.setObjectName("StickPlotPreview")
    self.preview_stack.setMinimumHeight(280)
    self.preview_placeholder = QLabel("Select left/right/bottom CSVs, then generate a stick-plot preview.")
    self.preview_placeholder.setAlignment(Qt.AlignCenter)
    self.preview_placeholder.setWordWrap(True)
    self.preview_placeholder.setObjectName("MutedLabel")
    self.stickplot_view = StickPlotPairPreviewWidget()
    self.stickplot_view.setObjectName("StickPlotPairPreview")
    self.stickplot_view.setMinimumSize(320, 260)
    self.stickplot_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    self.output_preview_view = OutputPreviewWidget(reader=self.analysis.results, max_csv_rows=7, max_csv_columns=10)
    self.output_preview_view.setObjectName("GaitOutputPreview")
    self.preview_stack.addWidget(self.preview_placeholder)
    self.preview_stack.addWidget(self.stickplot_view)
    self.preview_stack.addWidget(self.output_preview_view)
    self.preview_stack.setCurrentWidget(self.preview_placeholder)
    self.preview_page = QWidget()
    preview_layout = QVBoxLayout(self.preview_page)
    preview_layout.setContentsMargins(8, 10, 8, 8)
    preview_layout.addWidget(self.preview_stack, 1)
    self.workspace_tabs.addTab(self.preview_page, "2. Preview / results")
