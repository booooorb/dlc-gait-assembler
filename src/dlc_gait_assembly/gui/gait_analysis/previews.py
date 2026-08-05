"""Stick-plot and generated-output preview widgets and dialogs."""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
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

from dlc_gait_assembly.gui.shared.svg import qt_safe_svg_bytes


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


def previewable_output_paths(output_files) -> tuple[Path, ...]:
    """Return existing SVG and CSV outputs once, preserving pipeline order."""

    paths: list[Path] = []
    seen: set[Path] = set()
    for output_file in output_files:
        path = Path(output_file)
        if path.suffix.lower() not in {".svg", ".csv"} or not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        paths.append(resolved)
    return tuple(paths)


class OutputPreviewWidget(QWidget):
    """Selectable, bounded preview for generated SVG figures and CSV tables."""

    def __init__(
        self,
        *,
        max_csv_rows: int = 12,
        max_csv_columns: int = 12,
        parent=None,
    ):
        super().__init__(parent)
        self._paths: tuple[Path, ...] = ()
        self._max_csv_rows = max(1, max_csv_rows)
        self._max_csv_columns = max(1, max_csv_columns)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(QLabel("Generated output"))
        self.file_combo = QComboBox()
        self.file_combo.setObjectName("OutputPreviewFile")
        self.file_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        header.addWidget(self.file_combo, 1)
        layout.addLayout(header)

        self.preview_stack = QStackedWidget()
        self.empty_label = QLabel("Generated SVG figures and CSV tables will appear here.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setObjectName("MutedLabel")
        self.svg_preview = QSvgWidget()
        self.svg_preview.setObjectName("OutputPreviewSvg")
        self.svg_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.csv_preview = QTableWidget()
        self.csv_preview.setObjectName("OutputPreviewTable")
        self.csv_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.csv_preview.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.csv_preview.verticalHeader().setVisible(False)
        self.csv_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
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
        self._paths = previewable_output_paths(output_files)
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for path in self._paths:
            self.file_combo.addItem(f"{path.parent.name} / {path.name}")
        self.file_combo.blockSignals(False)

        if not self._paths:
            self.preview_stack.setCurrentWidget(self.empty_label)
            self.preview_note.setText("No previewable SVG or CSV outputs were generated.")
            return

        first_figure = next(
            (index for index, path in enumerate(self._paths) if path.suffix.lower() == ".svg"),
            0,
        )
        self.file_combo.setCurrentIndex(first_figure)
        self._show_current(first_figure)

    def _show_current(self, index: int) -> None:
        if not 0 <= index < len(self._paths):
            self.preview_stack.setCurrentWidget(self.empty_label)
            return
        path = self._paths[index]
        try:
            if path.suffix.lower() == ".svg":
                self.svg_preview.load(QByteArray(qt_safe_svg_bytes(path.read_bytes())))
                if not self.svg_preview.renderer().isValid():
                    raise ValueError("the generated SVG is not valid")
                self.preview_stack.setCurrentWidget(self.svg_preview)
                self.preview_note.setText(f"Figure preview • {path.name}")
            else:
                shown_rows, shown_columns = self._load_csv(path)
                self.preview_stack.setCurrentWidget(self.csv_preview)
                self.preview_note.setText(
                    f"Table preview • {shown_rows} rows × {shown_columns} columns shown"
                )
        except (OSError, csv.Error, UnicodeError, ValueError) as exc:
            self.empty_label.setText(f"Could not preview {path.name}:\n{exc}")
            self.preview_stack.setCurrentWidget(self.empty_label)
            self.preview_note.clear()

    def _load_csv(self, path: Path) -> tuple[int, int]:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            rows: list[list[str]] = []
            for row_index, row in enumerate(reader):
                if row_index >= self._max_csv_rows:
                    break
                rows.append(row)

        widest_row = max((len(row) for row in rows), default=0)
        column_count = min(
            max(len(header), widest_row),
            self._max_csv_columns,
        )
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
                self.csv_preview.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(value),
                )
        return len(rows), column_count
