"""Present coordinate inputs, matched recordings, and file/folder selection actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import (
    build_view_csv_sets,
    build_view_pair_rows,
    path_name,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    BOTTOM_VIEW_LABELS,
    FORELIMB_SIDE_VIEW_LABELS,
    MULTI_SIDE_VIEW_MODE_LABEL,
    SIDE_VIEW_LABELS,
    STANDARD_BODYPARTS,
    auto_bodypart_label,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_view_pairing_dialog import CsvPairingDialog
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitInputPanel:
    """GaitInputPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _add_file(self) -> None:
        (filenames, _) = QFileDialog.getOpenFileNames(
            self.view,
            "Select left/right/bottom coordinate CSVs",
            str(self.view._project_root),
            "CSV files (*.csv);;All files (*)",
        )
        if filenames:
            self._add_csv_paths([Path(filename) for filename in filenames])

    def _add_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self.view, "Select folder containing CSV files", str(self.view._project_root)
        )
        if directory:
            self._add_csv_paths(sorted(self.view.analysis.inputs.csv_files(directory)))

    def _add_csv_paths(self, paths: list[Path]) -> None:
        previous_count = len(self.view.state.selected_files)
        existing = {str(path) for path in self.view.state.selected_files}
        for path in paths:
            resolved = path.expanduser().resolve()
            if resolved.suffix.lower() != ".csv" or str(resolved) in existing:
                continue
            self.view.state.selected_files.append(resolved)
            self.view.file_list.addItem(str(resolved))
            existing.add(str(resolved))
        if self.view.state.selected_files and self.view.file_list.currentRow() < 0:
            self.view.file_list.setCurrentRow(0)
        self._refresh_view_sets()
        if self.view.state.selected_files and (not self.view.state.raw_bodyparts):
            self.view.mapping._load_bodypart_mapping_from_first_file()
        if len(self.view.state.selected_files) != previous_count:
            self.view.controller._invalidate_stickplot_preview()
        self.view.controller._update_run_state()

    def _clear_files(self) -> None:
        self.view.state.selected_files.clear()
        self.view.file_list.clear()
        self.view.state.view_sets = []
        self.view.state.view_set_errors = []
        self.view.state.manual_view_sets = None
        self.view.state.raw_bodyparts = []
        self.view.mapping._refresh_bodypart_mapping_choices()
        self.view.view_set_table.clear()
        self.view.view_set_status_label.setText("Add matched left, right, and bottom CSVs.")
        self.view.rustlab_status_label.setText("RustLab1 needs paired left, right, and bottom CSVs.")
        self.view.mapping_status_label.setText("Add a complete CSV view set to detect labels.")
        self.view.controller._invalidate_stickplot_preview(
            "Select matched left/right/bottom CSVs, then generate a RustLab1 stride preview."
            if self.view.setup._is_rustlab1_workflow()
            else "Select left/right/bottom CSVs, then generate a stick-plot preview."
        )
        self.view.controller._update_run_state()

    def _refresh_view_sets(self) -> None:
        if self.view.state.manual_view_sets is not None:
            selected = {path for path in self.view.state.selected_files}
            self.view.state.manual_view_sets = [
                view_set
                for view_set in self.view.state.manual_view_sets
                if view_set.left_csv in selected
                and view_set.right_csv in selected
                and (view_set.bottom_csv in selected)
            ]
            self.view.state.view_sets = list(self.view.state.manual_view_sets)
            used = {
                path
                for group in self.view.state.view_sets
                for path in (group.left_csv, group.right_csv, group.bottom_csv)
            }
            _, errors = build_view_csv_sets([path for path in self.view.state.selected_files if path not in used])
            self.view.state.view_set_errors = errors
        else:
            (self.view.state.view_sets, self.view.state.view_set_errors) = build_view_csv_sets(
                self.view.state.selected_files
            )
        self._refresh_view_set_table()
        if self.view.state.manual_view_sets is not None and self.view.state.view_sets:
            suffix = "" if len(self.view.state.view_sets) == 1 else "s"
            self.view.view_set_status_label.setText(
                f"Manual pairing: {len(self.view.state.view_sets)} complete CSV set{suffix}."
            )
            unassigned_count = len(set(self.view.state.selected_files) - used)
            if unassigned_count:
                self.view.view_set_status_label.setText(
                    self.view.view_set_status_label.text()
                    + f" {unassigned_count} unassigned CSVs — review pairings to include them."
                )
            self.view.rustlab_status_label.setText(
                f"RustLab1 ready for {len(self.view.state.view_sets)} manually paired CSV set{suffix}."
            )
        elif self.view.state.manual_view_sets is not None:
            self.view.view_set_status_label.setText("Manual pairing has no complete left/right/bottom CSV sets.")
            self.view.rustlab_status_label.setText("RustLab1 waiting for complete manual CSV pairs.")
        elif self.view.state.view_sets and (not self.view.state.view_set_errors):
            suffix = "" if len(self.view.state.view_sets) == 1 else "s"
            self.view.view_set_status_label.setText(
                f"Ready: {len(self.view.state.view_sets)} complete left/right/bottom CSV set{suffix}."
            )
            self.view.rustlab_status_label.setText(
                f"RustLab1 ready for {len(self.view.state.view_sets)} paired CSV set{suffix}."
            )
        elif self.view.state.view_sets:
            self.view.view_set_status_label.setText(
                f"{len(self.view.state.view_sets)} complete set(s); " + " ".join(self.view.state.view_set_errors)
            )
            self.view.rustlab_status_label.setText(
                "RustLab1 ready for complete paired sets; unresolved rows will be ignored."
            )
        elif self.view.state.selected_files:
            self.view.view_set_status_label.setText(self._multiview_requirement_message())
            self.view.rustlab_status_label.setText("RustLab1 waiting for complete left/right/bottom pairs.")
        else:
            self.view.view_set_status_label.setText("Add matched left, right, and bottom CSVs.")
            self.view.rustlab_status_label.setText("RustLab1 needs paired left, right, and bottom CSVs.")

    def _refresh_view_set_table(self) -> None:
        current = self.view.view_set_table.currentItem()
        selected_name = current.text(0) if current is not None else None
        if self.view.state.manual_view_sets is not None:
            rows = [
                {
                    "name": view_set.name,
                    "left": view_set.left_csv,
                    "right": view_set.right_csv,
                    "bottom": view_set.bottom_csv,
                    "status": "Manual",
                }
                for view_set in self.view.state.view_sets
            ]
            used = {
                path
                for group in self.view.state.view_sets
                for path in (group.left_csv, group.right_csv, group.bottom_csv)
            }
            for row in build_view_pair_rows([path for path in self.view.state.selected_files if path not in used]):
                rows.append({**row, "status": "Unassigned · " + row["status"]})
        else:
            rows = build_view_pair_rows(self.view.state.selected_files)
        self.view.view_set_table.blockSignals(True)
        self.view.view_set_table.clear()
        complete_index = 0
        first_ready_item = None
        selected_item = None
        for row in rows:
            item = QTreeWidgetItem(
                [
                    row["name"],
                    path_name(row.get("left")),
                    path_name(row.get("right")),
                    path_name(row.get("bottom")),
                    row["status"],
                ]
            )
            for column, view in enumerate(("left", "right", "bottom"), start=1):
                item.setToolTip(column, str(row.get(view) or row["status"]))
            if row["status"] in {"Ready", "Manual"}:
                item.setData(0, Qt.UserRole, complete_index)
                complete_index += 1
                if first_ready_item is None:
                    first_ready_item = item
                if row["name"] == selected_name:
                    selected_item = item
            else:
                item.setData(0, Qt.UserRole, -1)
            self.view.view_set_table.addTopLevelItem(item)
        if first_ready_item is not None:
            self.view.view_set_table.setCurrentItem(selected_item or first_ready_item)
        self.view.view_set_table.blockSignals(False)

    def _multiview_requirement_message(self) -> str:
        details = " ".join(self.view.state.view_set_errors)
        base = "Gait analysis now requires matched left, right, and bottom/down CSV files."
        if details:
            return f"{base} {details}"
        return base

    def _open_csv_pairing_dialog(self) -> None:
        if not self.view.state.selected_files:
            QMessageBox.information(self.view, "CSV files required", "Add CSV files before editing CSV pairing.")
            return
        dialog = CsvPairingDialog(
            self.view.state.selected_files,
            self.view.state.manual_view_sets
            if self.view.state.manual_view_sets is not None
            else self.view.state.view_sets,
            self.view,
        )
        selected = self.view.view_set_table.currentItem()
        if selected is not None:
            for index, row in enumerate(dialog._rows):
                if row["name"].text() == selected.text(0):
                    dialog.table.setCurrentCell(index, 0)
                    break
        if dialog.exec() != QDialog.Accepted:
            return
        self.view.state.manual_view_sets = dialog.pairings()
        self._refresh_view_sets()
        if self.view.state.view_sets:
            self.view.controller._select_view_set_row(0)
            self.view.controller._invalidate_stickplot_preview(
                f"Generate a stick-plot preview for {self.view.state.view_sets[0].name}."
            )
        else:
            self.view.controller._invalidate_stickplot_preview(self._multiview_requirement_message())
        self.view.controller._update_run_state()

    def _preview_inputs(self) -> tuple[tuple[str, Path], ...]:
        if self._is_three_view_mode():
            view_set = self._selected_view_set()
            if view_set is not None:
                return (("Left", view_set.left_csv), ("Right", view_set.right_csv), ("Bottom", view_set.bottom_csv))
            return ()
        return (("Single", self._selected_preview_file()),)

    def _selected_preview_file(self) -> Path:
        view_set = self._selected_view_set()
        if self._is_three_view_mode() and view_set is not None:
            return view_set.alma_csv
        row = self.view.file_list.currentRow()
        if 0 <= row < len(self.view.state.selected_files):
            return self.view.state.selected_files[row]
        return self.view.state.selected_files[0]

    def _has_valid_inputs(self) -> bool:
        if self._is_three_view_mode():
            return self._selected_view_set() is not None
        return bool(self.view.state.selected_files)

    def _has_valid_view_sets(self) -> bool:
        return bool(self.view.state.view_sets)

    def _is_three_view_mode(self) -> bool:
        return self.view.input_mode_combo.currentText() == MULTI_SIDE_VIEW_MODE_LABEL

    def _input_requirement_message(self) -> str:
        if self._is_three_view_mode():
            return self._multiview_requirement_message()
        return "Single side view mode requires at least one side-view CSV."

    def _selected_view_set(self) -> AlmaViewCsvSet | None:
        item = self.view.view_set_table.currentItem()
        if item is not None:
            index = item.data(0, Qt.UserRole)
            if isinstance(index, int) and 0 <= index < len(self.view.state.view_sets):
                return self.view.state.view_sets[index]
            return None
        if self.view.state.view_sets:
            return self.view.state.view_sets[0]
        return None

    def _missing_rustlab1_bodyparts(self, view_set: AlmaViewCsvSet, settings: RustLab1StandaloneSettings) -> list[str]:
        include_forelimb = settings.limb_scope == "Hindlimb + Forelimb"
        side_labels = ("ankle", "toe", "hip", "iliac crest")
        if include_forelimb:
            side_labels += FORELIMB_SIDE_VIEW_LABELS
        bottom_labels = list(BOTTOM_VIEW_LABELS)
        reference_label = {
            "d-back-left": "back left",
            "d-back-right": "back right",
            "d-front-left": "front left",
            "d-front-right": "front right",
        }[settings.reference_paw]
        if reference_label not in bottom_labels:
            bottom_labels.append(reference_label)
        missing = []
        view_mapping = settings.view_bodypart_mapping or {}
        for view, csv_path, required_labels in (
            ("left", view_set.left_csv, side_labels),
            ("right", view_set.right_csv, side_labels),
            ("bottom", view_set.bottom_csv, tuple(bottom_labels)),
        ):
            try:
                raw_bodyparts = self.view.analysis.inputs.bodyparts(csv_path)
            except Exception:
                missing.extend(f"{view} {label}" for label in required_labels)
                continue
            mapped_bodyparts = set((view_mapping.get(view) or {}).values())
            for standard_bodypart in required_labels:
                if standard_bodypart in mapped_bodyparts:
                    continue
                if auto_bodypart_label(raw_bodyparts, standard_bodypart) is None:
                    missing.append(f"{view} {standard_bodypart}")
        if settings.calibration_method == "reference":
            reference_labels = tuple(settings.reference_segment.split("_"))
            reference_available = False
            for view, csv_path in (("left", view_set.left_csv), ("right", view_set.right_csv)):
                try:
                    raw_bodyparts = self.view.analysis.inputs.bodyparts(csv_path)
                except Exception:
                    continue
                mapped_bodyparts = set((view_mapping.get(view) or {}).values())
                if all(
                    label in mapped_bodyparts or auto_bodypart_label(raw_bodyparts, label) is not None
                    for label in reference_labels
                ):
                    reference_available = True
                    break
            if not reference_available:
                missing.append("left or right reference segment " + settings.reference_segment)
        return missing

    def _missing_required_bodyparts(self, settings: AlmaSettings) -> list[str]:
        if self._is_three_view_mode():
            view_set = self._selected_view_set()
            if view_set is None:
                return []
            missing: list[str] = []
            view_mapping = settings.view_bodypart_mapping or {}
            include_forelimb = settings.limb_scope == "Hindlimb + Forelimb"
            side_labels = SIDE_VIEW_LABELS + (FORELIMB_SIDE_VIEW_LABELS if include_forelimb else ())
            bottom_labels = BOTTOM_VIEW_LABELS
            for view, csv_path, required_labels in (
                ("left", view_set.left_csv, side_labels),
                ("right", view_set.right_csv, side_labels),
                ("bottom", view_set.bottom_csv, bottom_labels),
            ):
                try:
                    raw_bodyparts = self.view.analysis.inputs.bodyparts(csv_path)
                except Exception:
                    missing.extend(f"{view} {label}" for label in required_labels)
                    continue
                mapped_bodyparts = set((view_mapping.get(view) or {}).values())
                for standard_bodypart in required_labels:
                    if standard_bodypart in mapped_bodyparts:
                        continue
                    if auto_bodypart_label(raw_bodyparts, standard_bodypart) is None:
                        missing.append(f"{view} {standard_bodypart}")
            return missing
        if not self.view.state.raw_bodyparts:
            return []
        mapped_bodyparts = set(settings.custom_bodypart_mapping.values()) if settings.custom_bodypart_mapping else set()
        missing: list[str] = []
        for standard_bodypart in STANDARD_BODYPARTS:
            if standard_bodypart in mapped_bodyparts:
                continue
            if auto_bodypart_label(self.view.state.raw_bodyparts, standard_bodypart) is None:
                missing.append(standard_bodypart)
        return missing


