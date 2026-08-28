"""Dialogs used to pair multiview CSVs and map DeepLabCut labels."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.gait_analysis.pairing import (
    build_view_csv_sets,
    suggest_view_set,
)
from dlc_gait_assembly.gui.gait_analysis.settings import (
    BOTTOM_VIEW_LABELS,
    FORELIMB_BOTTOM_VIEW_LABELS,
    FORELIMB_SIDE_VIEW_LABELS,
    SIDE_VIEW_LABELS,
    auto_bodypart_label,
    raw_label_for_standard,
)
from dlc_gait_assembly.gui.shared.interaction import set_tooltip
from dlc_gait_assembly.services.pipeline.alma import AlmaViewCsvSet, StrokeStudyMetadata


class CsvPairingDialog(QDialog):
    def __init__(self, csv_files: list[Path], initial_sets: list[AlmaViewCsvSet], parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV pairing")
        self.resize(980, 520)
        self._csv_files = list(csv_files)
        self._rows: list[dict[str, object]] = []
        self._pairings: list[AlmaViewCsvSet] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._row_container = QWidget()
        self._row_layout = QVBoxLayout(self._row_container)
        self._row_layout.setContentsMargins(0, 0, 0, 0)
        self._row_layout.setSpacing(8)
        scroll.setWidget(self._row_container)
        layout.addWidget(scroll, 1)

        source_sets = list(initial_sets)
        if not source_sets and len(self._csv_files) >= 3:
            source_sets = [suggest_view_set(self._csv_files)]
        for view_set in source_sets:
            self._add_row(view_set)
        if not self._rows:
            self._add_row()

        action_row = QHBoxLayout()
        self.add_set_button = QPushButton("Add CSV set")
        self.auto_pair_button = QPushButton("Use filename pairs")
        set_tooltip(self.add_set_button, "Add another left/right/bottom CSV set.")
        set_tooltip(
            self.auto_pair_button,
            "Replace manual rows with pairs inferred from CSV filenames.",
        )
        self.add_set_button.clicked.connect(lambda: self._add_row())
        self.auto_pair_button.clicked.connect(self._use_filename_pairs)
        action_row.addWidget(self.add_set_button)
        action_row.addWidget(self.auto_pair_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(theme.workspace_stylesheet("CsvPairingDialog", ""))

    def _add_row(self, view_set: AlmaViewCsvSet | None = None) -> None:
        frame = QFrame()
        frame.setObjectName("PairingRow")
        row_layout = QGridLayout(frame)
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setHorizontalSpacing(10)
        row_layout.setVerticalSpacing(6)
        name_edit = QLineEdit(
            view_set.name if view_set is not None else f"set_{len(self._rows) + 1}"
        )
        left_combo = self._path_combo(view_set.left_csv if view_set is not None else None)
        right_combo = self._path_combo(view_set.right_csv if view_set is not None else None)
        bottom_combo = self._path_combo(view_set.bottom_csv if view_set is not None else None)
        metadata = view_set.metadata if view_set is not None else None
        animal_edit = QLineEdit(metadata.animal_id if metadata is not None else "")
        group_edit = QLineEdit(metadata.group if metadata is not None else "")
        sex_edit = QLineEdit(metadata.sex if metadata is not None else "")
        timepoint_edit = QLineEdit(metadata.timepoint if metadata is not None else "")
        trial_edit = QLineEdit(metadata.trial if metadata is not None else "")
        session_edit = QLineEdit(metadata.session_id if metadata is not None else "")
        lesion_combo = QComboBox()
        lesion_combo.addItems(["unknown", "left", "right"])
        lesion_combo.setCurrentText(metadata.lesion_hemisphere if metadata is not None else "unknown")
        remove_button = QPushButton("Remove")
        row_layout.addWidget(QLabel("CSV set name"), 0, 0)
        row_layout.addWidget(name_edit, 0, 1, 1, 3)
        row_layout.addWidget(remove_button, 0, 4)
        row_layout.addWidget(QLabel("Left side view CSV"), 1, 0)
        row_layout.addWidget(left_combo, 1, 1)
        row_layout.addWidget(QLabel("Right side view CSV"), 1, 2)
        row_layout.addWidget(right_combo, 1, 3)
        row_layout.addWidget(QLabel("Bottom view CSV"), 2, 0)
        row_layout.addWidget(bottom_combo, 2, 1, 1, 3)
        row_layout.addWidget(QLabel("Animal ID"), 3, 0)
        row_layout.addWidget(animal_edit, 3, 1)
        row_layout.addWidget(QLabel("Session ID"), 3, 2)
        row_layout.addWidget(session_edit, 3, 3)
        row_layout.addWidget(QLabel("Group"), 4, 0)
        row_layout.addWidget(group_edit, 4, 1)
        row_layout.addWidget(QLabel("Time point"), 4, 2)
        row_layout.addWidget(timepoint_edit, 4, 3)
        row_layout.addWidget(QLabel("Sex"), 5, 0)
        row_layout.addWidget(sex_edit, 5, 1)
        row_layout.addWidget(QLabel("Trial"), 5, 2)
        row_layout.addWidget(trial_edit, 5, 3)
        row_layout.addWidget(QLabel("Lesion hemisphere"), 6, 0)
        row_layout.addWidget(lesion_combo, 6, 1)
        row = {
            "frame": frame,
            "name": name_edit,
            "left": left_combo,
            "right": right_combo,
            "bottom": bottom_combo,
            "animal_id": animal_edit,
            "group": group_edit,
            "sex": sex_edit,
            "timepoint": timepoint_edit,
            "trial": trial_edit,
            "session_id": session_edit,
            "lesion_hemisphere": lesion_combo,
        }
        remove_button.clicked.connect(lambda _checked=False, row=row: self._remove_row(row))
        self._rows.append(row)
        self._row_layout.addWidget(frame)

    def _remove_row(self, row: dict[str, object]) -> None:
        if row not in self._rows:
            return
        self._rows.remove(row)
        frame = row["frame"]
        if isinstance(frame, QWidget):
            frame.setParent(None)
            frame.deleteLater()
        if not self._rows:
            self._add_row()

    def _path_combo(self, selected: Path | None = None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("(none)", "")
        selected_text = str(Path(selected).expanduser().resolve()) if selected is not None else ""
        for path in self._csv_files:
            combo.addItem(_csv_choice_label(path, self._csv_files), str(path))
        if selected_text:
            index = combo.findData(selected_text)
            if index >= 0:
                combo.setCurrentIndex(index)
        return combo

    def _use_filename_pairs(self) -> None:
        view_sets, _errors = build_view_csv_sets(self._csv_files)
        for row in list(self._rows):
            self._remove_row(row)
        for view_set in view_sets:
            self._add_row(view_set)
        if not self._rows:
            self._add_row()

    def accept(self) -> None:
        try:
            self._pairings = self._collect_pairings()
        except ValueError as exc:
            QMessageBox.warning(self, "CSV pairing incomplete", str(exc))
            return
        super().accept()

    def _collect_pairings(self) -> list[AlmaViewCsvSet]:
        pairings: list[AlmaViewCsvSet] = []
        used_paths: dict[Path, str] = {}
        used_names: set[str] = set()
        for index, row in enumerate(self._rows, start=1):
            name_edit = row["name"]
            left_combo = row["left"]
            right_combo = row["right"]
            bottom_combo = row["bottom"]
            animal_edit = row["animal_id"]
            group_edit = row["group"]
            sex_edit = row["sex"]
            timepoint_edit = row["timepoint"]
            trial_edit = row["trial"]
            session_edit = row["session_id"]
            lesion_combo = row["lesion_hemisphere"]
            if not isinstance(name_edit, QLineEdit) or not isinstance(left_combo, QComboBox):
                continue
            if not isinstance(right_combo, QComboBox) or not isinstance(bottom_combo, QComboBox):
                continue
            name = name_edit.text().strip() or f"set_{index}"
            selected = {
                "left": _combo_path(left_combo),
                "right": _combo_path(right_combo),
                "bottom": _combo_path(bottom_combo),
            }
            if not any(selected.values()):
                continue
            missing = [view for view, path in selected.items() if path is None]
            if missing:
                raise ValueError(f"{name}: missing " + ", ".join(missing) + " CSV.")
            row_paths = [path for path in selected.values() if path is not None]
            if len(set(row_paths)) != len(row_paths):
                raise ValueError(f"{name}: each view must use a different CSV file.")
            if name in used_names:
                raise ValueError(f"{name}: CSV set names must be unique.")
            used_names.add(name)
            for view, path in selected.items():
                if path is None:
                    continue
                previous = used_paths.get(path)
                if previous is not None:
                    raise ValueError(f"{path.name} is already assigned to {previous}.")
                used_paths[path] = f"{name} {view}"
            pairings.append(
                AlmaViewCsvSet(
                    name=name,
                    left_csv=selected["left"],
                    right_csv=selected["right"],
                    bottom_csv=selected["bottom"],
                    metadata=StrokeStudyMetadata(
                        animal_id=animal_edit.text().strip(),
                        group=group_edit.text().strip(),
                        sex=sex_edit.text().strip(),
                        lesion_hemisphere=lesion_combo.currentText(),
                        timepoint=timepoint_edit.text().strip(),
                        trial=trial_edit.text().strip(),
                        session_id=session_edit.text().strip(),
                    ),
                )
            )
        if not pairings:
            raise ValueError("Create at least one complete left/right/bottom CSV set.")
        return pairings

    def pairings(self) -> list[AlmaViewCsvSet]:
        return list(self._pairings)


class LabelMappingDialog(QDialog):
    def __init__(
        self,
        view_set: AlmaViewCsvSet,
        labels_by_view: dict[str, list[str]],
        existing_mapping: dict[str, dict[str, str]],
        parent=None,
        *,
        include_forelimb: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Label matching: {view_set.name}")
        self.resize(820, 560)
        self._combos: dict[tuple[str, str], QComboBox] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)
        side_labels = SIDE_VIEW_LABELS + (FORELIMB_SIDE_VIEW_LABELS if include_forelimb else ())
        bottom_labels = BOTTOM_VIEW_LABELS + (FORELIMB_BOTTOM_VIEW_LABELS if include_forelimb else ())
        for view, title, csv_path, required_labels in (
            ("left", "Left side view", view_set.left_csv, side_labels),
            ("right", "Right side view", view_set.right_csv, side_labels),
            ("bottom", "Bottom view", view_set.bottom_csv, bottom_labels),
        ):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(8, 8, 8, 8)
            page_layout.setSpacing(10)
            file_label = QLabel(csv_path.name)
            file_label.setObjectName("MutedLabel")
            page_layout.addWidget(file_label)
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            raw_labels = labels_by_view.get(view, [])
            choices = ["(none)", *raw_labels]
            existing_for_view = existing_mapping.get(view, {})
            for row, standard_label in enumerate(required_labels):
                combo = QComboBox()
                combo.addItems(choices)
                selected = raw_label_for_standard(existing_for_view, standard_label)
                if selected not in raw_labels:
                    selected = auto_bodypart_label(raw_labels, standard_label)
                combo.setCurrentText(selected or "(none)")
                set_tooltip(combo, f"Raw DLC label to use as {standard_label}.")
                self._combos[(view, standard_label)] = combo
                grid.addWidget(QLabel(standard_label), row, 0)
                grid.addWidget(combo, row, 1)
            page_layout.addLayout(grid)
            page_layout.addStretch(1)
            tabs.addTab(page, title)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(theme.workspace_stylesheet("LabelMappingDialog", ""))

    def mapping(self) -> dict[str, dict[str, str]]:
        mapping: dict[str, dict[str, str]] = {"left": {}, "right": {}, "bottom": {}}
        for (view, standard_label), combo in self._combos.items():
            raw_label = combo.currentText()
            if raw_label and raw_label != "(none)":
                mapping[view][raw_label] = standard_label
        return {view: value for view, value in mapping.items() if value}


def _combo_path(combo: QComboBox) -> Path | None:
    value = combo.currentData()
    return Path(str(value)) if value else None


def _csv_choice_label(path: Path, all_paths: list[Path]) -> str:
    if sum(1 for candidate in all_paths if candidate.name == path.name) <= 1:
        return path.name
    return f"{path.name}  ({path.parent.name})"
