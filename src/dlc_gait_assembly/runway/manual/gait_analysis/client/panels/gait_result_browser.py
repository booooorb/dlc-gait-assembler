"""Display returned recording tables, generated figures, and parameter-figure pages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_figure_viewer import GaitFigureViewer
from dlc_gait_assembly.shared.client.qt_svg_preview import ClickableSvgWidget


class OutputPreviewWidget(QWidget):
    """Selectable, bounded preview for generated SVG figures and CSV tables."""

    def __init__(self, *, reader, max_csv_rows: int = 12, max_csv_columns: int = 12, parent=None):
        super().__init__(parent)
        self.reader = reader
        self._paths: tuple[Path, ...] = ()
        self._max_csv_rows = max(1, max_csv_rows)
        self._max_csv_columns = max(1, max_csv_columns)
        self.figures = GaitFigureViewer(self, reader)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(QLabel("Generated output"))
        self.file_combo = QComboBox()
        self.file_combo.setObjectName("OutputPreviewFile")
        self.file_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.addWidget(self.file_combo, 1)
        layout.addLayout(header)
        self.preview_stack = QStackedWidget()
        self.empty_label = QLabel("Generated SVG figures and CSV tables will appear here.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setObjectName("MutedLabel")
        self.svg_preview = ClickableSvgWidget()
        self.svg_preview.setObjectName("OutputPreviewSvg")
        self.svg_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.csv_preview = QTableWidget()
        self.csv_preview.setObjectName("OutputPreviewTable")
        self.csv_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.csv_preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.csv_preview.verticalHeader().setVisible(False)
        self.csv_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_stack.addWidget(self.empty_label)
        self.preview_stack.addWidget(self.svg_preview)
        self.preview_stack.addWidget(self.csv_preview)
        self.preview_stack.setCurrentWidget(self.empty_label)
        layout.addWidget(self.preview_stack, 1)
        self.preview_note = QLabel("")
        self.preview_note.setObjectName("MutedLabel")
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)
        self.file_combo.currentIndexChanged.connect(self._show_current)
        self.svg_preview.clicked.connect(lambda: self.figures.show(self.selected_path))

    @property
    def paths(self) -> tuple[Path, ...]:
        return self._paths

    @property
    def selected_path(self) -> Path | None:
        index = self.file_combo.currentIndex()
        if 0 <= index < len(self._paths):
            return self._paths[index]
        return None

    def load_paths(self, output_files) -> None:
        self._paths = self.reader.previewable_paths(output_files)
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for path in self._paths:
            self.file_combo.addItem(f"{path.parent.name} / {path.name}")
        self.file_combo.blockSignals(False)
        if not self._paths:
            self.preview_stack.setCurrentWidget(self.empty_label)
            self.preview_note.setText("No previewable SVG or CSV outputs were generated.")
            return
        first_figure = next((index for (index, path) in enumerate(self._paths) if path.suffix.lower() == ".svg"), 0)
        self.file_combo.setCurrentIndex(first_figure)
        self._show_current(first_figure)

    def _show_current(self, index: int) -> None:
        if not 0 <= index < len(self._paths):
            self.preview_stack.setCurrentWidget(self.empty_label)
            return
        path = self._paths[index]
        try:
            if path.suffix.lower() == ".svg":
                self.svg_preview.load(QByteArray(self.reader.svg_bytes(path)))
                if not self.svg_preview.renderer().isValid():
                    raise ValueError("the generated SVG is not valid")
                self.preview_stack.setCurrentWidget(self.svg_preview)
                self.preview_note.setText(f"Figure preview • {path.name} • Click to expand")
            else:
                (shown_rows, shown_columns) = self._load_csv(path)
                self.preview_stack.setCurrentWidget(self.csv_preview)
                self.preview_note.setText(f"Table preview • {shown_rows} rows × {shown_columns} columns shown")
        except (OSError, UnicodeError, ValueError) as exc:
            self.empty_label.setText(f"Could not preview {path.name}:\n{exc}")
            self.preview_stack.setCurrentWidget(self.empty_label)
            self.preview_note.clear()

    def _load_csv(self, path: Path) -> tuple[int, int]:
        (header, rows) = self.reader.table_preview(path, self._max_csv_rows)
        widest_row = max((len(row) for row in rows), default=0)
        column_count = min(max(len(header), widest_row), self._max_csv_columns)
        self.csv_preview.clear()
        self.csv_preview.setRowCount(len(rows))
        self.csv_preview.setColumnCount(column_count)
        if column_count:
            labels = [
                header[column] if column < len(header) and header[column] else f"Column {column + 1}"
                for column in range(column_count)
            ]
            self.csv_preview.setHorizontalHeaderLabels(labels)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row[:column_count]):
                self.csv_preview.setItem(row_index, column_index, QTableWidgetItem(value))
        return (len(rows), column_count)
