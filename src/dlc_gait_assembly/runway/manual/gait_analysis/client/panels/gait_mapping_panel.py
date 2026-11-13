"""Display all camera marker assignments inline in the gait Labels settings section."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    BOTTOM_CENTER_LABELS,
    BOTTOM_VIEW_LABELS,
    FORELIMB_SIDE_VIEW_LABELS,
    SIDE_VIEW_LABELS,
    STANDARD_BODYPARTS,
    auto_bodypart_label,
    raw_label_for_standard,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    resolve_view_mappings,
)
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitMappingPanel:
    """GaitMappingPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view
        self._mapping_context = "__default__"
        self._refreshing = False

    def _load_bodypart_mapping_from_first_file(self) -> None:
        if self.view.inputs._is_three_view_mode():
            self._refresh_view_mapping_choices()
            return
        if not self.view.state.selected_files:
            self.view.mapping_status_label.setText("Add a CSV to load bodypart labels, or type labels below.")
            return
        csv_path = self.view.inputs._selected_preview_file()
        try:
            self.view.state.raw_bodyparts = self.view.analysis.inputs.bodyparts(csv_path)
        except Exception as exc:
            self.view.state.raw_bodyparts = []
            self._refresh_bodypart_mapping_choices()
            self.view.mapping_status_label.setText("Could not read bodypart labels.")
            QMessageBox.critical(self.view, "Could not read bodypart labels", str(exc))
            return
        self._refresh_bodypart_mapping_choices()
        self._apply_auto_bodypart_mapping()
        self.view.mapping_status_label.setText(f"{len(self.view.state.raw_bodyparts)} labels loaded from {csv_path.name}.")

    def _show_label_assignments(self) -> None:
        """Keep existing action callers on the inline Labels section."""
        self._refresh_view_mapping_choices()
        self.view.settings_tabs.setCurrentWidget(self.view.mapping_tab)

    def _refresh_bodypart_mapping_choices(self) -> None:
        choices = ["(none)", *self.view.state.raw_bodyparts]
        for combo in self.view._bodypart_combos.values():
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(choices)
            if current in choices:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        self._update_mapping_enabled()

    def _refresh_view_mapping_choices(self) -> None:
        if not hasattr(self.view, "_view_bodypart_combos"):
            return
        three_view = self.view.inputs._is_three_view_mode()
        self.view.single_mapping_box.setVisible(not three_view)
        for box in self.view.view_mapping_boxes.values():
            box.setVisible(three_view)
        self.view.use_custom_mapping_checkbox.setVisible(not three_view)
        if not three_view:
            return
        view_set = self.view.inputs._selected_view_set()
        self._mapping_context = view_set.name if view_set else "__default__"
        mapping = resolve_view_mappings(self.view.state.view_label_mappings, self._mapping_context) or {}
        self._refreshing = True
        try:
            for camera, combos in self.view._view_bodypart_combos.items():
                path = getattr(view_set, f"{camera}_csv") if view_set else None
                labels = list(self.view.state.csv_bodyparts.get(path, ())) if path else []
                self.view.view_mapping_file_labels[camera].setText(
                    path.name if path else "Type DLC labels now, or add matched CSVs to load choices."
                )
                self.view.view_mapping_file_labels[camera].setToolTip(str(path) if path else "")
                for standard, combo in combos.items():
                    selected = raw_label_for_standard(mapping.get(camera, {}), standard)
                    if selected is None and self._mapping_context not in self.view.state.view_label_mappings:
                        selected = auto_bodypart_label(labels, standard, view=camera)
                    combo.blockSignals(True)
                    combo.clear()
                    combo.addItems(["(none)", *(labels or list(combos))])
                    combo.setCurrentText(selected or "(none)")
                    combo.blockSignals(False)
        finally:
            self._refreshing = False
        self._save_view_mapping()

    def _view_mapping(self):
        result = {}
        for camera, combos in self.view._view_bodypart_combos.items():
            mapping = {}
            for standard, combo in combos.items():
                raw = combo.currentText().strip()
                if not raw or raw == "(none)":
                    continue
                if raw in mapping:
                    raise ValueError(f"{camera.upper()}: {raw!r} is assigned to more than one bodypart.")
                mapping[raw] = standard
            result[camera] = mapping
        return result

    def _save_view_mapping(self) -> None:
        if self._refreshing or not self.view.inputs._is_three_view_mode():
            return
        try:
            mapping = self._view_mapping()
        except ValueError as exc:
            self.view.mapping_status_label.setText(str(exc))
            return
        if any(mapping.values()) or self._mapping_context in self.view.state.view_label_mappings:
            self.view.state.view_label_mappings[self._mapping_context] = mapping
        count = sum(len(labels) for labels in mapping.values())
        context = self._mapping_context if self._mapping_context != "__default__" else "workflow defaults"
        self.view.mapping_status_label.setText(f"{count}/26 labels assigned for {context}.")

    def _view_assignment_changed(self) -> None:
        self._save_view_mapping()
        if not self._refreshing:
            self.view.controller._invalidate_stickplot_preview("Bodypart label assignments changed.")

    def _apply_auto_bodypart_mapping(self) -> None:
        if self.view.inputs._is_three_view_mode():
            view_set = self.view.inputs._selected_view_set()
            if view_set is None:
                self.view.mapping_status_label.setText("Add matched CSVs to auto-detect labels, or assign labels below.")
                return
            for camera, combos in self.view._view_bodypart_combos.items():
                labels = list(self.view.state.csv_bodyparts.get(getattr(view_set, f"{camera}_csv"), ()))
                for standard, combo in combos.items():
                    combo.setCurrentText(auto_bodypart_label(labels, standard, view=camera) or "(none)")
            self._save_view_mapping()
            return
        for standard, combo in self.view._bodypart_combos.items():
            combo.setCurrentText(auto_bodypart_label(self.view.state.raw_bodyparts, standard) or "(none)")

    def _update_mapping_enabled(self) -> None:
        enabled = self.view.use_custom_mapping_checkbox.isChecked()
        for combo in self.view._bodypart_combos.values():
            combo.setEnabled(enabled)
        self._refresh_view_mapping_choices()

    def _collect_bodypart_mapping(self) -> dict[str, str] | None:
        if not self.view.use_custom_mapping_checkbox.isChecked():
            return None
        return {
            combo.currentText().strip(): standard for standard, combo in self.view._bodypart_combos.items()
            if combo.currentText().strip() not in ("", "(none)")
        } or None

    def _collect_view_bodypart_mapping(self) -> dict[str, object] | None:
        if not self.view.inputs._is_three_view_mode():
            return None
        self._view_mapping()  # Reject conflicting assignments before collecting a run configuration.
        return self.view.state.view_label_mappings or None


