"""Review recording groups in one table, with optional study details below."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import (
    build_view_pair_rows,
    csv_view_evidence,
    csv_view_from_bodyparts,
    normalized_bodyparts_by_path,
    rank_view_candidates,
)
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.theme.theme_application_styles import workspace_stylesheet

VIEWS = ("left", "right", "bottom")


class CsvPairingDialog(QDialog):
    def __init__(self, csv_files: list[Path], initial_sets: list[AlmaViewCsvSet], parent=None, *, bodyparts_by_path=None):
        super().__init__(parent)
        self.setObjectName("CsvPairingDialog")
        self.setWindowTitle("Pair recording views")
        self.resize(1120, 640)
        self.setMinimumSize(760, 420)
        self._csv_files = list(dict.fromkeys(Path(path).expanduser().resolve() for path in csv_files))
        self._choice_labels = {path: csv_choice_label(path, self._csv_files) for path in self._csv_files}
        self._rows = []
        self._pairings = []
        self._updating_pairings = True
        self._bodyparts = normalized_bodyparts_by_path(bodyparts_by_path)
        self._unused = []
        layout = QVBoxLayout(self)
        title = QLabel("One recording per row · left, right, and bottom views")
        layout.addWidget(title)
        actions = QHBoxLayout()
        self.search_edit = QLineEdit()
        set_tooltip(self.search_edit, "Filter available CSV filenames when assigning recordings to camera views.")
        self.search_edit.setPlaceholderText("Find a recording or filename…")
        self.add_set_button = QPushButton("Add recording")
        self.auto_pair_button = QPushButton("Auto-fill unmatched views")
        self.remove_button = QPushButton("Remove selected")
        self.auto_pair_button.setToolTip(
            "Match body-part labels, camera names, mouse IDs, and similar recording names. "
            "Keep existing assignments and study details; leave competing matches for review."
        )
        for widget in (self.search_edit, self.auto_pair_button, self.add_set_button, self.remove_button):
            actions.addWidget(widget)
        layout.addLayout(actions)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Recording", "Left side", "Right side", "Bottom", "Status"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(160)
        layout.addWidget(self.table, 1)
        self.unassigned_label = QLabel()
        self.unassigned_label.setWordWrap(True)
        self.unassigned_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.unassigned_label)
        self.exclude_unassigned = QCheckBox("Exclude unassigned CSVs from this workflow")
        set_tooltip(self.exclude_unassigned, 'Remove these CSVs from the input list when you apply the pairings.')
        self.exclude_unassigned.toggled.connect(self._refresh_status)
        layout.addWidget(self.exclude_unassigned)
        self.details_toggle = QToolButton()
        self.details_toggle.setText("Study details for selected recording")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.details_toggle.setArrowType(Qt.RightArrow)
        layout.addWidget(self.details_toggle)
        self.details_stack = QStackedWidget()
        self.details_stack.hide()
        layout.addWidget(self.details_stack)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Use these pairings")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.add_set_button.clicked.connect(lambda: self._add_row())
        self.remove_button.clicked.connect(self._remove_selected)
        self.auto_pair_button.clicked.connect(self._use_filename_pairs)
        self.search_edit.textChanged.connect(self._filter_rows)
        self.table.currentCellChanged.connect(self._select_details)
        self.details_toggle.toggled.connect(self._toggle_details)
        for view_set in initial_sets:
            self._add_row(view_set)
        self._use_filename_pairs()
        if not self._rows:
            self._add_row()
        self._updating_pairings = False
        self._refresh_status()
        self.setStyleSheet(workspace_stylesheet("CsvPairingDialog", ""))

    def _add_row(self, view_set=None, suggestion=None):
        index = len(self._rows)
        row = {
            "name": QLineEdit(
                view_set.name if view_set else suggestion["name"] if suggestion else f"recording_{index + 1}"
            )
        }
        self.table.insertRow(index)
        self.table.setRowHeight(index, 38)
        self.table.setCellWidget(index, 0, row["name"])
        for column, view in enumerate(VIEWS, start=1):
            selected = getattr(view_set, f"{view}_csv") if view_set else suggestion.get(view) if suggestion else None
            combo = self._path_combo(selected, view=view, recording=row["name"].text())
            row[view] = combo
            self.table.setCellWidget(index, column, combo)
            combo.currentIndexChanged.connect(self._refresh_status)
            combo.editTextChanged.connect(self._refresh_status)
            combo.activated.connect(lambda _index, row=row: self.table.setCurrentCell(self._rows.index(row), 0))
        row["status"] = QTableWidgetItem()
        row["status"].setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(index, 4, row["status"])
        details = QWidget()
        grid = QGridLayout(details)
        metadata = view_set.metadata if view_set else None
        for field_index, (field, label) in enumerate(
            (
                ("animal_id", "Animal ID"),
                ("session_id", "Session ID"),
                ("group", "Group"),
                ("timepoint", "Time point"),
                ("sex", "Sex"),
                ("trial", "Trial"),
            )
        ):
            editor = QLineEdit(getattr(metadata, field, "") if metadata else "")
            set_tooltip(editor, {
                "animal_id": "Stable animal identifier used to group repeated recordings from the same animal.",
                "session_id": "Identifier for the recording session, used with animal ID when summarizing measurements.",
                "group": "Study group assigned to this recording, such as treatment or control.",
                "timepoint": "Study time point for this recording, such as baseline or a post-treatment day.",
                "sex": "Animal sex recorded as study metadata.",
                "trial": "Trial identifier distinguishing recordings within the same session.",
            }[field])
            row[field] = editor
            grid.addWidget(QLabel(label), field_index // 2, (field_index % 2) * 2)
            grid.addWidget(editor, field_index // 2, (field_index % 2) * 2 + 1)
        lesion = QComboBox()
        set_tooltip(lesion, "Brain hemisphere affected by the lesion. Used to identify ipsilateral and contralateral measurements; select unknown when unavailable.")
        lesion.addItems(["unknown", "none", "left", "right"])
        lesion.setCurrentText(metadata.lesion_hemisphere if metadata else "unknown")
        row["lesion_hemisphere"] = lesion
        grid.addWidget(QLabel("Lesion hemisphere"), 3, 0)
        grid.addWidget(lesion, 3, 1)
        row["details"] = details
        self.details_stack.addWidget(details)
        self._rows.append(row)
        row["name"].textChanged.connect(self._refresh_status)
        row["animal_id"].textChanged.connect(self._refresh_status)
        self.table.setCurrentCell(index, 0)
        self._refresh_status()
        return row

    def _remove_selected(self):
        index = self.table.currentRow()
        if 0 <= index < len(self._rows):
            self._remove_row(self._rows[index])

    def _remove_row(self, row):
        if row not in self._rows:
            return
        index = self._rows.index(row)
        self._rows.remove(row)
        self.table.removeRow(index)
        self.details_stack.removeWidget(row["details"])
        row["details"].deleteLater()
        self._refresh_status()

    def _path_combo(self, selected=None, *, view=None, recording=""):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMinimumWidth(115)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        self._set_ranked_choices(combo, view, recording=recording)
        combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        combo.completer().setFilterMode(Qt.MatchContains)
        combo.completer().setCaseSensitivity(Qt.CaseInsensitive)
        if selected is not None:
            index = combo.findData(str(Path(selected).expanduser().resolve()))
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.lineEdit().setCursorPosition(0)
        return combo

    def _set_ranked_choices(self, combo, view, **context):
        selected, text = combo_path(combo), combo.currentText()
        cursor = combo.lineEdit().cursorPosition()
        ranked = rank_view_candidates(self._csv_files, view, bodyparts_by_path=self._bodyparts, **context)
        blocked = combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("Choose CSV…", "")
            for candidate in ranked:
                path = candidate.path
                combo.addItem(self._choice_labels[path], str(path))
                combo.setItemData(combo.count() - 1, "\n".join((str(path), *candidate.reasons)), Qt.ToolTipRole)
            if selected is not None:
                combo.setCurrentIndex(combo.findData(str(selected)))
            elif text and text != "Choose CSV…":
                combo.setCurrentIndex(-1)
                combo.setEditText(text)
            else:
                combo.setCurrentIndex(0)
            combo.lineEdit().setCursorPosition(cursor)
        finally:
            combo.blockSignals(blocked)

    def _refresh_candidate_ranking(self):
        assigned = {combo_path(row[view]) for row in self._rows for view in VIEWS} - {None}
        for row in self._rows:
            own = tuple(combo_path(row[view]) for view in VIEWS)
            signature = (row["name"].text(), row["animal_id"].text(), own, frozenset(assigned))
            if row.get("ranking_context") == signature:
                continue
            row["ranking_context"] = signature
            for view in VIEWS:
                references = tuple(combo_path(row[other]) for other in VIEWS
                                   if other != view and combo_path(row[other]) is not None)
                if not references and combo_path(row[view]) is not None:
                    references = (combo_path(row[view]),)
                self._set_ranked_choices(
                    row[view], view, recording=row["name"].text(), reference_paths=references,
                    used_paths=assigned - {path for path in own if path is not None}, animal_id=row["animal_id"].text(),
                )

    def _use_filename_pairs(self):
        updating = self._updating_pairings
        self._updating_pairings = True
        try:
            self._fill_unmatched_views()
        finally:
            self._updating_pairings = updating
        self._refresh_status()

    def _fill_unmatched_views(self):
        for suggestion in build_view_pair_rows(self._csv_files, self._bodyparts):
            candidates = {view: suggestion.get(view) for view in VIEWS}
            if not any(candidates.values()):
                continue
            used = {combo_path(row[view]) for row in self._rows for view in VIEWS} - {None}
            match = None
            for row in self._rows:
                assigned = {view: combo_path(row[view]) for view in VIEWS}
                consistent = all(path is None or path == candidates[view] for view, path in assigned.items())
                related = row["name"].text() == suggestion["name"] or any(
                    path is not None and path == candidates[view] for view, path in assigned.items()
                )
                if consistent and related:
                    match = row
                    break
            if match is not None:
                for view, path in candidates.items():
                    if path is not None and path not in used and combo_path(match[view]) is None:
                        match[view].setCurrentIndex(match[view].findData(str(path)))
            elif not used.intersection(path for path in candidates.values() if path is not None):
                self._add_row(suggestion=suggestion)

    def _row_errors(self):
        errors = [[] for _ in self._rows]
        names, paths = {}, {}
        for index, row in enumerate(self._rows):
            name = row["name"].text().strip()
            if not name:
                errors[index].append("Name required")
            elif name in {".", ".."} or "/" in name or "\\" in name:
                errors[index].append("Use a name without path separators")
            names.setdefault(name.casefold(), []).append(index)
            missing = []
            for view in VIEWS:
                path = combo_path(row[view])
                if path is None:
                    missing.append(view)
                else:
                    paths.setdefault(path, []).append(index)
                    inferred = csv_view_from_bodyparts(self._bodyparts.get(path, ()))
                    if inferred is None:
                        inferred, _ = csv_view_evidence(path)
                    if inferred is not None and inferred != view:
                        errors[index].append(f"{view.title()} CSV appears to be {inferred} view")
            if missing:
                errors[index].append("Missing " + ", ".join(missing))
        for indices in names.values():
            if len(indices) > 1:
                for index in indices:
                    errors[index].append("Duplicate name")
        for indices in paths.values():
            if len(indices) > 1:
                for index in set(indices):
                    errors[index].append("CSV used more than once")
        return errors

    def _refresh_status(self, *_args):
        if self._updating_pairings:
            return
        self._refresh_candidate_ranking()
        errors = self._row_errors()
        for row, problems in zip(self._rows, errors, strict=True):
            row["status"].setText("; ".join(problems) if problems else "Ready")
            for view in VIEWS:
                combo = row[view]
                index = combo.findData(str(combo_path(combo))) if combo_path(combo) is not None else -1
                set_tooltip(combo, combo.itemData(index, Qt.ToolTipRole) if index >= 0 else 'Search and select a CSV')
        ready = sum(not problems for problems in errors)
        used = {combo_path(row[view]) for row in self._rows for view in VIEWS}
        unused = [path for path in self._csv_files if path not in used]
        self._unused = unused
        summary = f"{ready} recording{'s' if ready != 1 else ''} ready"
        if ready != len(errors):
            summary += f" · {len(errors) - ready} need attention"
        if unused:
            summary += f" · {len(unused)} unassigned CSV{'s' if len(unused) != 1 else ''}"
        self.summary_label.setText(summary)
        names = ", ".join(path.name for path in unused[:4])
        extra = f" (+{len(unused) - 4} more)" if len(unused) > 4 else ""
        self.unassigned_label.setText(f"{len(unused)} unassigned CSVs" + (f": {names}{extra}" if unused else ""))
        self.unassigned_label.setToolTip("\n".join(str(path) for path in unused))
        self.exclude_unassigned.setVisible(bool(unused))
        self.exclude_unassigned.setText(f"Exclude {len(unused)} unassigned CSV{'s' if len(unused) != 1 else ''} from this workflow")
        self.buttons.button(QDialogButtonBox.Save).setEnabled(
            bool(self._rows) and ready == len(self._rows) and (not unused or self.exclude_unassigned.isChecked())
        )
        self.remove_button.setEnabled(bool(self._rows))
        self._filter_rows()

    def _filter_rows(self, *_args):
        query = self.search_edit.text().strip().casefold()
        for index, row in enumerate(self._rows):
            text = " ".join([row["name"].text(), *(row[view].currentText() for view in VIEWS), row["status"].text()])
            self.table.setRowHidden(index, query not in text.casefold())

    def _select_details(self, current_row, *_args):
        if 0 <= current_row < len(self._rows):
            row = self._rows[current_row]
            self.details_stack.setCurrentWidget(row["details"])
            self.details_toggle.setText(f"Study details · {row['name'].text()}")

    def _toggle_details(self, expanded):
        self.details_stack.setVisible(expanded)
        self.details_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _collect_pairings(self):
        for row, problems in zip(self._rows, self._row_errors(), strict=True):
            if problems:
                raise ValueError(f"{row['name'].text()}: {'; '.join(problems)}")
        if not self._rows:
            raise ValueError("Add at least one recording.")
        if self._unused and not self.exclude_unassigned.isChecked():
            raise ValueError("Assign every CSV or select Exclude unassigned CSVs.")
        return [
            AlmaViewCsvSet(
                name=row["name"].text().strip(),
                **{f"{view}_csv": combo_path(row[view]) for view in VIEWS},
                metadata=StrokeStudyMetadata(
                    **{
                        field: row[field].text().strip()
                        for field in ("animal_id", "group", "sex", "timepoint", "trial", "session_id")
                    },
                    lesion_hemisphere=row["lesion_hemisphere"].currentText(),
                ),
            )
            for row in self._rows
        ]

    def accept(self):
        try:
            self._pairings = self._collect_pairings()
        except ValueError as exc:
            QMessageBox.warning(self, "Pairing needs attention", str(exc))
            return
        super().accept()

    def pairings(self):
        return list(self._pairings)

    def excluded_paths(self):
        return list(self._unused) if self.exclude_unassigned.isChecked() else []


def combo_path(combo):
    index = combo.findText(combo.currentText(), Qt.MatchExactly)
    value = combo.itemData(index) if index >= 0 else None
    return Path(str(value)) if value else None


def csv_choice_label(path, all_paths):
    if sum(candidate.name == path.name for candidate in all_paths) <= 1:
        return path.name
    return f"{path.name}  ({path.parent})"
