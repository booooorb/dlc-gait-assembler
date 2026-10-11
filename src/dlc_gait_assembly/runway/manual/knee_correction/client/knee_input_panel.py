"""Select and present matched CSV/H5 datasets and optional source videos."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_dataset_pairing import pair_coordinate_files


class KneeInputPanel:
    """KneeInputPanel operates on its explicitly supplied KneeCorrectionWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_files(self) -> None:
        (paths, _) = QFileDialog.getOpenFileNames(
            self.view,
            "Choose paired DeepLabCut labels and video",
            str(self.view._project_root),
            "Knee correction inputs (*.avi *.csv *.h5 *.m4v *.mkv *.mov *.mp4 *.mpeg *.mpg *.webm);;All files (*)",
        )
        self._add_paths([Path(path) for path in paths])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self.view, "Choose folder containing paired labels and videos", str(self.view._project_root)
        )
        if folder:
            directory = Path(folder)
            self._add_paths(self.view.use_cases.input_files(directory))

    def _add_paths(self, paths: list[Path]) -> None:
        known = {str(path) for path in self.view.state.selected_paths}
        for path in paths:
            resolved = path.expanduser().resolve()
            if self.view.use_cases.accepts_input(resolved):
                if str(resolved) not in known:
                    self.view.state.selected_paths.append(resolved)
                    known.add(str(resolved))
        self._refresh_pairs()

    def _refresh_pairs(self) -> None:
        self.view.state.pairs = pair_coordinate_files(self.view.state.selected_paths)
        self.view.pair_table.clear()
        error_brush = QBrush(QColor(theme.STATUS_ERROR))
        for pair in self.view.state.pairs:
            csv_text = pair.csv_path.name if pair.csv_path is not None else "Missing"
            h5_text = pair.h5_path.name if pair.h5_path is not None else "Missing"
            video_text = pair.video_path.name if pair.video_path is not None else "Missing"
            item = QTreeWidgetItem([pair.stem, csv_text, h5_text, video_text, pair.status])
            item.setData(0, Qt.UserRole, [str(path) for path in (*pair.csv_paths, *pair.h5_paths, *pair.video_paths)])
            if not pair.is_paired:
                for column in range(5):
                    item.setForeground(column, error_brush)
            self.view.pair_table.addTopLevelItem(item)
        self._refresh_label_choices()
        self.view.preview_controller._invalidate_preview()
        self.view.controller._update_run_state()
        self.view.preview_controller._maybe_generate_previews()

    def _refresh_label_choices(self) -> None:
        previous_knee = self.view.knee_label_combo.currentData()
        previous_hip = self.view.hip_label_combo.currentData()
        previous_ankle = self.view.ankle_label_combo.currentData()
        labels: list[str] = []
        for pair in self.view.state.pairs:
            if pair.csv_path is None:
                continue
            try:
                for label in self.view.use_cases.bodyparts(pair.csv_path):
                    if label not in labels:
                        labels.append(label)
            except ValueError:
                continue
        combo_settings = (
            (self.view.knee_label_combo, "Auto-detect labels containing 'knee'", previous_knee),
            (self.view.hip_label_combo, "Auto-detect matching hip", previous_hip),
            (self.view.ankle_label_combo, "Auto-detect matching ankle", previous_ankle),
        )
        for combo, automatic_text, previous in combo_settings:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(automatic_text, None)
            for label in labels:
                combo.addItem(label, label)
            if previous in labels:
                combo.setCurrentIndex(labels.index(previous) + 1)
            combo.setEnabled(bool(labels))
            combo.blockSignals(False)

    def _remove_selected(self) -> None:
        removed = {path for item in self.view.pair_table.selectedItems() for path in item.data(0, Qt.UserRole) or []}
        self.view.state.selected_paths = [path for path in self.view.state.selected_paths if str(path) not in removed]
        self._refresh_pairs()

    def _clear(self) -> None:
        self.view.state.selected_paths.clear()
        self.view.preview_controller._release_preview_capture()
        self.view.state.preview_media_path = None
        self.view._preview_static_image = None
        self.view.state.preview_video_frame_count = 0
        self._refresh_pairs()
        self.view.log.clear()


def build_knee_inputs(self):
    files_box = QGroupBox("Paired DeepLabCut labels + video")
    files_layout = QVBoxLayout(files_box)
    toolbar = QHBoxLayout()
    self.add_files_button = QPushButton("Add CSV + H5 + video")
    self.add_folder_button = QPushButton("Add folder")
    self.remove_button = QPushButton("Remove")
    self.remove_button.setObjectName("RemoveButton")
    self.clear_button = QPushButton("Clear")
    self.clear_button.setObjectName("ClearButton")
    toolbar.addWidget(self.add_files_button)
    toolbar.addWidget(self.add_folder_button)
    toolbar.addStretch(1)
    toolbar.addWidget(self.remove_button)
    toolbar.addWidget(self.clear_button)
    files_layout.addLayout(toolbar)
    self.pair_table = QTreeWidget()
    self.pair_table.setObjectName("KneePairTable")
    self.pair_table.setHeaderLabels(["Dataset", "CSV", "H5", "Video", "Status"])
    self.pair_table.setRootIsDecorated(False)
    self.pair_table.setAlternatingRowColors(False)
    self.pair_table.setSelectionMode(QTreeWidget.ExtendedSelection)
    self.pair_table.header().setStretchLastSection(False)
    self.pair_table.header().setSectionResizeMode(0, QHeaderView.Stretch)
    self.pair_table.header().setSectionResizeMode(1, QHeaderView.Stretch)
    self.pair_table.header().setSectionResizeMode(2, QHeaderView.Stretch)
    self.pair_table.header().setSectionResizeMode(3, QHeaderView.Stretch)
    self.pair_table.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
    files_layout.addWidget(self.pair_table, 1)
    return files_box
