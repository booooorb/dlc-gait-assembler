"""Review actual candidate boundaries before choosing a stride detector."""

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import STRIDE_METHOD_DESCRIPTIONS
from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_stickplot_panel import (
    StickPlotPairPreviewWidget,
)


class StrideComparisonDialog(QDialog):
    def __init__(self, results, current_method, parent=None):
        super().__init__(parent)
        self.results = results
        self.setWindowTitle("Compare stride detection on this recording")
        self.resize(1100, 800)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Compare the stick plots: every method draws the entire recording with identical skeleton frames and axes for each view. Only stance/swing colours and stride markers change; counts may differ. Grey = stance; orange = swing. Asterisked strides fail the current filters and are shown for review only."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.methods = QComboBox()
        self.methods.addItems([row[0] for row in results])
        layout.addWidget(self.methods)
        # Keep the stick-plot viewport the same size when a method has more notes.
        # Otherwise identical SVG geometry appears to resize during comparison.
        self.method_details_scroll = QScrollArea()
        self.method_details_scroll.setWidgetResizable(True)
        self.method_details_scroll.setFixedHeight(175)
        metadata = QWidget()
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.setContentsMargins(4, 4, 4, 4)
        self.method_details_scroll.setWidget(metadata)
        layout.addWidget(self.method_details_scroll)
        self.method_description = QLabel()
        self.method_description.setWordWrap(True)
        metadata_layout.addWidget(self.method_description)
        self.details = QLabel()
        self.details.setWordWrap(True)
        metadata_layout.addWidget(self.details)
        metadata_layout.addStretch(1)
        self.preview = StickPlotPairPreviewWidget()
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.use_button = buttons.addButton("Use selected method", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.methods.currentIndexChanged.connect(self._show_method)
        self.methods.setCurrentText(current_method)
        self._show_method()

    def _show_method(self, *_):
        method, plots, message = self.results[self.methods.currentIndex()]
        self.method_description.setText(STRIDE_METHOD_DESCRIPTIONS.get(method, ""))
        self.details.setText(
            "\n".join(line for line in message.splitlines() if not line.startswith("Tracking confidence filter:"))
        )
        self.preview.setVisible(bool(plots))
        self.use_button.setEnabled(bool(plots))
        if plots:
            view_index = max(0, self.preview.tabs.currentIndex())
            self.preview.load_plots(plots)
            self.preview.tabs.setCurrentIndex(min(view_index, self.preview.tabs.count() - 1))

    def selected_method(self):
        return self.methods.currentText()
