"""Assign coordinate files and source videos independently of their filenames."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import CoordinateFilePair
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS


class KneePairingDialog(QDialog):
    def __init__(self, paths: list[Path], pairs: list[CoordinateFilePair], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize knee correction pairings")
        self.resize(960, 480)
        self._paths = sorted(set(paths))
        self._rows = []
        layout = QVBoxLayout(self)
        explanation = QLabel("Choose one H5 and source video for each CSV. Filenames and folders can differ.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["CSV", "H5", "Video", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.exclude_unassigned = QCheckBox("Remove unassigned H5 and video files from the input list")
        self.exclude_unassigned.toggled.connect(self._refresh_status)
        layout.addWidget(self.exclude_unassigned)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Use these pairings")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for csv in (path for path in self._paths if path.suffix.lower() == ".csv"):
            initial = next((pair for pair in pairs if csv in pair.csv_paths), None)
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            item = QTableWidgetItem(csv.name)
            item.setToolTip(str(csv))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row_index, 0, item)
            h5 = self._path_combo({".h5"}, initial.h5_path if initial else None)
            video = self._path_combo(VIDEO_EXTENSIONS, initial.video_path if initial else None)
            self.table.setCellWidget(row_index, 1, h5)
            self.table.setCellWidget(row_index, 2, video)
            status = QTableWidgetItem()
            status.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row_index, 3, status)
            self._rows.append((csv, h5, video, status))
            h5.currentIndexChanged.connect(self._refresh_status)
            video.currentIndexChanged.connect(self._refresh_status)
        self._refresh_status()
        self.table.resizeColumnToContents(0)
        for column in (1, 2):
            width = max(
                (combo.fontMetrics().horizontalAdvance(combo.itemText(index)) + 50
                 for row in self._rows for combo in (row[column],) for index in range(combo.count())),
                default=200,
            )
            self.table.setColumnWidth(column, max(200, width))
        self.table.resizeColumnToContents(3)

    def _path_combo(self, extensions, selected):
        combo = QComboBox()
        combo.setMinimumContentsLength(12)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.addItem("Choose file…", None)
        candidates = [path for path in self._paths if path.suffix.lower() in extensions]
        counts = Counter(path.name for path in candidates)
        for path in candidates:
            label = f"{path.name} ({path.parent})" if counts[path.name] > 1 else path.name
            combo.addItem(label, str(path))
            combo.setItemData(combo.count() - 1, str(path), Qt.ToolTipRole)
        if selected is not None:
            combo.setCurrentIndex(max(0, combo.findData(str(selected))))
        popup_width = max(
            (combo.fontMetrics().horizontalAdvance(combo.itemText(index)) + 40 for index in range(combo.count())),
            default=200,
        )
        combo.view().setMinimumWidth(min(popup_width, self.screen().availableGeometry().width() - 80))
        return combo

    def _unused_paths(self):
        used = {path for csv, h5, video, _ in self._rows for path in (csv, selected_path(h5), selected_path(video))}
        return [path for path in self._paths if path not in used]

    def _refresh_status(self, *_args):
        assignments = Counter(
            selected_path(combo) for _, h5, video, _ in self._rows for combo in (h5, video)
            if selected_path(combo) is not None
        )
        names = Counter(csv.stem.casefold() for csv, _, _, _ in self._rows)
        ready = 0
        for csv, h5, video, status in self._rows:
            for combo in (h5, video):
                path = selected_path(combo)
                combo.setToolTip(str(path) if path else "Choose file…")
            problems = []
            if selected_path(h5) is None:
                problems.append("Choose H5")
            if selected_path(video) is None:
                problems.append("Choose video")
            if any(assignments[selected_path(combo)] > 1 for combo in (h5, video)):
                problems.append("File used more than once")
            if names[csv.stem.casefold()] > 1:
                problems.append("CSV names would overwrite outputs")
            status.setText("; ".join(problems) or "Ready")
            ready += not problems
        unused = self._unused_paths()
        self.summary_label.setText(f"{ready} of {len(self._rows)} datasets ready · {len(unused)} unassigned files")
        self.summary_label.setToolTip("\n".join(str(path) for path in unused))
        self.exclude_unassigned.setVisible(bool(unused))
        self.buttons.button(QDialogButtonBox.Save).setEnabled(
            bool(self._rows) and ready == len(self._rows) and (not unused or self.exclude_unassigned.isChecked())
        )

    def accept(self):
        self._refresh_status()
        if self.buttons.button(QDialogButtonBox.Save).isEnabled():
            super().accept()

    def pairings(self) -> list[CoordinateFilePair]:
        return [
            CoordinateFilePair(
                directory=csv.parent, stem=csv.stem, csv_paths=(csv,),
                h5_paths=(selected_path(h5),), video_paths=(selected_path(video),),
            )
            for csv, h5, video, _ in self._rows
        ]

    def excluded_paths(self) -> list[Path]:
        return self._unused_paths() if self.exclude_unassigned.isChecked() else []


def selected_path(combo: QComboBox) -> Path | None:
    value = combo.currentData()
    return Path(value) if value else None
