"""Display detected events, collect inclusion/classification edits, and request reviewed exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderEvent
from dlc_gait_assembly.ladder.business.ladder_event_review_rules import review_ladder_event


class LadderEventReviewTable:
    """LadderEventReviewTable operates on its explicitly supplied LadderAnalysisWidget view."""

    def __init__(self, view):
        self.view = view

    def _populate_event_table(self) -> None:
        self.view.events_table.setRowCount(len(self.view.state.events))
        for row, event in enumerate(self.view.state.events):
            include = QCheckBox()
            include.setChecked(event.included)
            include.setToolTip("Include this event in the reviewed export.")
            include_cell = QWidget()
            include_layout = QHBoxLayout(include_cell)
            include_layout.setContentsMargins(0, 0, 0, 0)
            include_layout.addWidget(include, 0, Qt.AlignmentFlag.AlignCenter)
            self.view.events_table.setCellWidget(row, 0, include_cell)
            for column, value in enumerate(
                (
                    event.view.title(),
                    event.bodypart,
                    event.peak_frame,
                    event.start_frame,
                    event.end_frame,
                    f"{event.depth_px:.3f}",
                    f"{event.duration_s:.3f}",
                ),
                start=1,
            ):
                self.view.events_table.setItem(row, column, QTableWidgetItem(str(value)))
            classification = QComboBox()
            classification.addItems(["unreviewed", "footfall", "slip", "fall"])
            classification.setCurrentText(event.classification)
            self.view.events_table.setCellWidget(row, 8, classification)

    def _reviewed_events(self) -> list[LadderEvent]:
        reviewed: list[LadderEvent] = []
        for row, event in enumerate(self.view.state.events):
            include_cell = self.view.events_table.cellWidget(row, 0)
            include = include_cell.findChild(QCheckBox) if include_cell is not None else None
            classification = self.view.events_table.cellWidget(row, 8)
            reviewed.append(
                review_ladder_event(event, classification.currentText(), bool(include and include.isChecked()))
            )
        return reviewed

    def _save_reviewed_results(self) -> None:
        if self.view.state.csv_path is None:
            return
        if self.view.controller._is_dual_mode() and self.view.state.right_csv_path is not None:
            default_name = (
                f"{self.view.state.csv_path.stem}__{self.view.state.right_csv_path.stem}_ladder_combined_reviewed.csv"
            )
        else:
            default_name = f"{self.view.state.csv_path.stem}_ladder_reviewed.csv"
        default_path = Path(self.view.output_edit.text()).expanduser() / default_name
        (filename, _) = QFileDialog.getSaveFileName(
            self.view, "Save reviewed ladder events", str(default_path), "CSV files (*.csv)"
        )
        if not filename:
            return
        try:
            output = self.view.use_cases.export_reviewed(
                self._reviewed_events(), Path(filename), combined=self.view.controller._is_dual_mode()
            )
        except Exception as exc:
            QMessageBox.critical(self.view, "Could not save reviewed events", str(exc))
            return
        self.view.status_label.setText(f"Reviewed ladder events saved to {output.name}.")
        QMessageBox.information(self.view, "Ladder results saved", str(output))

    def _event_selected(
        self, current_row: int, _current_column: int, _previous_row: int, _previous_column: int
    ) -> None:
        if 0 <= current_row < len(self.view.state.events):
            event = self.view.state.events[current_row]
            self.view.state.active_preview_view = event.view
            frame_count = self.view.state.video_frame_counts.get(event.view, 0)
            self.view.frame_slider.setRange(0, max(0, frame_count - 1))
            self.view.frame_slider.setValue(event.peak_frame)
            self.view.video_review._show_video_frame(event.peak_frame)


def build_ladder_events(self, review_layout):
    table_box = QGroupBox("Detected events — select a row to inspect its deepest frame")
    table_layout = QVBoxLayout(table_box)
    self.events_table = QTableWidget(0, 9)
    self.events_table.setHorizontalHeaderLabels(
        ["Use", "View", "Body part", "Peak", "Start", "End", "Depth (px)", "Duration (s)", "Classification"]
    )
    self.events_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    self.events_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    self.events_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    header = self.events_table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    table_layout.addWidget(self.events_table)
    review_layout.addWidget(table_box, 3)
    export_row = QHBoxLayout()
    export_note = QLabel("Uncheck false detections; classify accepted events as footfall, slip, or fall.")
    export_note.setObjectName("MutedLabel")
    export_note.setWordWrap(True)
    self.save_button = QPushButton("Save reviewed results…")
    self.save_button.setEnabled(False)
    export_row.addWidget(export_note, 1)
    export_row.addWidget(self.save_button)
    review_layout.addLayout(export_row)
    controls_scroll = QScrollArea()
    controls_scroll.setObjectName("LadderControlsScroll")
    controls_scroll.setWidgetResizable(True)
    controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    return controls_scroll