def build_gait_inputs(self):
    file_box = QGroupBox("Multi-view ALMA input and output")
    self.file_box = file_box
    file_layout = QVBoxLayout(file_box)
    button_row = QHBoxLayout()
    self.add_file_button = QPushButton("Add CSVs")
    set_tooltip(self.add_file_button, "Add left, right, and bottom DeepLabCut coordinate CSVs.", "Ctrl+O")
    self.add_folder_button = QPushButton("Add folder")
    set_tooltip(self.add_folder_button, "Add every CSV in a folder and group left/right/bottom views.", "Ctrl+Shift+O")
    self.clear_files_button = QPushButton("Clear")
    set_tooltip(self.clear_files_button, "Clear the selected input CSV files.", "Ctrl+L")
    button_row.addWidget(self.add_file_button)
    button_row.addWidget(self.add_folder_button)
    button_row.addWidget(self.clear_files_button)
    file_layout.addLayout(button_row)
    self.file_list = QListWidget()
    self.file_list.setMaximumHeight(96)
    self.file_list.setVisible(False)
    file_layout.addWidget(self.file_list)
    self.view_set_table = QTreeWidget()
    self.view_set_table.setObjectName("RunwayViewSetTable")
    self.view_set_table.setHeaderLabels(["Recording", "Left side", "Right side", "Bottom", "Pairing"])
    self.view_set_table.setRootIsDecorated(False)
    self.view_set_table.setAlternatingRowColors(False)
    self.view_set_table.setMinimumHeight(128)
    self.view_set_table.setMaximumHeight(240)
    self.view_set_table.itemDoubleClicked.connect(lambda *_args: self.inputs._open_csv_pairing_dialog())
    self.view_set_table.header().setStretchLastSection(False)
    self.view_set_table.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    self.view_set_table.header().setSectionResizeMode(1, QHeaderView.Stretch)
    self.view_set_table.header().setSectionResizeMode(2, QHeaderView.Stretch)
    self.view_set_table.header().setSectionResizeMode(3, QHeaderView.Stretch)
    self.view_set_table.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
    file_layout.addWidget(self.view_set_table)
    self.view_set_status_label = QLabel("Add matched left, right, and bottom CSVs.")
    self.view_set_status_label.setObjectName("MutedLabel")
    self.view_set_status_label.setWordWrap(True)
    file_layout.addWidget(self.view_set_status_label)
    pairing_row = QHBoxLayout()
    self.edit_pairing_button = QPushButton("Review pairings…")
    self.label_matching_button = QPushButton("Label body parts...")
    set_tooltip(self.edit_pairing_button, "Assign selected CSV files to left side, right side, and bottom views.")
    set_tooltip(self.label_matching_button, "Map body-part labels for the selected left/right/bottom CSV set.")
    pairing_row.addWidget(self.edit_pairing_button)
    pairing_row.addWidget(self.label_matching_button)
    file_layout.addLayout(pairing_row)
    output_row = QHBoxLayout()
    self.output_folder_edit = QLineEdit(str(self._default_output_root()))
    self.output_folder_button = QPushButton("Save to…")
    set_tooltip(self.output_folder_edit, "Folder where ALMA gait-analysis outputs will be saved.")
    set_tooltip(self.output_folder_button, "Choose the output folder.", "Ctrl+Shift+S")
    output_row.addWidget(self.output_folder_edit, 1)
    output_row.addWidget(self.output_folder_button)
    file_layout.addLayout(output_row)
    return file_box