def _marker_grid(combos, labels, on_change):
    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(8)
    for row, standard in enumerate(labels):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.addItem("(none)")
        combo.setMinimumWidth(140)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        set_tooltip(combo, f"DLC label assigned to {standard}. Choose a label or type its exact name.")
        combos[standard] = combo
        if on_change is not None:
            combo.currentTextChanged.connect(on_change)
        grid.addWidget(QLabel(standard), row, 0)
        grid.addWidget(combo, row, 1)
    grid.setColumnStretch(1, 1)
    return grid


def build_gait_marker_mapping(self, mapping_tab_layout):
    title = QLabel("DeepLabCut bodypart markers")
    title.setObjectName("TitleLabel")
    mapping_tab_layout.addWidget(title)
    note = QLabel("Assign the DLC label for each marker below. Leave markers you do not track set to (none).")
    note.setWordWrap(True)
    mapping_tab_layout.addWidget(note)
    self.use_custom_mapping_checkbox = QCheckBox("Use custom mapping")
    set_tooltip(self.use_custom_mapping_checkbox, 'Use your chosen DeepLabCut marker names instead of automatically matching markers to standard body parts.')
    mapping_tab_layout.addWidget(self.use_custom_mapping_checkbox)
    header = QHBoxLayout()
    self.reload_mapping_button = QPushButton("Load from CSV")
    self.auto_mapping_button = QPushButton("Auto detect")
    header.addWidget(self.reload_mapping_button)
    header.addWidget(self.auto_mapping_button)
    mapping_tab_layout.addLayout(header)
    self.mapping_status_label = QLabel("Add matched CSVs to detect labels, or type labels below.")
    self.mapping_status_label.setObjectName("MutedLabel")
    self.mapping_status_label.setWordWrap(True)
    status_policy = self.mapping_status_label.sizePolicy()
    status_policy.setHorizontalPolicy(QSizePolicy.Ignored)
    self.mapping_status_label.setSizePolicy(status_policy)
    mapping_tab_layout.addWidget(self.mapping_status_label)
    self.single_mapping_box = QGroupBox("Side view")
    single_layout = QVBoxLayout(self.single_mapping_box)
    single_layout.addLayout(_marker_grid(self._bodypart_combos, STANDARD_BODYPARTS, None))
    mapping_tab_layout.addWidget(self.single_mapping_box)
    self._view_bodypart_combos = {}
    self.view_mapping_boxes = {}
    self.view_mapping_file_labels = {}
    for camera in ("left", "right", "bottom"):
        box = QGroupBox(camera.upper())
        box_layout = QVBoxLayout(box)
        source = QLabel()
        source.setObjectName("MutedLabel")
        source.setWordWrap(True)
        # DLC filenames are often long, unbroken strings. Their size hint must not
        # widen the scroll content and push the assignment dropdowns offscreen.
        source_policy = source.sizePolicy()
        source_policy.setHorizontalPolicy(QSizePolicy.Ignored)
        source.setSizePolicy(source_policy)
        box_layout.addWidget(source)
        combos = {}
        labels = BOTTOM_VIEW_LABELS + BOTTOM_CENTER_LABELS if camera == "bottom" else SIDE_VIEW_LABELS + FORELIMB_SIDE_VIEW_LABELS
        box_layout.addLayout(_marker_grid(combos, labels, self.mapping._view_assignment_changed))
        self._view_bodypart_combos[camera] = combos
        self.view_mapping_boxes[camera] = box
        self.view_mapping_file_labels[camera] = source
        mapping_tab_layout.addWidget(box)
    mapping_tab_layout.addStretch(1)
